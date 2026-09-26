// Streamed speech plays as one sentence — owner order, 26 September 2026.
//
// Her first sentence now reaches the desktop in ~1-second pieces while the rest of
// it is still being voiced. These tests hold what that must not break: the pieces of
// one segment are joined on the audio clock with no seam; the segment starts once,
// completes only after its last piece, and the next segment waits for it; a stop
// silences everything scheduled; and the controller keeps each piece with the answer
// that took the segment.

import { describe, expect, it } from "vitest";

import { SpeechPlayer, type SegmentAudio, type SpeakerObserver, type SpeakerPlatform } from "./speaker";
import { SpokenPresentation } from "./spokenPresentation";

class Source {
  buffer: { duration: number } | null = null;
  onended: (() => void) | null = null;
  startedAt: number | null = null;
  stops = 0;
  connect(): void {}
  disconnect(): void {}
  start(when?: number): void {
    this.startedAt = when ?? 0;
  }
  stop(): void {
    this.stops += 1;
  }
  end(): void {
    this.onended?.();
  }
}

function world() {
  const sources: Source[] = [];
  const context = {
    currentTime: 10,
    destination: {},
    decodeAudioData: async (bytes: ArrayBuffer) => ({ duration: bytes.byteLength / 1000 }),
    createBufferSource: () => {
      const source = new Source();
      sources.push(source);
      return source;
    },
    close: async () => undefined,
  };
  const platform: SpeakerPlatform = { createContext: () => context as unknown as AudioContext };
  const events: string[] = [];
  const observer: SpeakerObserver = {
    onStarted: (s) => events.push(`started ${s.segmentIndex}`),
    onCompleted: (s) => events.push(`completed ${s.segmentIndex}`),
    onInterrupted: (s) => events.push(`interrupted ${s.segmentIndex}`),
    onFailed: (s) => events.push(`failed ${s.segmentIndex}`),
  };
  return { sources, context, platform, events, player: new SpeechPlayer(observer, platform) };
}

/** A piece whose audio "lasts" `ms` (the fake decoder reads length as duration). */
function piece(segmentIndex: number, chunk: number, ms: number, last = false): SegmentAudio {
  return { messageId: "m", segmentIndex, text: `segment ${segmentIndex}`, audio: new ArrayBuffer(ms), chunk, last };
}

async function settle(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve();
}

describe("a streamed segment", () => {
  it("is joined on the audio clock with no seam, and starts once", async () => {
    const { player, sources, events } = world();
    player.enqueue(piece(1, 0, 960));
    player.enqueue(piece(1, 1, 960));
    player.enqueue(piece(1, 2, 880));
    await settle();
    const starts = sources.map((s) => s.startedAt as number);
    expect(starts[0]).toBe(10);
    expect(starts[1]).toBeCloseTo(10.96, 9);
    expect(starts[2]).toBeCloseTo(11.92, 9);
    expect(events).toEqual(["started 1"]);
  });

  it("completes only after its last piece has arrived and every piece has played", async () => {
    const { player, sources, events } = world();
    player.enqueue(piece(1, 0, 960));
    player.enqueue(piece(1, 1, 960));
    await settle();
    sources[0]!.end();
    sources[1]!.end();
    expect(events).toEqual(["started 1"]); // its end has not been announced yet
    player.enqueue(piece(1, 2, 0, true)); // the empty closing piece
    await settle();
    expect(events).toEqual(["started 1", "completed 1"]);
  });

  it("holds the next segment until it has finished", async () => {
    const { player, sources, events } = world();
    player.enqueue(piece(1, 0, 960));
    player.enqueue(piece(1, 1, 0, true));
    player.enqueue({ ...piece(2, 0, 500), last: true });
    await settle();
    expect(events).toEqual(["started 1"]);
    expect(player.queued).toBe(1);
    sources[0]!.end();
    await settle();
    expect(events).toEqual(["started 1", "completed 1", "started 2"]);
  });

  it("a stop silences every piece already scheduled", async () => {
    const { player, sources, events } = world();
    player.enqueue(piece(1, 0, 960));
    player.enqueue(piece(1, 1, 960));
    await settle();
    player.stop("the owner spoke");
    expect(sources.map((s) => s.stops)).toEqual([1, 1]);
    expect(player.audible).toBe(false);
    expect(events).toEqual(["started 1", "interrupted 1"]);
  });

  it("a whole segment still plays as before", async () => {
    const { player, sources, events } = world();
    player.enqueue({ messageId: "m", segmentIndex: 1, text: "Whole.", audio: new ArrayBuffer(700) });
    await settle();
    sources[0]!.end();
    await settle();
    expect(events).toEqual(["started 1", "completed 1"]);
  });
});

describe("the stall bound follows a streamed segment's real length", () => {
  it("extends the expected end as pieces arrive, before and after it starts", () => {
    const clock = { now: 0 };
    const presentation = new SpokenPresentation(() => undefined, () => clock.now);
    presentation.turn("h", 1);
    presentation.answered("h", "m");
    const key = presentation.offered("m") as number;
    presentation.extend(key, 1, 960); // arrived before playback began
    presentation.started(key, 1, "A long first sentence. ", 960);
    presentation.extend(key, 1, 960);
    const segment = presentation.byKey(key)!.segments[0]!;
    expect(segment.expectedEndAt).toBe(2_880);
  });
});
