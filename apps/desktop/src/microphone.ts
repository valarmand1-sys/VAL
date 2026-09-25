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
 * Where the processor module is served from. **Same-origin, and deliberately not a
 * `blob:` URL.**
 *
 * The processor itself lives in `public/pcm-worklet.js`, which the application
 * serves at this path. It was first built as a string and loaded from a blob, and
 * the desktop's Content Security Policy refused it — `default-src 'self'` with no
 * `script-src`, so a blob-backed script has no source that permits it. That refusal
 * was the policy working, and the fix is to stop needing the exception rather than
 * to grant one: served from the app's own origin, the module satisfies
 * `default-src 'self'` and **no policy change was required**.
 *
 * Permitting blob scripts would have widened what *any* injected string in this
 * window could execute, which is a real loosening for a purely cosmetic benefit.
 */
export const WORKLET_MODULE_URL = "/pcm-worklet.js";

/** What the capture layer needs from the platform, so a test can supply fakes. */
export interface CapturePlatform {
  getUserMedia(constraints: MediaStreamConstraints): Promise<MediaStream>;
  createContext(): AudioContext;
  /** Where the processor module is fetched from. A same-origin path, never a blob. */
  workletModuleUrl: string;
}

export const browserPlatform: CapturePlatform = {
  getUserMedia: (constraints) => navigator.mediaDevices.getUserMedia(constraints),
  createContext: () => new AudioContext(),
  workletModuleUrl: WORKLET_MODULE_URL,
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

/**
 * What the platform actually applied to the track — owner acceptance, §25.
 *
 * The constraints below *request* echo cancellation. Whether WKWebView granted it is
 * a different fact, and the acceptance question "did Val's own voice reach the
 * microphone?" cannot be reasoned about without it. `getSettings()` is the platform's
 * own answer where it exposes one; a platform that says nothing yields `null`, which
 * is recorded as not stated rather than as false.
 */
export interface AppliedCaptureSettings {
  /** A boolean where the platform states one; some report a mode string instead. */
  echoCancellation: boolean | string | null;
  noiseSuppression: boolean | string | null;
  autoGainControl: boolean | string | null;
  sampleRate: number | null;
  channelCount: number | null;
}

export function appliedSettings(stream: MediaStream): AppliedCaptureSettings {
  // **A diagnostic may never take the microphone down.** Everything here is
  // best-effort: a platform that does not implement `getAudioTracks` or
  // `getSettings`, or throws from either, yields nulls — recorded as "not stated"
  // rather than as false, and never as a failure to capture.
  let settings: MediaTrackSettings = {};
  try {
    const tracks = typeof stream.getAudioTracks === "function" ? stream.getAudioTracks() : [];
    const [track] = tracks;
    if (track !== undefined && typeof track.getSettings === "function") {
      settings = track.getSettings();
    }
  } catch {
    settings = {};
  }
  const stated = <T,>(value: T | undefined): T | null => (value === undefined ? null : value);
  return {
    echoCancellation: stated(settings.echoCancellation),
    noiseSuppression: stated(settings.noiseSuppression),
    autoGainControl: stated(settings.autoGainControl),
    sampleRate: stated(settings.sampleRate),
    channelCount: stated(settings.channelCount),
  };
}

export interface MicrophoneObserver {
  /** One bounded chunk of 16 kHz mono int16 PCM, on its way to the service. */
  onChunk(pcm: ArrayBuffer): void;
  /** The hardware is really capturing now, with what the platform actually applied. */
  onLive(applied: AppliedCaptureSettings): void;
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
      // **Owned the instant it exists.** Owner acceptance, 24 September 2026: the
      // worklet module load below failed under the desktop's CSP *after* the device
      // had been granted, and because the stream was still only a local variable at
      // that point, the release path in `catch` had nothing to stop — leaving a live
      // track held by nothing, to be collected whenever the engine felt like it.
      // §1.3 says a failure moves toward released, and "eventually, probably" is not
      // that. Each resource is therefore assigned to the object as soon as it is
      // created, so `release()` can take down whatever exists no matter where the
      // failure happens.
      this.stream = await this.platform.getUserMedia(CAPTURE_CONSTRAINTS);
      const context = this.platform.createContext();
      this.context = context;
      // Fetched from the application's own origin, which is what `default-src
      // 'self'` permits. A `blob:` URL here is refused by the desktop's CSP, and
      // that refusal is the policy working.
      await context.audioWorklet.addModule(this.platform.workletModuleUrl);
      const worklet = new AudioWorkletNode(context, "val-pcm", {
        numberOfInputs: 1,
        numberOfOutputs: 0,
        processorOptions: { targetRate: TARGET_SAMPLE_RATE, chunkSamples: CHUNK_SAMPLES },
      });
      this.worklet = worklet;
      worklet.port.onmessage = (event: MessageEvent) => {
        // Dropped the moment the owner mutes: the check is here as well as in the
        // release path, because a chunk already in flight must not be forwarded.
        if (!this.accepting) return;
        this.observer.onChunk(event.data as ArrayBuffer);
      };
      const source = context.createMediaStreamSource(this.stream);
      this.source = source;
      source.connect(worklet);
      this.accepting = true;

      if (!this.live) {
        // The platform handed back a stream with no live track. Fail closed rather
        // than reporting Listening over a device that is not capturing.
        this.release();
        this.observer.onFailure("the microphone stream carried no live track");
        return;
      }
      this.observer.onLive(appliedSettings(this.stream));
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
    this.observer.onReleased();
  }
}
