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

import type {
  PlaybackState,
  SpokenAudioView,
  VoiceCommittedView,
  VoiceSessionView,
} from "./api";
import { api, describeFailure } from "./api";
import {
  MicrophoneCapture,
  type AppliedCaptureSettings,
  type CapturePlatform,
} from "./microphone";
import { OrderedPcmSender, type SenderReport } from "./pcmSender";
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

/**
 * What this window observed, **for one turn**.
 *
 * Owner acceptance repair, 25 September 2026 (WP3 §4). These were per-*session*
 * before, and set once: `speechEndAt` kept the session's first transcript,
 * `firstAudibleAt` its first audio, and `bargeInAt` its first interruption, while
 * `silenceAt` was overwritten by whichever came last. So the figures shown in the
 * room — `transcript → audible 23210 ms`, `barge-in → silence 49891 ms` — were not
 * latencies at all. They were the span from one turn's beginning to a later turn's
 * end. **Each interval is now a pair of marks from the same event.**
 */
export interface VoiceTimings {
  /** Owner's unmute gesture → a live track → the first chunk accepted (§7). */
  unmuteGestureAt: number | null;
  unmuteTrackLiveAt: number | null;
  unmuteFirstChunkAt: number | null;
  /**
   * When this window first observed the service holding a settled transcript for
   * **this** utterance, and when the first audio of the answer to it was scheduled.
   * Reset together, so they can only ever describe one turn.
   */
  utterance: number | null;
  speechEndAt: number | null;
  firstAudibleAt: number | null;
  /**
   * The most recent interruption: when the stop instruction was observed, and when
   * the playing buffer had been stopped. Both written by the same event.
   */
  bargeInAt: number | null;
  silenceAt: number | null;
  /**
   * Owner diagnostic, 25 September 2026: his words, from the service to the screen.
   * `committedSeenAt` is when a poll first returned his committed message;
   * `ownerShownAt` is the React commit that put it in the thread (a DOM fact); and
   * `ownerFramesAt` is two animation frames after that — the nearest this window
   * can come to a paint, and **not** a claim that the screen showed it.
   */
  committedSeenAt: number | null;
  ownerShownAt: number | null;
  ownerFramesAt: number | null;
  /**
   * When his speech ended, **estimated** from the recognizer's endpoint: the
   * service says how long ago (endpoint less the confirming silence), and this is
   * the time the poll carrying that arrived, less it. Not an acoustic observation,
   * and it carries the poll's own transit as error (owner Step B retest, §13.1).
   */
  speechEndEstimateAt: number | null;
}

export const NO_TIMINGS: VoiceTimings = {
  unmuteGestureAt: null,
  unmuteTrackLiveAt: null,
  unmuteFirstChunkAt: null,
  utterance: null,
  speechEndAt: null,
  firstAudibleAt: null,
  bargeInAt: null,
  silenceAt: null,
  committedSeenAt: null,
  ownerShownAt: null,
  ownerFramesAt: null,
  speechEndEstimateAt: null,
};

export interface VoiceControllerHooks {
  onStatus(status: VoiceStatus): void;
  onSession(view: VoiceSessionView | null): void;
  onTimings(timings: VoiceTimings): void;
  /**
   * An answered exchange exists: the conversation should be re-read from the store.
   *
   * **Owner acceptance, 24 September 2026 (§4.1 B), and its correction.** That pass
   * said this hook now fired "as soon as a canonical turn exists". It did not, and
   * could not: it keyed on the session's `turns`, which the service filled only
   * once her answer was written and spoken, so an "asked" state never occurred. His
   * diagnostic of 25 September found the same invisible wait. What shows his words
   * now is `onOwnerMessageCommitted`, driven by the commit itself; this hook is the
   * second read, for her answer.
   */
  onTurnSettled(view: VoiceSessionView): void;
  /**
   * His spoken words are canonical in the store — re-read the conversation now,
   * while she is still thinking. Fired once per committed message, from the
   * service's `committed` field, which the commit itself sets before any provider
   * is contacted (owner diagnostic, 25 September 2026).
   */
  onOwnerMessageCommitted?(committed: VoiceCommittedView): void;
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
  /** One sender, one request in flight, strict order (WP3 repair pass §2). */
  private sender: OrderedPcmSender | null = null;
  /** What the platform applied to the live track, once it has said (§25). */
  private applied: AppliedCaptureSettings | null = null;
  private player: SpeechPlayer | null = null;
  private pollHandle: number | null = null;
  private speechHandle: number | null = null;
  private lastDeliveredMessage: string | null = null;
  /** The turn state the desktop was last told to render, so it is told once each. */
  private lastShown: string | null = null;
  /** The committed owner message the desktop was last told to show. */
  private lastCommitted: string | null = null;
  /** The utterance whose intervals have been reported, so each is sent once. */
  private reportedUtterance: number | null = null;
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
    // Nothing unsent survives a mute: audio captured before the release is stale
    // the moment the device is gone, and sending it afterwards would be sending
    // audio from a microphone the owner had already closed.
    this.sender?.close();
    this.sender = null;
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
          // Offered to the ordered sender, never sent from here: the audio's order
          // is the audio, and fifty racing requests a second destroyed it.
          this.sender?.offer(pcm);
        },
        onLive: (applied) => {
          // §25: what the platform actually applied, recorded rather than assumed.
          // The next acceptance run can say whether echo cancellation was in force.
          this.applied = applied;
          console.info("val.voice.capture", JSON.stringify(applied));
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
    this.openSender();
    this.microphone = capture;
    await capture.open();
  }

  /** A fresh ordered sender for this acquisition. */
  private openSender(): void {
    this.sender?.close();
    this.sender = new OrderedPcmSender(
      async (payload) => {
        const session = this.session;
        if (session === null) return;
        if (this.status.mic !== "live") return;
        await api.sendVoiceAudio(session, payload);
      },
      (detail) => {
        this.apply(next(this.status, { kind: "transport_failed", detail }));
        void this.releaseEverything();
      },
    );
  }

  /** What the platform applied to the microphone, or null until it says. */
  get captureSettings(): AppliedCaptureSettings | null {
    return this.applied;
  }

  /** What the sender did this session — ordered, coalesced, and counted. */
  get transport(): SenderReport | null {
    return this.sender === null ? null : this.sender.measured;
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
      this.noteSpeechEndEstimate(view, this.now());
      this.applyActivity(view);
      // **His words, the moment they are canonical.** The service sets `committed`
      // from inside the turn when his message is written, before cognition begins;
      // the conversation is read then, once per message, and not on every poll.
      const committed = view.committed ?? null;
      if (committed !== null && committed.message_id !== this.lastCommitted) {
        this.lastCommitted = committed.message_id;
        if (this.timings.committedSeenAt === null) {
          this.timings = { ...this.timings, committedSeenAt: this.now() };
          this.options.hooks.onTimings(this.timings);
        }
        this.options.hooks.onOwnerMessageCommitted?.(committed);
      }
      // And hers, once the exchange is answered.
      const settled = view.turns.at(-1);
      if (settled !== undefined) {
        const state = `${settled.message_id}:${settled.answer === null ? "asked" : "answered"}`;
        if (state !== this.lastShown) {
          this.lastShown = state;
          this.options.hooks.onTurnSettled(view);
        }
      }
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
    // **Per utterance, not per session.** The service's `utterance` index is what
    // makes this turn a different turn; without it the first transcript of the
    // session was paired with the last audio of the session, which is how a 23-second
    // figure appeared for an interval nobody had measured.
    if (this.timings.utterance === view.utterance) return;
    this.timings = {
      ...this.timings,
      utterance: view.utterance,
      speechEndAt: this.now(),
      firstAudibleAt: null,
      committedSeenAt: null,
      ownerShownAt: null,
      ownerFramesAt: null,
      speechEndEstimateAt: null,
    };
    this.reportedUtterance = null;
    this.options.hooks.onTimings(this.timings);
  }

  /** Speech end for the current utterance, from the service's endpoint estimate. */
  private noteSpeechEndEstimate(view: VoiceSessionView, receivedAt: number): void {
    const ended = view.speech_end ?? null;
    if (ended === null || ended.utterance !== this.timings.utterance) return;
    if (this.timings.speechEndEstimateAt !== null) return;
    this.timings = { ...this.timings, speechEndEstimateAt: receivedAt - ended.ms_ago };
    this.options.hooks.onTimings(this.timings);
  }

  /**
   * The turn's owner-facing intervals, sent once to the service to be logged — his
   * run left them on the panel and nowhere else. Sent when both ends exist.
   */
  private maybeReportTimings(): void {
    const t = this.timings;
    const session = this.session;
    if (session === null || t.utterance === null || this.reportedUtterance === t.utterance) return;
    if (t.ownerShownAt === null || t.firstAudibleAt === null) return;
    this.reportedUtterance = t.utterance;
    const between = (from: number | null, to: number | null) =>
      from === null || to === null ? null : Math.round(to - from);
    void api
      .reportVoiceTimings(session, {
        utterance: t.utterance,
        speech_end_to_owner_message_dom_ms: between(t.speechEndEstimateAt, t.ownerShownAt),
        owner_message_dom_to_playback_start_ms: between(t.ownerShownAt, t.firstAudibleAt),
        speech_end_to_playback_start_ms: between(t.speechEndEstimateAt, t.firstAudibleAt),
        committed_seen_to_owner_message_dom_ms: between(t.committedSeenAt, t.ownerShownAt),
      })
      .catch(() => undefined);
  }

  /**
   * His committed message that has no answered turn yet — what Voice Off must not
   * strand. `null` when everything he said has been answered, or nothing was said.
   */
  get awaitingAnswer(): VoiceCommittedView | null {
    const view = this.view;
    const committed = view?.committed ?? null;
    if (view === null || committed === null) return null;
    const answered = view.turns.some((turn) => turn.message_id === committed.message_id);
    return answered ? null : committed;
  }

  /**
   * The thread has rendered his committed message: `domAt` is the React commit that
   * contained it, `framesAt` two animation frames later. Ignored for any message but
   * the one last committed, and recorded once, so a later re-render cannot move it.
   */
  noteOwnerMessageShown(messageId: string, domAt: number, framesAt: number | null): void {
    if (messageId !== this.lastCommitted || this.timings.committedSeenAt === null) return;
    if (this.timings.ownerShownAt !== null && framesAt === null) return;
    this.timings = {
      ...this.timings,
      ownerShownAt: this.timings.ownerShownAt ?? domAt,
      ownerFramesAt: this.timings.ownerFramesAt ?? framesAt,
    };
    this.options.hooks.onTimings(this.timings);
    this.maybeReportTimings();
  }

  /** The message the desktop was last told to show, for the thread to look for. */
  get committedMessage(): string | null {
    return this.lastCommitted;
  }

  private applyActivity(view: VoiceSessionView): void {
    // Presentation, from what the service says is true. Never a guess, and never a
    // claim about the microphone: `withActivity` cannot change `mic`.
    // `delivery`, as the service's contract names it. This read `speaking` — a field
    // the service has never sent — so the service's own word that she was speaking
    // never reached this line (found in the owner diagnostic pass, 25 September 2026).
    const speaking = view.delivery?.active === true;
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
        // Both marks from this one event: the stop instruction as it was observed,
        // and the moment the playing buffer had been stopped. Keeping the session's
        // *first* barge-in here — which is what `?? this.now()` did — is what
        // produced the 49,891 ms figure he saw, an interval spanning several turns.
        const observed = this.now();
        this.player.stop(offer.reason ?? "delivery ended");
        this.timings = { ...this.timings, bargeInAt: observed, silenceAt: this.now() };
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
          this.maybeReportTimings();
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
    this.sender?.close();
    this.sender = null;
    this.microphone?.release();
    this.microphone = null;
    this.player?.close();
    this.player = null;
    // The service is told **before anything is awaited**. On a closing window the
    // first await can be the last thing that runs, and the close used to come after
    // the shortcut's unregistration — which is how three of his four diagnostic
    // sessions were left open on the service (owner diagnostic, 25 September 2026).
    const session = this.session;
    this.session = null;
    const closing =
      session === null
        ? Promise.resolve()
        : api.closeVoiceSession(session).then(
            () => undefined,
            // The device is already released, which is the part that matters here;
            // and a session the service never hears about is reaped there.
            () => undefined,
          );
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
    await closing;
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
