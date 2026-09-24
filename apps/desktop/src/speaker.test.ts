// Physical playback and barge-in — owner execution order, 24 September 2026, §12, §19.
//
// The assertion here: **stopping stops the sound, not only the queue.** A queue
// emptied while a buffer plays on is not an interruption, and the difference is the
// whole of barge-in. Also: playback started is reported from the scheduling call,
// so the record's physical boundary is a real event rather than an intention.

import { describe, expect, it } from "vitest";

import {
  SpeechPlayer,
  decodeSegmentAudio,
  type SegmentAudio,
  type SpeakerObserver,
  type SpeakerPlatform,
} from "./speaker";

class FakeSource {
  started = 0;
  stops = 0;
  disconnects = 0;
  onended: (() => void) | null = null;
  buffer: unknown = null;
  connect(): void {}
  disconnect(): void {
    this.disconnects += 1;
  }
  start(): void {
    this.started += 1;
  }
  stop(): void {
    this.stops += 1;
  }
  /** What a real source does when it finishes on its own. */
  finish(): void {
    this.onended?.();
  }
}

class FakeAudioContext {
  sources: FakeSource[] = [];
  closed = 0;
  decoded = 0;
  failDecode = false;
  destination = {};
  async decodeAudioData(buffer: ArrayBuffer): Promise<unknown> {
    this.decoded += 1;
    if (this.failDecode) throw new Error("not audio");
    // A real decode detaches the buffer; the fake records that the bytes were
    // consumed rather than retained.
    void buffer;
    return { duration: 0.5 };
  }
  createBufferSource(): FakeSource {
    const source = new FakeSource();
    this.sources.push(source);
    return source;
  }
  async close(): Promise<void> {
    this.closed += 1;
  }
}

function world(): { platform: SpeakerPlatform; context: FakeAudioContext } {
  const context = new FakeAudioContext();
  return { platform: { createContext: () => context as unknown as AudioContext }, context };
}

function segment(index: number, text = "Eight, my lord."): SegmentAudio {
  return {
    messageId: "01a0d000-0000-7000-8000-000000000000",
    segmentIndex: index,
    text,
    audio: new ArrayBuffer(16),
  };
}

interface Reported {
  started: number[];
  completed: number[];
  interrupted: [number, string][];
  failed: [number, string][];
}

function observer(): { reported: Reported; hooks: SpeakerObserver } {
  const reported: Reported = { started: [], completed: [], interrupted: [], failed: [] };
  return {
    reported,
    hooks: {
      onStarted: (item: SegmentAudio) => reported.started.push(item.segmentIndex),
      onCompleted: (item: SegmentAudio) => reported.completed.push(item.segmentIndex),
      onInterrupted: (item: SegmentAudio, reason: string) =>
        reported.interrupted.push([item.segmentIndex, reason]),
      onFailed: (item: SegmentAudio, detail: string) =>
        reported.failed.push([item.segmentIndex, detail]),
    },
  };
}

describe("playing Val's speech", () => {
  it("reports started from the scheduling call, which is the physical boundary", async () => {
    const { platform, context } = world();
    const watch = observer();
    const player = new SpeechPlayer(watch.hooks, platform);
    player.enqueue(segment(1));
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    expect(context.sources).toHaveLength(1);
    expect(context.sources[0]!.started).toBe(1);
    expect(watch.reported.started).toEqual([1]);
    // Nothing is reported as completed until the source really ends.
    expect(watch.reported.completed).toEqual([]);
    context.sources[0]!.finish();
    expect(watch.reported.completed).toEqual([1]);
  });

  it("reports a failed decode rather than pretending it played", async () => {
    const { platform, context } = world();
    context.failDecode = true;
    const watch = observer();
    const player = new SpeechPlayer(watch.hooks, platform);
    player.enqueue(segment(1));
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    expect(watch.reported.failed).toHaveLength(1);
    expect(watch.reported.started).toEqual([]);
  });
});

describe("barge-in", () => {
  it("stops the sounding buffer and discards what was queued behind it", async () => {
    const { platform, context } = world();
    const watch = observer();
    const player = new SpeechPlayer(watch.hooks, platform);
    player.enqueue(segment(1));
    player.enqueue(segment(2, "And the wine."));
    player.enqueue(segment(3, "At once."));
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    expect(player.audible).toBe(true);
    expect(player.queued).toBe(2);

    player.stop("the owner spoke");

    // The sound stopped — not merely the queue.
    expect(context.sources[0]!.stops).toBe(1);
    expect(context.sources[0]!.disconnects).toBe(1);
    expect(player.audible).toBe(false);
    expect(player.queued).toBe(0);
    expect(watch.reported.interrupted).toEqual([[1, "the owner spoke"]]);
    // And an interruption is never recorded as a completion.
    expect(watch.reported.completed).toEqual([]);
  });

  it("plays nothing more after a stop", async () => {
    const { platform, context } = world();
    const watch = observer();
    const player = new SpeechPlayer(watch.hooks, platform);
    player.enqueue(segment(1));
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    player.stop("the owner spoke");
    player.enqueue(segment(2));
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    expect(context.sources).toHaveLength(1);
    expect(watch.reported.started).toEqual([1]);
  });

  it("closing releases the audio device and stops anything playing", async () => {
    const { platform, context } = world();
    const watch = observer();
    const player = new SpeechPlayer(watch.hooks, platform);
    player.enqueue(segment(1));
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    player.close();
    expect(context.sources[0]!.stops).toBe(1);
    expect(context.closed).toBe(1);
    expect(watch.reported.interrupted[0]?.[1]).toBe("voice mode ended");
  });
});

describe("the transport", () => {
  it("decodes the service's base64 into the exact bytes", () => {
    const bytes = new Uint8Array([0x52, 0x49, 0x46, 0x46, 0x00, 0xff]);
    const base64 = btoa(String.fromCharCode(...bytes));
    const decoded = new Uint8Array(decodeSegmentAudio(base64));
    expect(Array.from(decoded)).toEqual(Array.from(bytes));
  });

  it("writes no file and keeps no archive", async () => {
    const modules = import.meta.glob("./speaker.ts", {
      query: "?raw",
      import: "default",
      eager: true,
    });
    const source = String(Object.values(modules)[0]);
    for (const forbidden of ["MediaRecorder", "showSaveFilePicker", "createWriteStream", "localStorage"]) {
      expect(source).not.toContain(forbidden);
    }
  });
});
