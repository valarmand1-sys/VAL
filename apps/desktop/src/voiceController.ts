// The Voice controller — owner execution order, 24 September 2026, §4, §5, §7, §16.
//
// What the owner's gestures actually do. The state machine in `voiceState` decides;
// this performs. Everything that touches a device or the service happens here, and
// every path into it begins with an owner gesture — a click on the visible control,
// or the global mute shortcut while a session is already active.
//
// The three rules this file exists to make true:
//
// **Only the owner starts a microphone.** `start` is called from a click handler and
// from nowhere else. There is no timer, no wake word, no resume, no retry that
// reacquires a device, and no path from a failure back to capture.
//
// **The indicators report what happened, not what was asked.** Every state change
// here is driven by an observation — the capture layer saying the device is live or
// released — rather than by the request that preceded it (§9).
//
// **Voice off releases everything.** Microphone, playback, service session, global
// shortcut. In that order, and idempotently.

import type { PlaybackState, SpokenAudioView, VoiceSessionView } from "./api";
import { api, describeFailure } from "./api";
import { MicrophoneCapture, type CapturePlatform } from "./microphone";
import { SpeechPlayer, decodeSegmentAudio, type SpeakerPlatform, type SegmentAudio } from "./speaker";
import {
  VOICE_OFF,
  type VoiceStatus,
  next,
  stopped,
  withActivity,
  withShortcut,
} from "./voiceState";

/** How often the desktop asks the service what is happening. */
export const POLL_INTERVAL_MS = 120;

/** How often it asks whether a spoken segment is waiting to be played. */
export const SPEECH_POLL_INTERVAL_MS = 80;

export interface VoiceTimings {
  /** Owner's unmute gesture → a live track → the first chunk accepted (§7). */
  unmuteGestureAt: number | null;
  unmuteTrackLiveAt: number | null;
  unmuteFirstChunkAt: number | null;
  /** Owner speech end (the service's final transcript) → first audible speech (§18). */
  speechEndAt: number | null;
  firstAudibleAt: number | null;
  /** Owner barge-in → physical silence (§12). */
  bargeInAt: number | null;
  silenceAt: number | null;
}

export const NO_TIMINGS: VoiceTimings = {
  unmuteGestureAt: null,
  unmuteTrackLiveAt: null,
  unmuteFirstChunkAt: null,
  speechEndAt: null,
  firstAudibleAt: null,
  bargeInAt: null,
  silenceAt: null,
};

export interface VoiceControllerHooks {
  onStatus(status: VoiceStatus): void;
  onSession(view: VoiceSessionView | null): void;
  onTimings(timings: VoiceTimings): void;
  /** A settled turn the desktop should show in the conversation. */
  onTurnSettled(view: VoiceSessionView): void;
}

export interface VoiceControllerOptions {
  hooks: VoiceControllerHooks;
  capture?: CapturePlatform;
  speaker?: SpeakerPlatform;
  now?: () => number;
  /** Registers the global mute shortcut while a session is active (§8). */
  registerShortcut?: (toggle: () => void) => Promise<boolean>;
  unregisterShortcut?: () => Promise<void>;
  scheduleInterval?: (callback: () => void, ms: number) => number;
  clearScheduled?: (handle: number) => void;
}

export class VoiceController {
  private status: VoiceStatus = VOICE_OFF;
  private timings: VoiceTimings = { ...NO_TIMINGS };
  private session: string | null = null;
  private view: VoiceSessionView | null = null;
  private microphone: MicrophoneCapture | null = null;
  private player: SpeechPlayer | null = null;
  private pollHandle: number | null = null;
  private speechHandle: number | null = null;
  private lastDeliveredMessage: string | null = null;
  private collecting = false;
  private polling = false;
  private readonly now: () => number;
  private readonly schedule: (callback: () => void, ms: number) => number;
  private readonly unschedule: (handle: number) => void;

  constructor(private readonly options: VoiceControllerOptions) {
    this.now = options.now ?? (() => performance.now());
    this.schedule =
      options.scheduleInterval ??
      ((callback, ms) => globalThis.setInterval(callback, ms) as unknown as number);
    this.unschedule =
      options.clearScheduled ?? ((handle) => globalThis.clearInterval(handle as unknown as number));
  }

  get state(): VoiceStatus {
    return this.status;
  }

  get sessionKey(): string | null {
    return this.session;
  }

  get measured(): VoiceTimings {
    return this.timings;
  }

  // --- owner gestures --------------------------------------------------------------

  /**
   * Voice on. **Called only from the owner's click on the visible control.**
   *
   * The order matters and is the order §5 states: establish the service session
   * first — which makes the conversation local-only for as long as it lasts, before
   * a single sample exists — then acquire the microphone, and only report Listening
   * once the hardware says it is capturing.
   */
  async start(scope: { conversation_id?: string; project?: string; no_project?: boolean }): Promise<void> {
    if (this.status.session !== "off") return;
    this.apply(next(this.status, { kind: "owner_pressed_voice_on" }));
    try {
      const view = await api.openVoiceSession(scope);
      this.session = view.session;
      this.view = view;
      this.options.hooks.onSession(view);
      this.apply(next(this.status, { kind: "session_ready" }));
    } catch (failure) {
      this.apply(
        next(this.status, { kind: "transport_failed", detail: describeFailure(failure) }),
      );
      await this.releaseEverything();
      return;
    }

    this.player = new SpeechPlayer(this.speakerObserver(), this.options.speaker);
    await this.acquireMicrophone();
    if (this.status.session === "off" || this.status.session === "error_safe") return;

    const register = this.options.registerShortcut;
    if (register !== undefined) {
      const registered = await register(() => void this.toggleMute());
      this.apply(withShortcut(this.status, registered));
    }
    this.startPolling();
  }

  /** Voice off. Releases the device, the speakers, the session and the shortcut. */
  async stop(): Promise<void> {
    if (this.status.session === "off") return;
    this.apply(next(this.status, { kind: "owner_pressed_voice_off" }));
    await this.releaseEverything();
  }

  /** The visible mute control, and the global shortcut's mute half. */
  async mute(): Promise<void> {
    if (this.status.session !== "active_mic_live") return;
    // The state moves first so nothing can be forwarded while the device comes
    // down; the capture layer's own `accepting` flag is the second guard.
    this.apply(next(this.status, { kind: "owner_pressed_mute" }));
    this.microphone?.release();
    this.microphone = null;
  }

  /** The visible unmute control, and the global shortcut's unmute half. */
  async unmute(): Promise<void> {
    if (this.status.session !== "active_muted") return;
    this.timings = {
      ...this.timings,
      unmuteGestureAt: this.now(),
      unmuteTrackLiveAt: null,
      unmuteFirstChunkAt: null,
    };
    this.options.hooks.onTimings(this.timings);
    this.apply(next(this.status, { kind: "owner_pressed_unmute" }));
    await this.acquireMicrophone();
  }

  /** What the global shortcut does: mute ↔ unmute, and never start Voice (§8). */
  async toggleMute(): Promise<void> {
    if (this.status.session === "active_mic_live") return this.mute();
    if (this.status.session === "active_muted") return this.unmute();
    // Off, starting, stopping or error: a hard no-op. The shortcut cannot start
    // Voice, and this is the second guard after not registering it at all.
  }

  /** Barge-in: he began speaking while she was. §12's owner-facing boundary. */
  async interruptSpeech(reason = "the owner spoke"): Promise<void> {
    if (this.player === null) return;
    this.timings = { ...this.timings, bargeInAt: this.now(), silenceAt: null };
    this.player.stop(reason);
    this.timings = { ...this.timings, silenceAt: this.now() };
    this.options.hooks.onTimings(this.timings);
    this.player = new SpeechPlayer(this.speakerObserver(), this.options.speaker);
    if (this.session !== null) {
      try {
        await api.interruptVoice(this.session);
      } catch {
        // The physical sound has already stopped, which is the part he notices.
        // A failed report is surfaced by the next poll rather than thrown here.
      }
    }
  }

  // --- lifecycle events that may only fail closed ---------------------------------

  /** A conversation change, a suspend, or a quit. Voice goes off (§16). */
  async releaseForLifecycle(kind: "conversation_changed" | "app_or_machine_suspending"): Promise<void> {
    if (this.status.session === "off") return;
    this.apply(next(this.status, { kind }));
    await this.releaseEverything();
  }

  // --- the machinery ---------------------------------------------------------------

  private async acquireMicrophone(): Promise<void> {
    const capture = new MicrophoneCapture(
      {
        onChunk: (pcm) => {
          if (this.timings.unmuteGestureAt !== null && this.timings.unmuteFirstChunkAt === null) {
            this.timings = { ...this.timings, unmuteFirstChunkAt: this.now() };
            this.options.hooks.onTimings(this.timings);
          }
          void this.forward(pcm);
        },
        onLive: () => {
          if (this.timings.unmuteGestureAt !== null && this.timings.unmuteTrackLiveAt === null) {
            this.timings = { ...this.timings, unmuteTrackLiveAt: this.now() };
            this.options.hooks.onTimings(this.timings);
          }
          this.apply(next(this.status, { kind: "capture_became_live" }));
        },
        onReleased: () => {
          this.apply(next(this.status, { kind: "capture_released" }));
        },
        onFailure: (detail) => {
          // No automatic retry. The owner is told, and the next move is his (§7).
          this.apply(next(this.status, { kind: "capture_failed", detail }));
        },
      },
      this.options.capture,
    );
    this.microphone = capture;
    await capture.open();
  }

  private async forward(pcm: ArrayBuffer): Promise<void> {
    const session = this.session;
    if (session === null) return;
    if (this.status.mic !== "live") return;
    try {
      await api.sendVoiceAudio(session, pcm);
    } catch (failure) {
      this.apply(
        next(this.status, { kind: "transport_failed", detail: describeFailure(failure) }),
      );
      await this.releaseEverything();
    }
  }

  private startPolling(): void {
    if (this.pollHandle === null) {
      this.pollHandle = this.schedule(() => void this.poll(), POLL_INTERVAL_MS);
    }
    if (this.speechHandle === null) {
      this.speechHandle = this.schedule(() => void this.collectSpeech(), SPEECH_POLL_INTERVAL_MS);
    }
  }

  private async poll(): Promise<void> {
    const session = this.session;
    if (session === null || this.polling) return;
    this.polling = true;
    try {
      const view = await api.voiceSession(session);
      this.view = view;
      this.options.hooks.onSession(view);
      this.noteSpeechEnd(view);
      this.applyActivity(view);
      const settled = view.turns.at(-1);
      if (settled !== undefined && settled.answer !== null) this.options.hooks.onTurnSettled(view);
    } catch (failure) {
      this.apply(
        next(this.status, { kind: "transport_failed", detail: describeFailure(failure) }),
      );
      await this.releaseEverything();
    } finally {
      this.polling = false;
    }
  }

  /**
   * The moment this window first observed that his speech had settled.
   *
   * `pending` is the service's settled-but-not-yet-submitted utterance, which is
   * exactly "he has stopped talking". Labelled honestly: this is when the desktop
   * *observed* it, one poll interval at most after the service established it, and
   * the §18 figure derived from it is a window measurement rather than a claim about
   * the recognizer's own clock.
   */
  private noteSpeechEnd(view: VoiceSessionView): void {
    if (view.pending === "") return;
    if (this.timings.speechEndAt !== null) return;
    this.timings = { ...this.timings, speechEndAt: this.now(), firstAudibleAt: null };
    this.options.hooks.onTimings(this.timings);
  }

  private applyActivity(view: VoiceSessionView): void {
    // Presentation, from what the service says is true. Never a guess, and never a
    // claim about the microphone: `withActivity` cannot change `mic`.
    const speaking = view.speaking?.active === true;
    if (speaking) {
      this.apply(withActivity(this.status, "speaking"));
      return;
    }
    if (view.pending !== "" || view.state === "thinking") {
      this.apply(withActivity(this.status, "thinking"));
      return;
    }
    if (view.provisional !== "") {
      this.apply(withActivity(this.status, "transcribing"));
      return;
    }
    this.apply(withActivity(this.status, this.status.mic === "live" ? "listening" : "idle"));
  }

  private async collectSpeech(): Promise<void> {
    const session = this.session;
    if (session === null || this.player === null || this.collecting) return;
    // §1.2: with Voice off no sink exists, so nothing can be played. Checked here
    // as well as by the player's own lifetime.
    if (this.status.session !== "active_mic_live" && this.status.session !== "active_muted") return;
    this.collecting = true;
    try {
      const offer = await api.collectSpeech(session);
      if (offer.stop) {
        // The physical half of barge-in, and the reason this poll asks both
        // questions: the buffer stops here rather than a session-poll later.
        this.timings = { ...this.timings, bargeInAt: this.timings.bargeInAt ?? this.now() };
        this.player.stop(offer.reason ?? "delivery ended");
        this.timings = { ...this.timings, silenceAt: this.now() };
        this.options.hooks.onTimings(this.timings);
        this.player = new SpeechPlayer(this.speakerObserver(), this.options.speaker);
        return;
      }
      const offered: SpokenAudioView | null = offer.segment;
      if (offered === null) return;
      this.player.enqueue({
        messageId: offered.message_id,
        segmentIndex: offered.segment_index,
        text: offered.text,
        audio: decodeSegmentAudio(offered.audio_base64),
      });
    } catch {
      // A failed collection is reported by the next session poll; it is not a
      // reason to tear the microphone down.
    } finally {
      this.collecting = false;
    }
  }

  private speakerObserver() {
    const report = (segment: SegmentAudio, state: PlaybackState, reason?: string): void => {
      const session = this.session;
      if (session === null) return;
      void api
        .reportPlayback(session, {
          message_id: segment.messageId,
          segment_index: segment.segmentIndex,
          state,
          // Omitted rather than sent as null when there is none: the service
          // refuses a reason on a state that must not carry one.
          ...(reason === undefined ? {} : { reason }),
        })
        .catch(() => undefined);
    };
    return {
      onStarted: (segment: SegmentAudio) => {
        if (this.timings.firstAudibleAt === null) {
          this.timings = { ...this.timings, firstAudibleAt: this.now() };
          this.options.hooks.onTimings(this.timings);
        }
        this.apply(withActivity(this.status, "speaking"));
        report(segment, "playback_started");
      },
      onCompleted: (segment: SegmentAudio) => {
        report(segment, "playback_completed");
        void this.markDelivered(segment.messageId);
      },
      onInterrupted: (segment: SegmentAudio, reason: string) => {
        report(segment, "playback_interrupted", reason);
      },
      onFailed: (segment: SegmentAudio, detail: string) => {
        report(segment, "playback_failed", detail);
      },
    };
  }

  private async markDelivered(messageId: string): Promise<void> {
    const session = this.session;
    if (session === null || this.lastDeliveredMessage === messageId) return;
    this.lastDeliveredMessage = messageId;
    try {
      await api.deliveredVoiceTurn(session, messageId);
    } catch {
      // The next poll reports the session's own view of delivery.
    }
  }

  private async releaseEverything(): Promise<void> {
    this.microphone?.release();
    this.microphone = null;
    this.player?.close();
    this.player = null;
    if (this.pollHandle !== null) {
      this.unschedule(this.pollHandle);
      this.pollHandle = null;
    }
    if (this.speechHandle !== null) {
      this.unschedule(this.speechHandle);
      this.speechHandle = null;
    }
    const unregister = this.options.unregisterShortcut;
    if (unregister !== undefined) await unregister().catch(() => undefined);
    const session = this.session;
    this.session = null;
    if (session !== null) {
      try {
        await api.closeVoiceSession(session);
      } catch {
        // The device is already released, which is the part that matters here.
      }
    }
    this.view = null;
    this.options.hooks.onSession(null);
    this.apply(stopped(this.status));
  }

  private apply(status: VoiceStatus): void {
    if (status === this.status) return;
    this.status = status;
    this.options.hooks.onStatus(status);
  }

  /** What the last poll said, for a caller that wants the session view. */
  get sessionView(): VoiceSessionView | null {
    return this.view;
  }
}
