// Real microphone capture — owner execution order, 24 September 2026, §3, §6, §10.
//
// **The only place in Val that calls `getUserMedia`.** It is reached from the
// desktop's owner-facing Voice controls and from nothing else: not from Core, not
// from the model, not from a tool, not from a timer, not from an error handler. A
// structural test asserts there is no second call site.
//
// Two rules shape everything here.
//
// **Mute releases the device.** Not `track.enabled = false`, not a stream kept open
// with its samples discarded, not a "warm" microphone held for a faster unmute.
// Every track is stopped, every node disconnected, every reference dropped — so the
// macOS orange indicator goes dark, which is the owner's ground truth and cannot be
// faked by an icon in this application (§9.1).
//
// **Nothing accumulates.** Audio exists as bounded chunks on their way to the
// loopback service and nowhere else: no MediaRecorder, no Blob, no temporary file,
// no session recording in memory. A chunk is released as soon as it has been handed
// over.

/** The recognizer's contract: 16 kHz, mono, signed 16-bit little-endian PCM. */
export const TARGET_SAMPLE_RATE = 16_000;

/** How much audio one chunk carries. 20 ms at 16 kHz, matching the service's tests. */
export const CHUNK_SAMPLES = 320;

/**
 * The worklet, as source. It runs on the audio thread, converts to the recognizer's
 * format, and posts bounded chunks. It keeps one small buffer and no history.
 *
 * Resampling is a plain decimating average, which is enough for speech at these
 * rates and costs nothing: the alternative is a filter design exercise for audio
 * that whisper.cpp then resamples internally anyway.
 */
export const PCM_WORKLET_SOURCE = `
class ValPcmProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const settings = (options && options.processorOptions) || {};
    this.targetRate = settings.targetRate || ${TARGET_SAMPLE_RATE};
    this.chunkSamples = settings.chunkSamples || ${CHUNK_SAMPLES};
    this.ratio = sampleRate / this.targetRate;
    this.pending = new Float32Array(this.chunkSamples);
    this.held = 0;
    this.position = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel) return true;
    // Down-mix to mono by averaging whatever channels arrived.
    const frames = channel.length;
    for (let index = 0; index < frames; index += 1) {
      let sum = 0;
      for (let c = 0; c < input.length; c += 1) sum += input[c][index] || 0;
      const mono = sum / input.length;
      this.position += 1;
      if (this.position < this.ratio) continue;
      this.position -= this.ratio;
      this.pending[this.held] = mono;
      this.held += 1;
      if (this.held === this.chunkSamples) {
        const out = new Int16Array(this.chunkSamples);
        for (let s = 0; s < this.chunkSamples; s += 1) {
          const clamped = Math.max(-1, Math.min(1, this.pending[s]));
          out[s] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
        }
        this.port.postMessage(out.buffer, [out.buffer]);
        this.held = 0;
      }
    }
    return true;
  }
}
registerProcessor('val-pcm', ValPcmProcessor);
`;

/** What the capture layer needs from the platform, so a test can supply fakes. */
export interface CapturePlatform {
  getUserMedia(constraints: MediaStreamConstraints): Promise<MediaStream>;
  createContext(): AudioContext;
  createModuleUrl(source: string): string;
  revokeModuleUrl(url: string): void;
}

export const browserPlatform: CapturePlatform = {
  getUserMedia: (constraints) => navigator.mediaDevices.getUserMedia(constraints),
  createContext: () => new AudioContext(),
  createModuleUrl: (source) => URL.createObjectURL(new Blob([source], { type: "text/javascript" })),
  revokeModuleUrl: (url) => URL.revokeObjectURL(url),
};

/**
 * The capture constraints. `echoCancellation` is requested (§13) so Val's own
 * speaker output is not accepted as owner speech — the local WebRTC facility, not a
 * service, and not a substitute for the physical acceptance the order requires.
 *
 * Muting the microphone whenever Val speaks would destroy barge-in, so it is not
 * done: the whole point is that he can interrupt her.
 */
export const CAPTURE_CONSTRAINTS: MediaStreamConstraints = {
  audio: {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
    channelCount: 1,
  },
  video: false,
};

export interface MicrophoneObserver {
  /** One bounded chunk of 16 kHz mono int16 PCM, on its way to the service. */
  onChunk(pcm: ArrayBuffer): void;
  /** The hardware is really capturing now. */
  onLive(): void;
  /** The hardware is really released now. */
  onReleased(): void;
  onFailure(detail: string): void;
}

/**
 * One microphone, held only while the owner wants it held.
 *
 * `open` is called from an owner gesture handler. `release` is called from an owner
 * gesture, from Voice off, from a conversation change, from suspend, from quit and
 * from any failure — and it is idempotent, because a release that cannot be called
 * twice is a release that will one day not be called at all.
 */
export class MicrophoneCapture {
  private stream: MediaStream | null = null;
  private context: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private worklet: AudioWorkletNode | null = null;
  private moduleUrl: string | null = null;
  /** Set false before the release path runs, so no sample can enter after mute. */
  private accepting = false;

  constructor(
    private readonly observer: MicrophoneObserver,
    private readonly platform: CapturePlatform = browserPlatform,
  ) {}

  get live(): boolean {
    if (this.stream === null) return false;
    return this.stream.getTracks().some((track) => track.readyState === "live");
  }

  /** Acquire the device. Only ever called from an explicit owner gesture. */
  async open(): Promise<void> {
    if (this.live) return;
    try {
      const stream = await this.platform.getUserMedia(CAPTURE_CONSTRAINTS);
      const context = this.platform.createContext();
      const url = this.platform.createModuleUrl(PCM_WORKLET_SOURCE);
      await context.audioWorklet.addModule(url);
      const worklet = new AudioWorkletNode(context, "val-pcm", {
        numberOfInputs: 1,
        numberOfOutputs: 0,
        processorOptions: { targetRate: TARGET_SAMPLE_RATE, chunkSamples: CHUNK_SAMPLES },
      });
      worklet.port.onmessage = (event: MessageEvent) => {
        // Dropped the moment the owner mutes: the check is here as well as in the
        // release path, because a chunk already in flight must not be forwarded.
        if (!this.accepting) return;
        this.observer.onChunk(event.data as ArrayBuffer);
      };
      const source = context.createMediaStreamSource(stream);
      source.connect(worklet);

      this.stream = stream;
      this.context = context;
      this.source = source;
      this.worklet = worklet;
      this.moduleUrl = url;
      this.accepting = true;

      if (!this.live) {
        // The platform handed back a stream with no live track. Fail closed rather
        // than reporting Listening over a device that is not capturing.
        this.release();
        this.observer.onFailure("the microphone stream carried no live track");
        return;
      }
      this.observer.onLive();
    } catch (failure) {
      this.release();
      this.observer.onFailure(
        failure instanceof Error ? failure.message : "the microphone could not be opened",
      );
    }
  }

  /**
   * Release the device completely. **This is what mute means** (§6.1).
   *
   * Order matters: stop accepting samples first, then take the hardware down, so
   * nothing captured during the teardown is forwarded.
   */
  release(): void {
    this.accepting = false;

    if (this.worklet !== null) {
      this.worklet.port.onmessage = null;
      try {
        this.worklet.disconnect();
      } catch {
        // A node already disconnected is the state we wanted.
      }
      this.worklet = null;
    }
    if (this.source !== null) {
      try {
        this.source.disconnect();
      } catch {
        // As above.
      }
      this.source = null;
    }
    if (this.stream !== null) {
      // Every track, not the first: a device that hands back two must not leave
      // one of them capturing.
      for (const track of this.stream.getTracks()) track.stop();
      this.stream = null;
    }
    if (this.context !== null) {
      void this.context.close().catch(() => undefined);
      this.context = null;
    }
    if (this.moduleUrl !== null) {
      this.platform.revokeModuleUrl(this.moduleUrl);
      this.moduleUrl = null;
    }
    this.observer.onReleased();
  }
}
