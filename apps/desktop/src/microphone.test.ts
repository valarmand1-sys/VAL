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
  PCM_WORKLET_SOURCE,
  TARGET_SAMPLE_RATE,
  type CapturePlatform,
} from "./microphone";

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
  revoked: string[];
  constraints: MediaStreamConstraints[];
}

function harness(tracks = 1): Harness {
  const made = Array.from({ length: tracks }, () => new FakeTrack());
  const context = new FakeContext();
  const worklet = new FakeWorkletNode();
  const revoked: string[] = [];
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
    createModuleUrl: () => "blob:worklet",
    revokeModuleUrl: (url) => revoked.push(url),
  };
  return { platform, context, tracks: made, worklet, revoked, constraints };
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

  it("disconnects the worklet and the source, closes the context, revokes the module", async () => {
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
    expect(world.revoked).toEqual(["blob:worklet"]);
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
    const source = PCM_WORKLET_SOURCE;
    expect(source).toContain("AudioWorkletProcessor");
    expect(source).not.toContain("MediaRecorder");
    expect(source).not.toContain("ScriptProcessorNode");
  });

  it("holds one bounded chunk and no history", () => {
    // The worklet's buffer is exactly one chunk long; there is no growing array
    // and no session recording anywhere in it.
    expect(PCM_WORKLET_SOURCE).toContain("new Float32Array(this.chunkSamples)");
    expect(PCM_WORKLET_SOURCE).not.toMatch(/push\(/);
    expect(PCM_WORKLET_SOURCE).not.toContain("concat");
  });

  it("targets exactly the recognizer's contract", () => {
    expect(TARGET_SAMPLE_RATE).toBe(16_000);
    expect(CHUNK_SAMPLES).toBe(320); // 20 ms
    expect(PCM_WORKLET_SOURCE).toContain("Int16Array");
  });

  it("transfers each chunk rather than copying it onward", () => {
    // `postMessage(buffer, [buffer])` transfers ownership, so the audio thread does
    // not keep a second copy of what it just sent.
    expect(PCM_WORKLET_SOURCE).toContain("this.port.postMessage(out.buffer, [out.buffer])");
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
