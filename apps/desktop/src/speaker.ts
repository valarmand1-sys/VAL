// Physical playback — owner execution order, 24 September 2026, §11, §11.1, §12;
// rebuilt 26 September 2026 for the audio regression (§8 of that day's order).
//
// Val's synthesised speech becomes sound in the room here, and nowhere else. The
// audio arrives over the existing loopback service as WAV — a whole segment, or a
// segment in ~1-second pieces — is decoded here, handed to one playback worklet as a
// single continuous stream of samples, and released.
//
// **One stream, not one buffer per piece.** The previous player decoded each piece
// with `decodeAudioData` and scheduled it as its own source node. `decodeAudioData`
// resamples each piece independently to the context's rate, and separately scheduled
// nodes meet at a boundary the engine did not design for, so every seam between
// pieces was a resampler restart and a scheduling edge — audible as a click. Now the
// pieces of a segment are written to the device sample after sample by
// `pcm-playback-worklet.js`, and the context is asked for the speech's own sample
// rate so that, where the platform grants it, nothing is resampled at all. Where it
// is not, the worklet's own resampler carries its state across pieces.
//
// Three rules, unchanged.
//
// **Only under an owner-started Voice session.** This player is created when Voice
// goes on and destroyed when Voice goes off; with Voice off no sink exists, so no
// generated speech can be played (§1.2).
//
// **Barge-in stops the sound, not just the queue.** `stop` silences the worklet —
// which discards everything it holds — and disconnects it, so nothing keeps
// sounding while the queue is cleared (§12).
//
// **Playback started is reported, never assumed.** The service cannot see an output
// device. What it records is what this module says happened, and this module says it
// when the worklet has written the segment's first sample to the output — sound at
// the device, not an intention to schedule (§11.1).

export interface SpeakerPlatform {
  /**
   * An output context, asked for the speech's sample rate. A platform may ignore the
   * request; the worklet resamples if the context runs at another rate.
   */
  createContext(sampleRate: number): AudioContext;
  workletModuleUrl: string;
}

export const PLAYBACK_WORKLET_URL = "/pcm-playback-worklet.js";

export const browserSpeaker: SpeakerPlatform = {
  createContext: (sampleRate) => {
    try {
      return new AudioContext({ sampleRate });
    } catch {
      return new AudioContext();
    }
  },
  workletModuleUrl: PLAYBACK_WORKLET_URL,
};

export interface SegmentAudio {
  messageId: string;
  segmentIndex: number;
  text: string;
  audio: ArrayBuffer;
  /** Which of her answers this segment belongs to, in the window's own terms. */
  answerKey?: number;
  /** The audio's length, as the service stated it. */
  durationSeconds?: number;
  /**
   * Which piece of the segment this is (from 0) and whether it ends the segment. A
   * segment voiced whole is one piece that ends it; a streamed one is several, then
   * an empty piece that ends it. Absent means whole.
   */
  chunk?: number;
  last?: boolean;
}

export interface SpeakerObserver {
  /** The segment's first sample has been written to the output device. Sound in the room. */
  onStarted(segment: SegmentAudio): void;
  onCompleted(segment: SegmentAudio): void;
  onInterrupted(segment: SegmentAudio, reason: string): void;
  onFailed(segment: SegmentAudio, detail: string): void;
}

/** A WAV file's samples, as the worklet wants them. */
export interface DecodedWav {
  sampleRate: number;
  samples: Float32Array;
}

/**
 * Decode a WAV file: PCM 16-bit, or 32-bit float, mono (channels are averaged).
 * Done here, from the bytes, rather than through `decodeAudioData`: a decode that
 * resamples each piece on its own is exactly what produced the seams.
 */
export function decodeWav(buffer: ArrayBuffer): DecodedWav {
  const view = new DataView(buffer);
  const tag = (at: number) => String.fromCharCode(...new Uint8Array(buffer, at, 4));
  if (buffer.byteLength < 12 || tag(0) !== "RIFF" || tag(8) !== "WAVE") {
    throw new Error("not a WAV file");
  }
  let at = 12;
  let format: { channels: number; rate: number; bits: number; float: boolean } | null = null;
  while (at + 8 <= buffer.byteLength) {
    const id = tag(at);
    const size = view.getUint32(at + 4, true);
    const body = at + 8;
    if (id === "fmt ") {
      const code = view.getUint16(body, true);
      format = {
        channels: view.getUint16(body + 2, true),
        rate: view.getUint32(body + 4, true),
        bits: view.getUint16(body + 14, true),
        float: code === 3,
      };
    } else if (id === "data") {
      if (format === null) throw new Error("WAV data before its format");
      const frameBytes = (format.bits / 8) * format.channels;
      const frames = Math.floor(Math.min(size, buffer.byteLength - body) / frameBytes);
      const samples = new Float32Array(frames);
      for (let frame = 0; frame < frames; frame += 1) {
        let sum = 0;
        for (let channel = 0; channel < format.channels; channel += 1) {
          const offset = body + frame * frameBytes + channel * (format.bits / 8);
          if (format.float && format.bits === 32) sum += view.getFloat32(offset, true);
          else if (format.bits === 16) sum += view.getInt16(offset, true) / 32768;
          else throw new Error(`unsupported WAV sample format (${format.bits}-bit)`);
        }
        samples[frame] = sum / format.channels;
      }
      return { sampleRate: format.rate, samples };
    }
    at = body + size + (size % 2);
  }
  throw new Error("WAV file has no data");
}

interface Tracked {
  segment: SegmentAudio;
  started: boolean;
  completed: boolean;
}

/** One answer's worth of speech, played in order, stoppable at any instant. */
export class SpeechPlayer {
  private context: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;
  private ready: Promise<boolean> | null = null;
  private sourceRate: number | null = null;
  private readonly tracked = new Map<string, Tracked>();
  /** Pieces waiting for the worklet to be ready, in arrival order. */
  private chain: Promise<void> = Promise.resolve();
  private stopped = false;
  /** Frames of silence the worklet had to write while waiting for a piece. */
  underrunFrames = 0;

  constructor(
    private readonly observer: SpeakerObserver,
    private readonly platform: SpeakerPlatform = browserSpeaker,
  ) {}

  /** Queue a segment, or a piece of one, collected from the service. Service order. */
  enqueue(piece: SegmentAudio): void {
    if (this.stopped) return;
    this.chain = this.chain.then(() => this.accept(piece)).catch(() => undefined);
  }

  get queued(): number {
    return 0; // the worklet holds the queue; nothing waits on this side once ready
  }

  get audible(): boolean {
    for (const item of this.tracked.values()) if (item.started && !item.completed) return true;
    return false;
  }

  private key(piece: SegmentAudio): string {
    return `${piece.answerKey ?? "-"}:${piece.segmentIndex}`;
  }

  private async accept(piece: SegmentAudio): Promise<void> {
    if (this.stopped) return;
    const key = this.key(piece);
    const opening = (piece.chunk ?? 0) === 0;
    if (opening) this.tracked.set(key, { segment: piece, started: false, completed: false });
    const known = this.tracked.get(key);
    if (known === undefined) return; // a later piece of a segment never opened here
    let decoded: DecodedWav | null = null;
    if (piece.audio.byteLength > 0) {
      try {
        decoded = decodeWav(piece.audio);
      } catch (failure) {
        this.observer.onFailed(
          known.segment,
          failure instanceof Error ? failure.message : "the audio could not be decoded",
        );
        this.tracked.delete(key);
        return;
      }
    }
    if (this.ready === null) this.ready = this.prepare(decoded?.sampleRate ?? 24000);
    if (!(await this.ready)) {
      this.observer.onFailed(known.segment, "the playback worklet could not be started");
      this.tracked.delete(key);
      return;
    }
    if (this.stopped || this.node === null) return;
    if (decoded !== null && this.sourceRate !== null && decoded.sampleRate !== this.sourceRate) {
      this.observer.onFailed(known.segment, "a piece arrived at another sample rate");
      this.tracked.delete(key);
      return;
    }
    const samples = decoded === null ? new Float32Array(0) : decoded.samples;
    this.node.port.postMessage(
      { type: "piece", key, samples: samples.buffer, last: piece.last ?? true },
      [samples.buffer],
    );
  }

  private async prepare(sampleRate: number): Promise<boolean> {
    try {
      const context = this.platform.createContext(sampleRate);
      this.context = context;
      this.sourceRate = sampleRate;
      await context.audioWorklet.addModule(this.platform.workletModuleUrl);
      if (this.stopped) return false;
      const node = new AudioWorkletNode(context, "val-playback", {
        numberOfInputs: 0,
        numberOfOutputs: 1,
        outputChannelCount: [1],
        processorOptions: { sourceRate: sampleRate },
      });
      node.port.onmessage = (event: MessageEvent) => this.receive(event.data as WorkletEvent);
      node.connect(context.destination);
      this.node = node;
      return true;
    } catch {
      return false;
    }
  }

  private receive(event: WorkletEvent): void {
    if (this.stopped) return;
    const item = event.key === undefined ? undefined : this.tracked.get(event.key);
    if (event.type === "started" && item !== undefined && !item.started) {
      item.started = true;
      this.observer.onStarted(item.segment);
    } else if (event.type === "completed" && item !== undefined && !item.completed) {
      item.completed = true;
      this.observer.onCompleted(item.segment);
    } else if (event.type === "underrun") {
      this.underrunFrames += event.frames ?? 0;
    }
  }

  /**
   * Stop the sound now and discard what was queued behind it.
   *
   * The order is the contract: the worklet is silenced first — it drops every piece it
   * holds and writes silence — then disconnected, so nothing keeps sounding while the
   * queue is cleared.
   */
  stop(reason: string): void {
    if (this.stopped) return;
    this.stopped = true;
    const node = this.node;
    if (node !== null) {
      try {
        node.port.postMessage({ type: "stop" });
        node.disconnect();
      } catch {
        // A node already gone is the state we wanted.
      }
      this.node = null;
    }
    for (const item of this.tracked.values()) {
      if (item.started && !item.completed) {
        item.completed = true;
        this.observer.onInterrupted(item.segment, reason);
      }
    }
  }

  /** Release the audio device. Called when Voice goes off. */
  close(): void {
    this.stop("voice mode ended");
    if (this.context !== null) {
      void this.context.close().catch(() => undefined);
      this.context = null;
    }
  }
}

interface WorkletEvent {
  type: "started" | "completed" | "underrun" | "stopped";
  key?: string;
  frame?: number;
  frames?: number;
}

/** Decode the service's base64 transport into bytes to hand to the player. */
export function decodeSegmentAudio(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes.buffer;
}
