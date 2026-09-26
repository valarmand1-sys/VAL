// Physical playback — owner execution order, 24 September 2026, §11, §11.1, §12.
//
// Val's synthesised speech becomes sound in the room here, and nowhere else. The
// audio arrives over the existing loopback service, is decoded, is scheduled on the
// Mac's default output device, and is then released.
//
// Three rules.
//
// **Only under an owner-started Voice session.** This player is created when Voice
// goes on and destroyed when Voice goes off; with Voice off no sink exists, so no
// generated speech can be played (§1.2).
//
// **Barge-in stops the sound, not just the queue.** `stop` halts the source that is
// playing *and* discards everything queued behind it, in that order, because a
// queue emptied while a buffer plays on is not an interruption (§12).
//
// **Playback started is reported, never assumed.** The service cannot see an output
// device. What it records is what this module says happened, and this module says it
// when the buffer is actually scheduled — which is why `onStarted` fires from the
// scheduling call and not from the decision to schedule (§11.1).

export interface SpeakerPlatform {
  createContext(): AudioContext;
}

export const browserSpeaker: SpeakerPlatform = {
  createContext: () => new AudioContext(),
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
  /** The segment is actually scheduled on the output device. Sound in the room. */
  onStarted(segment: SegmentAudio): void;
  onCompleted(segment: SegmentAudio): void;
  onInterrupted(segment: SegmentAudio, reason: string): void;
  onFailed(segment: SegmentAudio, detail: string): void;
}

/** One answer's worth of speech, played in order, stoppable at any instant. */
export class SpeechPlayer {
  private context: AudioContext | null = null;
  /** Every buffer scheduled and not yet ended: all of them stop together. */
  private sources = new Set<AudioBufferSourceNode>();
  /** The segment sounding now, and where its next piece joins it on the audio clock. */
  private active: {
    segment: SegmentAudio;
    joinAt: number;
    outstanding: number;
    ended: boolean;
    finished: Promise<void>;
    finish: () => void;
  } | null = null;
  private queue: SegmentAudio[] = [];
  private draining = false;
  private stopped = false;

  constructor(
    private readonly observer: SpeakerObserver,
    private readonly platform: SpeakerPlatform = browserSpeaker,
  ) {}

  /** Queue a segment, or a piece of one, collected from the service. Service order. */
  enqueue(segment: SegmentAudio): void {
    if (this.stopped) return;
    this.queue.push(segment);
    void this.drain();
  }

  get queued(): number {
    return this.queue.length;
  }

  get audible(): boolean {
    return this.sources.size > 0;
  }

  private async drain(): Promise<void> {
    if (this.draining || this.stopped) return;
    this.draining = true;
    try {
      while (!this.stopped) {
        const piece = this.queue[0];
        if (piece === undefined) break;
        // A new segment stays queued — where a stop discards it — until the one
        // sounding now has finished.
        if ((piece.chunk ?? 0) === 0 && this.active !== null) {
          await this.active.finished;
          continue;
        }
        this.queue.shift();
        await this.accept(piece);
      }
    } finally {
      this.draining = false;
    }
  }

  /**
   * One piece. The first piece of a segment waits for the segment before it to
   * finish, and starts it; every later piece is scheduled on the audio clock to
   * begin exactly where the one before it ends (26 September 2026: streamed
   * speech), so a sentence arriving in pieces plays without a seam of silence.
   */
  private async accept(piece: SegmentAudio): Promise<void> {
    const opening = (piece.chunk ?? 0) === 0;
    if (this.stopped) return;
    const closes = piece.last ?? true;
    if (piece.audio.byteLength === 0) {
      // The end of a streamed segment: nothing to play, only its close.
      if (this.active !== null && !opening) {
        this.active.ended = true;
        this.settle();
      }
      return;
    }
    if (this.context === null) this.context = this.platform.createContext();
    const context = this.context;
    let buffer: AudioBuffer;
    try {
      // `decodeAudioData` detaches the ArrayBuffer, which is the release: after
      // this the bytes we were handed are gone from this side too.
      buffer = await context.decodeAudioData(piece.audio);
    } catch (failure) {
      this.observer.onFailed(
        piece,
        failure instanceof Error ? failure.message : "the audio could not be decoded",
      );
      return;
    }
    if (this.stopped) return;
    if (opening) {
      let finish: () => void = () => undefined;
      const finished = new Promise<void>((resolve) => {
        finish = resolve;
      });
      this.active = { segment: piece, joinAt: 0, outstanding: 0, ended: false, finished, finish };
    }
    const active = this.active;
    if (active === null) return; // a later piece of a segment already stopped
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    const now = typeof context.currentTime === "number" ? context.currentTime : 0;
    const at = Math.max(now, active.joinAt);
    active.joinAt = at + (typeof buffer.duration === "number" ? buffer.duration : 0);
    active.outstanding += 1;
    if (closes) active.ended = true;
    this.sources.add(source);
    source.onended = () => {
      if (!this.sources.delete(source)) return;
      active.outstanding -= 1;
      this.settle();
    };
    source.start(at);
    if (opening) {
      // Reported here, from the scheduling call itself: this is the moment the
      // buffer is on the device, which is the physical boundary §11.1 names.
      this.observer.onStarted(piece);
    }
  }

  /** The active segment is over once its last piece has come and every piece has played. */
  private settle(): void {
    const active = this.active;
    if (active === null || !active.ended || active.outstanding > 0) return;
    this.active = null;
    // An interrupted source also ends; `stopped` tells the two apart, so an
    // interruption is never recorded as a completion.
    if (!this.stopped) this.observer.onCompleted(active.segment);
    active.finish();
  }

  /**
   * Stop the sound now and discard what was queued behind it.
   *
   * The order is the contract: every scheduled source is stopped first, so nothing
   * keeps sounding while the queue is cleared.
   */
  stop(reason: string): void {
    this.stopped = true;
    for (const source of this.sources) {
      try {
        source.onended = null;
        source.stop();
        source.disconnect();
      } catch {
        // A source that had already ended is the state we wanted.
      }
    }
    this.sources.clear();
    const interrupted = this.active;
    this.active = null;
    this.queue = [];
    if (interrupted !== null) {
      this.observer.onInterrupted(interrupted.segment, reason);
      interrupted.finish();
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

/** Decode the service's base64 transport into bytes to hand to the player. */
export function decodeSegmentAudio(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes.buffer;
}
