// Physical playback and barge-in — owner execution order, 24 September 2026, §12, §19;
// rebuilt 26 September 2026 (audio regression §8) around the real playback worklet.
//
// The assertions: pieces of one segment reach the device as ONE continuous signal; a
// segment starts once and completes after its last piece; the next segment follows
// without a gap; a late piece is silence and an underrun, never a click; stopping
// silences the device and discards everything queued; and a stopped or failed piece is
// reported as what it was, never as a completion.

import { beforeEach, describe, expect, it } from "vitest";

import {
  decodeSegmentAudio,
  decodeWav,
  SpeechPlayer,
  type SegmentAudio,
  type SpeakerObserver,
} from "./speaker";
import { PlaybackHarness, ramp, wavBase64, wavBytes } from "./testPlayback";

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
      onStarted: (item) => reported.started.push(item.segmentIndex),
      onCompleted: (item) => reported.completed.push(item.segmentIndex),
      onInterrupted: (item, reason) => reported.interrupted.push([item.segmentIndex, reason]),
      onFailed: (item, detail) => reported.failed.push([item.segmentIndex, detail]),
    },
  };
}

function piece(index: number, chunk: number, samples: number[], last: boolean): SegmentAudio {
  return { messageId: "m", segmentIndex: index, text: `segment ${index}`, audio: wavBytes(samples), chunk, last };
}

async function settle(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

let harness: PlaybackHarness;
let watch: ReturnType<typeof observer>;
let player: SpeechPlayer;

beforeEach(() => {
  harness = new PlaybackHarness(24000);
  watch = observer();
  player = new SpeechPlayer(watch.hooks, harness.platform());
});

describe("streamed pieces are one signal", () => {
  it("joins a segment's pieces sample to sample, starts it once and completes it after the last", async () => {
    const first = ramp(480, -0.5, 0.5);
    const second = ramp(480, 0.5, -0.5);
    player.enqueue(piece(1, 0, first, false));
    player.enqueue(piece(1, 1, second, false));
    player.enqueue(piece(1, 2, [], true));
    await settle();
    expect(harness.requestedRate).toBe(24000);
    harness.pump(960);
    // The device saw the two ramps back to back, to 16-bit precision.
    const expected = [...first, ...second];
    for (let i = 0; i < 960; i += 1) expect(harness.output[i]).toBeCloseTo(expected[i]!, 3);
    expect(watch.reported.started).toEqual([1]);
    expect(watch.reported.completed).toEqual([1]);
    expect(player.underrunFrames).toBe(0);
  });

  it("plays the next segment right after the previous one, in order", async () => {
    player.enqueue(piece(1, 0, ramp(240, 0.2, 0.2), true));
    player.enqueue(piece(2, 0, ramp(240, -0.2, -0.2), true));
    await settle();
    harness.pump(480);
    expect(harness.output[239]).toBeCloseTo(0.2, 3);
    expect(harness.output[240]).toBeCloseTo(-0.2, 3);
    expect(watch.reported.started).toEqual([1, 2]);
    expect(watch.reported.completed).toEqual([1, 2]);
  });

  it("writes silence and counts an underrun when the next piece is late — never a click", async () => {
    player.enqueue(piece(1, 0, ramp(240, 0.3, 0.3), false));
    await settle();
    harness.pump(360); // 120 frames past the end of the piece
    expect(harness.output.slice(240, 360).every((v) => v === 0)).toBe(true);
    player.enqueue(piece(1, 1, ramp(240, 0.3, 0.3), true));
    await settle();
    harness.pump(240);
    expect(player.underrunFrames).toBe(120);
    expect(watch.reported.completed).toEqual([1]);
  });

  it("resamples continuously when the context runs at another rate", async () => {
    harness = new PlaybackHarness(48000);
    player = new SpeechPlayer(watch.hooks, harness.platform());
    player.enqueue(piece(1, 0, ramp(240, 0, 0.5), false));
    player.enqueue(piece(1, 1, ramp(240, 0.5, 1.0), true));
    await settle();
    harness.pump(960);
    // Twice as many output samples, and no jump at the boundary between pieces.
    const steps = harness.output.slice(1, 960).map((v, i) => Math.abs(v - harness.output[i]!));
    expect(Math.max(...steps)).toBeLessThan(0.002);
    expect(harness.output[959]).toBeCloseTo(1.0, 2);
  });
});

describe("barge-in", () => {
  it("silences the device at once and discards what was queued", async () => {
    player.enqueue(piece(1, 0, ramp(4800, 0.4, 0.4), true));
    player.enqueue(piece(2, 0, ramp(4800, 0.4, 0.4), true));
    await settle();
    harness.pump(128);
    expect(player.audible).toBe(true);
    player.stop("the owner spoke");
    const after = harness.pump(4800);
    expect(after.every((v) => v === 0)).toBe(true);
    expect(player.audible).toBe(false);
    expect(watch.reported.interrupted).toEqual([[1, "the owner spoke"]]);
    expect(watch.reported.completed).toEqual([]);
    expect(watch.reported.started).toEqual([1]);
  });

  it("plays nothing more after a stop", async () => {
    player.enqueue(piece(1, 0, ramp(240, 0.4, 0.4), true));
    await settle();
    player.stop("the owner spoke");
    player.enqueue(piece(2, 0, ramp(240, 0.4, 0.4), true));
    await settle();
    expect(harness.pump(480).every((v) => v === 0)).toBe(true);
    expect(watch.reported.started).toEqual([]);
  });
});

describe("what is reported is what happened", () => {
  it("reports a piece that is not audio as failed rather than played", async () => {
    player.enqueue({ messageId: "m", segmentIndex: 1, text: "x", audio: new ArrayBuffer(16) });
    await settle();
    expect(watch.reported.failed).toHaveLength(1);
    expect(watch.reported.started).toEqual([]);
  });

  it("decodes the service's transport into the WAV it carried", () => {
    const samples = ramp(100, -0.25, 0.25);
    const decoded = decodeWav(decodeSegmentAudio(wavBase64(samples)));
    expect(decoded.sampleRate).toBe(24000);
    expect(decoded.samples).toHaveLength(100);
    expect(decoded.samples[99]).toBeCloseTo(0.25, 3);
  });
});
