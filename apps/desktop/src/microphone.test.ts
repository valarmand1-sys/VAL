// Real device release — owner execution order, 24 September 2026, §6.1 and §19.
//
// The assertion this file exists for: **mute stops every track, drops the stream and
// disconnects the nodes.** Not `track.enabled = false`, not a stream held open with
// its samples discarded, not a warm microphone kept for a faster unmute. The macOS
// orange indicator going dark is the owner's own proof, and it goes dark only if
// this is true — so this is tested against a fake device that records what happened
// to it, and the physical indicator is accepted separately by him.

import { describe, expect, it, vi } from "vitest";

import {
  CAPTURE_CONSTRAINTS,
  CHUNK_SAMPLES,
  MicrophoneCapture,
  TARGET_SAMPLE_RATE,
  WORKLET_MODULE_URL,
  type AppliedCaptureSettings,
  type CapturePlatform,
} from "./microphone";

/** The processor as the application actually serves it. */
const PROCESSOR = String(
  Object.values(
    import.meta.glob("../public/pcm-worklet.js", {
      query: "?raw",
      import: "default",
      eager: true,
    }),
  )[0],
);

class FakeTrack {
  readyState: "live" | "ended" = "live";
  enabled = true;
  stops = 0;
  stop(): void {
    this.stops += 1;
    this.readyState = "ended";
  }
}

class FakeStream {
  constructor(readonly tracks: FakeTrack[]) {}
  getTracks(): FakeTrack[] {
    return this.tracks;
  }
  /** A real stream reports its audio tracks and their applied settings. */
  getAudioTracks(): FakeTrack[] {
    return this.tracks;
  }
}

class FakeNode {
  disconnects = 0;
  connect(): void {}
  disconnect(): void {
    this.disconnects += 1;
  }
}

class FakeWorkletNode extends FakeNode {
  port = { onmessage: null as ((event: MessageEvent) => void) | null };
}

class FakeContext {
  closed = 0;
  addedModules: string[] = [];
  source = new FakeNode();
  audioWorklet = {
    addModule: async (url: string) => {
      this.addedModules.push(url);
    },
  };
  createMediaStreamSource(): FakeNode {
    return this.source;
  }
  async close(): Promise<void> {
    this.closed += 1;
  }
}

interface Harness {
  platform: CapturePlatform;
  context: FakeContext;
  tracks: FakeTrack[];
  worklet: FakeWorkletNode;
  constraints: MediaStreamConstraints[];
}

function harness(tracks = 1): Harness {
  const made = Array.from({ length: tracks }, () => new FakeTrack());
  const context = new FakeContext();
  const worklet = new FakeWorkletNode();
  const constraints: MediaStreamConstraints[] = [];
  // The worklet node is constructed with `new AudioWorkletNode(...)`, so the fake
  // has to be reachable through the global the module uses.
  (globalThis as Record<string, unknown>).AudioWorkletNode = class {
    constructor() {
      return worklet as unknown as AudioWorkletNode;
    }
  };
  const platform: CapturePlatform = {
    getUserMedia: async (asked) => {
      constraints.push(asked);
      return new FakeStream(made) as unknown as MediaStream;
    },
    createContext: () => context as unknown as AudioContext,
    workletModuleUrl: WORKLET_MODULE_URL,
  };
  return { platform, context, tracks: made, worklet, constraints };
}

describe("acquiring the device", () => {
  it("asks for local echo cancellation, mono, and no video", () => {
    // §13: Val's own speaker output must not be accepted as owner speech, and the
    // local WebRTC facility is how that is asked for. Never by muting while she
    // speaks, which would destroy barge-in.
    expect(CAPTURE_CONSTRAINTS.video).toBe(false);
    const audio = CAPTURE_CONSTRAINTS.audio as MediaTrackConstraints;
    expect(audio.echoCancellation).toBe(true);
    expect(audio.channelCount).toBe(1);
  });

  it("reports live only once a real track is live", async () => {
    const world = harness();
    const events: string[] = [];
    const capture = new MicrophoneCapture(
      {
        onChunk: () => events.push("chunk"),
        onLive: () => events.push("live"),
        onReleased: () => events.push("released"),
        onFailure: (detail) => events.push(`failed:${detail}`),
      },
      world.platform,
    );
    await capture.open();
    expect(events).toEqual(["live"]);
    expect(capture.live).toBe(true);
    expect(world.constraints).toHaveLength(1);
  });

  it("fails closed when the platform hands back no live track", async () => {
    const world = harness();
    world.tracks[0]!.readyState = "ended";
    const events: string[] = [];
    const capture = new MicrophoneCapture(
      {
        onChunk: () => events.push("chunk"),
        onLive: () => events.push("live"),
        onReleased: () => events.push("released"),
        onFailure: (detail) => events.push(`failed:${detail}`),
      },
      world.platform,
    );
    await capture.open();
    expect(events).toContain("released");
    expect(events.some((event) => event.startsWith("failed:"))).toBe(true);
    expect(events).not.toContain("live");
  });

  it("reports a refused permission and holds nothing", async () => {
    const world = harness();
    const platform: CapturePlatform = {
      ...world.platform,
      getUserMedia: async () => {
        throw new Error("Permission denied");
      },
    };
    const events: string[] = [];
    const capture = new MicrophoneCapture(
      {
        onChunk: () => undefined,
        onLive: () => events.push("live"),
        onReleased: () => events.push("released"),
        onFailure: (detail) => events.push(`failed:${detail}`),
      },
      platform,
    );
    await capture.open();
    expect(events).toEqual(["released", "failed:Permission denied"]);
    expect(capture.live).toBe(false);
  });
});

describe("mute releases the device", () => {
  it("stops every track, not the first", async () => {
    const world = harness(2);
    const capture = new MicrophoneCapture(
      { onChunk: () => undefined, onLive: () => undefined, onReleased: () => undefined, onFailure: () => undefined },
      world.platform,
    );
    await capture.open();
    capture.release();
    for (const track of world.tracks) {
      expect(track.stops).toBe(1);
      expect(track.readyState).toBe("ended");
    }
    expect(capture.live).toBe(false);
  });

  it("does not merely disable the track", async () => {
    const world = harness();
    const capture = new MicrophoneCapture(
      { onChunk: () => undefined, onLive: () => undefined, onReleased: () => undefined, onFailure: () => undefined },
      world.platform,
    );
    await capture.open();
    capture.release();
    // The distinction the whole rule is about: a disabled track is still a held
    // device, and the orange indicator stays lit.
    expect(world.tracks[0]!.enabled).toBe(true);
    expect(world.tracks[0]!.stops).toBe(1);
  });

  it("disconnects the worklet and the source and closes the context", async () => {
    const world = harness();
    const capture = new MicrophoneCapture(
      { onChunk: () => undefined, onLive: () => undefined, onReleased: () => undefined, onFailure: () => undefined },
      world.platform,
    );
    await capture.open();
    capture.release();
    expect(world.worklet.disconnects).toBe(1);
    expect(world.worklet.port.onmessage).toBeNull();
    expect(world.context.source.disconnects).toBe(1);
    expect(world.context.closed).toBe(1);
  });

  it("accepts no further sample after release, even one already in flight", async () => {
    const world = harness();
    const chunks: ArrayBuffer[] = [];
    const capture = new MicrophoneCapture(
      { onChunk: (pcm) => chunks.push(pcm), onLive: () => undefined, onReleased: () => undefined, onFailure: () => undefined },
      world.platform,
    );
    await capture.open();
    const post = world.worklet.port.onmessage;
    expect(post).not.toBeNull();
    post?.({ data: new ArrayBuffer(8) } as MessageEvent);
    expect(chunks).toHaveLength(1);
    capture.release();
    // The handler is detached, and the accepting flag is false besides: a chunk
    // arriving through a retained reference is still dropped.
    post?.({ data: new ArrayBuffer(8) } as MessageEvent);
    expect(chunks).toHaveLength(1);
  });

  it("is idempotent, because a release that cannot run twice will one day not run", async () => {
    const world = harness();
    const released: number[] = [];
    const capture = new MicrophoneCapture(
      { onChunk: () => undefined, onLive: () => undefined, onReleased: () => released.push(1), onFailure: () => undefined },
      world.platform,
    );
    await capture.open();
    capture.release();
    capture.release();
    capture.release();
    expect(world.tracks[0]!.stops).toBe(1);
    expect(released).toHaveLength(3);
  });
});

describe("nothing accumulates and nothing records", () => {
  it("uses an AudioWorklet and never MediaRecorder or ScriptProcessor", () => {
    const source = PROCESSOR;
    expect(source).toContain("AudioWorkletProcessor");
    expect(source).not.toContain("MediaRecorder");
    expect(source).not.toContain("ScriptProcessorNode");
  });

  it("holds one bounded chunk and no history", () => {
    // The worklet's buffer is exactly one chunk long; there is no growing array
    // and no session recording anywhere in it.
    expect(PROCESSOR).toContain("new Float32Array(this.chunkSamples)");
    expect(PROCESSOR).not.toMatch(/push\(/);
    expect(PROCESSOR).not.toContain("concat");
  });

  it("targets exactly the recognizer's contract", () => {
    expect(TARGET_SAMPLE_RATE).toBe(16_000);
    expect(CHUNK_SAMPLES).toBe(320); // 20 ms
    expect(PROCESSOR).toContain("Int16Array");
  });

  it("transfers each chunk rather than copying it onward", () => {
    // `postMessage(buffer, [buffer])` transfers ownership, so the audio thread does
    // not keep a second copy of what it just sent.
    expect(PROCESSOR).toContain("this.port.postMessage(out.buffer, [out.buffer])");
  });

  it("calls getUserMedia in exactly one place in the whole application", async () => {
    // §3 and §15: the only OS capture implementation lives in the desktop
    // presentation layer, and a second call site is what this catches.
    const modules = import.meta.glob("./*.ts", { query: "?raw", import: "default", eager: true });
    const offenders = Object.entries(modules)
      .filter(([path]) => !path.endsWith(".test.ts"))
      .filter(([, source]) => String(source).includes("getUserMedia("))
      .map(([path]) => path);
    expect(offenders).toEqual(["./microphone.ts"]);
    expect(vi.isMockFunction(() => undefined)).toBe(false);
  });

  it("no module anywhere creates a MediaRecorder", () => {
    const modules = import.meta.glob("./*.ts", { query: "?raw", import: "default", eager: true });
    for (const [path, source] of Object.entries(modules)) {
      if (path.endsWith(".test.ts")) continue;
      expect(String(source)).not.toContain("new MediaRecorder");
    }
  });
});


describe("the Content Security Policy refusal that failed owner acceptance step A", () => {
  // Owner acceptance, 24 September 2026. Voice reached `Voice Starting…`, macOS
  // presented the microphone prompt correctly, and startup then failed with
  // `Not allowed by CSP`. Reproduced under the application's exact policy:
  //
  //   Loading the script 'blob:…' violates the following Content Security Policy
  //   directive: "default-src 'self'". Note that 'script-src-elem' was not
  //   explicitly set, so 'default-src' is used as a fallback.
  //
  // The processor module was built as a string and loaded from a blob. These hold
  // the fix in place: the module is served by the application, and no blob-backed
  // script is created anywhere in the desktop.

  it("fetches the processor from the application's own origin", () => {
    expect(WORKLET_MODULE_URL).toBe("/pcm-worklet.js");
    expect(WORKLET_MODULE_URL.startsWith("blob:")).toBe(false);
    expect(WORKLET_MODULE_URL.startsWith("data:")).toBe(false);
    expect(WORKLET_MODULE_URL.startsWith("http")).toBe(false);
    // Relative to the app: satisfied by `default-src 'self'` with no exception.
    expect(WORKLET_MODULE_URL.startsWith("/")).toBe(true);
  });

  it("asks the platform for that URL and for no blob", async () => {
    const world = harness();
    const capture = new MicrophoneCapture(
      {
        onChunk: () => undefined,
        onLive: () => undefined,
        onReleased: () => undefined,
        onFailure: () => undefined,
      },
      world.platform,
    );
    await capture.open();
    expect(world.context.addedModules).toEqual([WORKLET_MODULE_URL]);
  });

  it("releases a granted device when the worklet module is refused", async () => {
    // **The defect the CSP failure hid.** The device had been granted, the module
    // load then failed, and the release path had nothing to stop because the stream
    // was still only a local variable. A live track held by nothing, released
    // whenever the engine chose to collect it — which is not "fail closed".
    const world = harness();
    const refusing: CapturePlatform = {
      ...world.platform,
      createContext: () =>
        ({
          ...world.context,
          audioWorklet: {
            addModule: async () => {
              throw new DOMException("Not allowed by CSP", "AbortError");
            },
          },
          createMediaStreamSource: () => world.context.source,
          close: async () => undefined,
        }) as unknown as AudioContext,
    };
    const events: string[] = [];
    const capture = new MicrophoneCapture(
      {
        onChunk: () => undefined,
        onLive: () => events.push("live"),
        onReleased: () => events.push("released"),
        onFailure: (detail) => events.push(`failed:${detail}`),
      },
      refusing,
    );
    await capture.open();

    // Every track the platform granted is stopped, deterministically.
    expect(world.tracks[0]!.stops).toBe(1);
    expect(world.tracks[0]!.readyState).toBe("ended");
    expect(capture.live).toBe(false);
    // Released **before** the failure is reported, and never reported as live.
    expect(events).toEqual(["released", "failed:Not allowed by CSP"]);
  });

  it("creates no object URL for a script anywhere in the desktop", () => {
    // Attachment previews legitimately use `createObjectURL` for images, video and
    // audio, which `img-src`/`media-src` permit. A **script** built that way is
    // what the policy refuses, so the assertion is about the type.
    const modules = import.meta.glob("./*.ts", { query: "?raw", import: "default", eager: true });
    for (const [path, source] of Object.entries(modules)) {
      if (path.endsWith(".test.ts")) continue;
      const text = String(source);
      expect(text).not.toContain("text/javascript");
      expect(text).not.toContain("application/javascript");
    }
  });

  it("the served processor is valid JavaScript with no template interpolation left in it", () => {
    // The second defect this fix uncovered. The processor began life as a template
    // string in TypeScript, and extracting it into a file left `${TARGET_SAMPLE_RATE}`
    // behind as literal text — a SyntaxError at line 23, found by loading the real
    // built file under the real policy rather than by reading it.
    expect(PROCESSOR).not.toContain("${");
    expect(() => new Function(`${PROCESSOR.replace("registerProcessor", "void")}`)).not.toThrow();
  });

  it("the served fallbacks equal the constants the code passes", () => {
    // `processorOptions` supplies both on every construction; these are the
    // fallbacks, and they may not drift from the TypeScript constants.
    expect(PROCESSOR).toContain(`|| ${TARGET_SAMPLE_RATE}`);
    expect(PROCESSOR).toContain(`|| ${CHUNK_SAMPLES}`);
  });

  it("the processor the application serves registers the processor the code asks for", () => {
    // The string and the file could drift apart; they cannot now, because there is
    // only the file — and this checks the name the node is constructed with.
    expect(PROCESSOR).toContain("registerProcessor('val-pcm'");
    const modules = import.meta.glob("./microphone.ts", {
      query: "?raw",
      import: "default",
      eager: true,
    });
    expect(String(Object.values(modules)[0])).toContain('"val-pcm"');
  });
});

describe("what the platform actually applied (§25)", () => {
  it("reports the track's own settings where the platform states them", async () => {
    const world = harness();
    // A platform that answers, as WKWebView does where it implements getSettings.
    const stated = {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: false,
      sampleRate: 48000,
      channelCount: 1,
    };
    (world.tracks[0] as unknown as { getSettings: () => unknown }).getSettings = () => stated;
    let applied: unknown = null;
    const capture = new MicrophoneCapture(
      {
        onChunk: () => undefined,
        onLive: (settings) => {
          applied = settings;
        },
        onReleased: () => undefined,
        onFailure: () => undefined,
      },
      world.platform,
    );
    await capture.open();
    expect(applied).toEqual(stated);
  });

  it("records not-stated rather than false when the platform says nothing", async () => {
    const world = harness();
    let applied: AppliedCaptureSettings | null = null;
    const capture = new MicrophoneCapture(
      {
        onChunk: () => undefined,
        onLive: (settings) => {
          applied = settings;
        },
        onReleased: () => undefined,
        onFailure: () => undefined,
      },
      world.platform,
    );
    await capture.open();
    // **Null, not false.** "The platform did not say" and "the platform said no" are
    // different facts, and the acceptance question turns on which one it is.
    expect(applied).not.toBeNull();
    expect(applied!.echoCancellation).toBeNull();
    expect(applied!.sampleRate).toBeNull();
  });

  it("never takes the microphone down to report a setting", async () => {
    const world = harness();
    (world.tracks[0] as unknown as { getSettings: () => unknown }).getSettings = () => {
      throw new Error("this platform refuses to say");
    };
    const events: string[] = [];
    const capture = new MicrophoneCapture(
      {
        onChunk: () => undefined,
        onLive: () => events.push("live"),
        onReleased: () => events.push("released"),
        onFailure: (detail) => events.push(`failed:${detail}`),
      },
      world.platform,
    );
    await capture.open();
    // A diagnostic that could end capture would be worse than no diagnostic.
    expect(events).toEqual(["live"]);
    expect(capture.live).toBe(true);
  });
});
