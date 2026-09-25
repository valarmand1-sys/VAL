// The Voice state machine — owner execution order, 24 September 2026, §4.
//
// Two dimensions, never collapsed into one (§4's explicit instruction). The
// **session** is what Lord Armand turned on; the **microphone** is what the
// hardware is actually doing; and what Val is doing with her voice is a third,
// independent thing. "Voice On · Mic Muted · Val Speaking" is a valid state, and a
// single enum could not say it.
//
// Every transition below is guarded, and the guards are the privacy ruling in
// code: **nothing but an explicit owner gesture reaches a live microphone.** There
// is no timer, no wake word, no resume, no retry that reacquires a device, and no
// path from an error back to capture.

/** What the owner turned on. */
export type VoiceSession =
  | "off"
  | "starting"
  | "active_mic_live"
  | "active_muted"
  | "stopping"
  | "error_safe";

/** What the microphone hardware is actually doing. Observed, never requested. */
export type MicHardware = "released" | "acquiring" | "live";

/** What the house is doing with the turn, for presentation only. */
export type Activity = "idle" | "listening" | "transcribing" | "thinking" | "speaking";

/** Every owner gesture, and the few non-gesture events that may only fail closed. */
export type VoiceEvent =
  // Owner gestures. These are the ONLY events that may lead toward a live mic.
  | { kind: "owner_pressed_voice_on" }
  | { kind: "owner_pressed_voice_off" }
  | { kind: "owner_pressed_mute" }
  | { kind: "owner_pressed_unmute" }
  // Observations of what actually happened, reported by the capture layer.
  | { kind: "capture_became_live" }
  | { kind: "capture_released" }
  | { kind: "session_ready" }
  // Failures. Every one of these may only move toward muted or off (§1.3).
  | { kind: "permission_denied"; detail: string }
  | { kind: "capture_failed"; detail: string }
  | { kind: "transport_failed"; detail: string }
  | { kind: "conversation_changed" }
  | { kind: "app_or_machine_suspending" };

export interface VoiceStatus {
  session: VoiceSession;
  mic: MicHardware;
  activity: Activity;
  /** Present when a failure put the session here. Shown to the owner, never hidden. */
  failure: string | null;
  /** True only while the global mute shortcut is allowed to exist (§8). */
  shortcutRegistered: boolean;
}

export const VOICE_OFF: VoiceStatus = {
  session: "off",
  mic: "released",
  activity: "idle",
  failure: null,
  shortcutRegistered: false,
};

/** Whether this status means a real microphone track is live. */
export function micIsLive(status: VoiceStatus): boolean {
  return status.mic === "live";
}

/** Whether physical speaker output is permitted right now (§1.2). */
export function speakerPermitted(status: VoiceStatus): boolean {
  return status.session === "active_mic_live" || status.session === "active_muted";
}

/**
 * The transition function. Pure: it decides, and the caller performs.
 *
 * Returning the same object means "this event changes nothing", which is how a
 * shortcut press while Voice is off becomes a hard no-op rather than a start.
 */
export function next(status: VoiceStatus, event: VoiceEvent): VoiceStatus {
  switch (event.kind) {
    // --- the one door to a live microphone ---------------------------------------
    case "owner_pressed_voice_on":
      // Only from off, and only from an owner press. A session that is starting,
      // active, stopping or in a safe error state is not restarted by this.
      if (status.session !== "off") return status;
      return { ...status, session: "starting", mic: "acquiring", activity: "idle", failure: null };

    case "session_ready":
      // The service session exists. The microphone is still not live: that waits
      // for the capture layer to say so.
      return status;

    case "capture_became_live":
      // The hardware really is capturing. Reachable only while starting or
      // unmuting — never from off, and never from an error state.
      if (status.session === "starting" || status.session === "active_muted") {
        return { ...status, session: "active_mic_live", mic: "live", activity: "listening" };
      }
      return status;

    // --- mute, unmute -------------------------------------------------------------
    case "owner_pressed_mute":
      if (status.session !== "active_mic_live") return status;
      // The session stays active and Val keeps speaking (§6.3). `mic` becomes
      // `released` only when the capture layer confirms it, which is the honest
      // indicator rule (§9) — so this says "acquiring nothing" rather than lying.
      return { ...status, session: "active_muted", mic: "released" };

    case "owner_pressed_unmute":
      if (status.session !== "active_muted") return status;
      return { ...status, session: "active_muted", mic: "acquiring", failure: null };

    case "capture_released":
      if (status.session === "active_mic_live") {
        return { ...status, session: "active_muted", mic: "released" };
      }
      return { ...status, mic: "released" };

    // --- off ----------------------------------------------------------------------
    case "owner_pressed_voice_off":
      if (status.session === "off") return status;
      return {
        ...status,
        session: "stopping",
        mic: "released",
        activity: "idle",
        shortcutRegistered: false,
      };

    case "conversation_changed":
    case "app_or_machine_suspending":
      // §16. Voice goes off and the microphone is released. Never a mute that
      // might be silently unmuted later by something that is not him.
      if (status.session === "off") return status;
      return {
        ...status,
        session: "off",
        mic: "released",
        activity: "idle",
        shortcutRegistered: false,
        failure: null,
      };

    // --- failures, which may only fail closed -------------------------------------
    case "permission_denied":
    case "capture_failed":
      // A failure while starting ends in OFF; a failure while unmuting stays
      // MUTED, because the session and the conversation are still his and only
      // the device acquisition failed. Neither retries (§7, §16).
      if (status.session === "active_muted" || status.session === "active_mic_live") {
        return { ...status, session: "active_muted", mic: "released", failure: event.detail };
      }
      return {
        ...status,
        session: "off",
        mic: "released",
        activity: "idle",
        shortcutRegistered: false,
        failure: event.detail,
      };

    case "transport_failed":
      return {
        ...status,
        session: "error_safe",
        mic: "released",
        activity: "idle",
        shortcutRegistered: false,
        failure: event.detail,
      };
  }
}

/** Mark the session fully stopped, once the release path has actually run. */
export function stopped(status: VoiceStatus): VoiceStatus {
  return { ...VOICE_OFF, failure: status.failure };
}

/** Record that the global shortcut is (un)registered — §8's privacy rule. */
export function withShortcut(status: VoiceStatus, registered: boolean): VoiceStatus {
  return { ...status, shortcutRegistered: registered };
}

export function withActivity(status: VoiceStatus, activity: Activity): VoiceStatus {
  // Presentation only, and never a claim about hardware: an activity change
  // cannot make a released microphone read as live.
  return { ...status, activity };
}

/**
 * The owner-facing labels — §9. Actual state, never requested state.
 *
 * Both dimensions are always represented when they differ, and colour is never
 * the only signal because these are words.
 */
export function describeVoice(status: VoiceStatus): string {
  if (status.session === "off") return "Voice Off";
  if (status.session === "error_safe") return "Voice Off · Error";
  if (status.session === "stopping") return "Voice Stopping…";
  if (status.session === "starting") return "Voice Starting…";

  const mic =
    status.mic === "live" ? "Mic Listening" : status.mic === "acquiring" ? "Unmuting…" : "Mic Muted";
  const what =
    status.activity === "speaking"
      ? "Val Speaking"
      : status.activity === "thinking"
        ? "Val Thinking"
        : status.activity === "transcribing"
          ? "Transcribing"
          : null;
  return ["Voice On", mic, what].filter((piece) => piece !== null).join(" · ");
}

/** A short accessible label for the microphone control. */
export function micControlLabel(status: VoiceStatus): string {
  if (status.mic === "acquiring") return "Unmuting…";
  return status.mic === "live" ? "Mute microphone" : "Unmute microphone";
}


/**
 * What Lord Armand is asked before a conversation change ends Voice — §5.
 *
 * Owner acceptance, 24 September 2026. The release itself is the ruling and stays:
 * Voice must never carry its microphone or its session silently into another
 * conversation. What he objected to was being told afterwards. So the change is
 * intercepted **before** it happens, and this is the question.
 */
export const LEAVING_VOICE_CONFIRMATION =
  "Switching conversations will end Voice and release the microphone. Continue?";
