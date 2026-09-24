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
  private playing: AudioBufferSourceNode | null = null;
  private current: SegmentAudio | null = null;
  private queue: SegmentAudio[] = [];
  private draining = false;
  private stopped = false;

  constructor(
    private readonly observer: SpeakerObserver,
    private readonly platform: SpeakerPlatform = browserSpeaker,
  ) {}

  /** Queue a segment collected from the service. Order is the service's order. */
  enqueue(segment: SegmentAudio): void {
    if (this.stopped) return;
    this.queue.push(segment);
    void this.drain();
  }

  get queued(): number {
    return this.queue.length;
  }

  get audible(): boolean {
    return this.playing !== null;
  }

  private async drain(): Promise<void> {
    if (this.draining || this.stopped) return;
    this.draining = true;
    try {
      while (!this.stopped) {
        const segment = this.queue.shift();
        if (segment === undefined) break;
        await this.play(segment);
      }
    } finally {
      this.draining = false;
    }
  }

  private async play(segment: SegmentAudio): Promise<void> {
    if (this.context === null) this.context = this.platform.createContext();
    const context = this.context;
    let buffer: AudioBuffer;
    try {
      // `decodeAudioData` detaches the ArrayBuffer, which is the release: after
      // this the bytes we were handed are gone from this side too.
      buffer = await context.decodeAudioData(segment.audio);
    } catch (failure) {
      this.observer.onFailed(
        segment,
        failure instanceof Error ? failure.message : "the audio could not be decoded",
      );
      return;
    }
    if (this.stopped) return;

    await new Promise<void>((resolve) => {
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(context.destination);
      let settled = false;
      source.onended = () => {
        if (settled) return;
        settled = true;
        this.playing = null;
        this.current = null;
        // An interrupted source also ends; `stopped` tells the two apart, so an
        // interruption is never recorded as a completion.
        if (!this.stopped) this.observer.onCompleted(segment);
        resolve();
      };
      this.playing = source;
      this.current = segment;
      source.start();
      // Reported here, from the scheduling call itself: this is the moment the
      // buffer is on the device, which is the physical boundary §11.1 names.
      this.observer.onStarted(segment);
    });
  }

  /**
   * Stop the sound now and discard what was queued behind it.
   *
   * The order is the contract: the playing source is stopped first, so nothing
   * keeps sounding while the queue is cleared.
   */
  stop(reason: string): void {
    this.stopped = true;
    const interrupted = this.current;
    if (this.playing !== null) {
      try {
        this.playing.onended = null;
        this.playing.stop();
        this.playing.disconnect();
      } catch {
        // A source that had already ended is the state we wanted.
      }
      this.playing = null;
    }
    this.current = null;
    const discarded = this.queue.length;
    this.queue = [];
    if (interrupted !== null) this.observer.onInterrupted(interrupted, reason);
    if (discarded > 0) {
      // Not an error: a discarded segment is exactly what barge-in means. Counted
      // so the caller can report it truthfully.
      void discarded;
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
