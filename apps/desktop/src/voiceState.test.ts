// The Voice state machine's guards — owner execution order, 24 September 2026, §19.
//
// These are the privacy rulings as assertions. The one that matters most is the
// first group: **nothing but an explicit owner gesture may lead toward a live
// microphone**, and every other event in the system is tested against that.

import { describe, expect, it } from "vitest";

import {
  VOICE_OFF,
  type VoiceEvent,
  type VoiceStatus,
  describeVoice,
  micControlLabel,
  micIsLive,
  next,
  speakerPermitted,
  stopped,
  withActivity,
  withShortcut,
} from "./voiceState";

const LIVE: VoiceStatus = {
  session: "active_mic_live",
  mic: "live",
  activity: "listening",
  failure: null,
  shortcutRegistered: true,
};
const MUTED: VoiceStatus = { ...LIVE, session: "active_muted", mic: "released" };

/** Every event the machine knows, so a new one cannot quietly escape the sweep. */
const EVERY_EVENT: VoiceEvent[] = [
  { kind: "owner_pressed_voice_on" },
  { kind: "owner_pressed_voice_off" },
  { kind: "owner_pressed_mute" },
  { kind: "owner_pressed_unmute" },
  { kind: "capture_became_live" },
  { kind: "capture_released" },
  { kind: "session_ready" },
  { kind: "permission_denied", detail: "denied" },
  { kind: "capture_failed", detail: "no device" },
  { kind: "transport_failed", detail: "no service" },
  { kind: "conversation_changed" },
  { kind: "app_or_machine_suspending" },
];

describe("only the owner starts a microphone", () => {
  it("defaults to off, with nothing held and no shortcut bound", () => {
    expect(VOICE_OFF.session).toBe("off");
    expect(VOICE_OFF.mic).toBe("released");
    expect(VOICE_OFF.shortcutRegistered).toBe(false);
    expect(micIsLive(VOICE_OFF)).toBe(false);
    expect(speakerPermitted(VOICE_OFF)).toBe(false);
  });

  it("reaches a starting state from the owner's press and from nothing else", () => {
    for (const event of EVERY_EVENT) {
      const result = next(VOICE_OFF, event);
      if (event.kind === "owner_pressed_voice_on") {
        expect(result.session).toBe("starting");
        continue;
      }
      expect(result.session === "starting").toBe(false);
      expect(result.mic).not.toBe("live");
    }
  });

  it("never reaches a live microphone from any non-owner event", () => {
    // Swept over every state, not only over off: an error path that reacquired a
    // device from a machine wake would be caught here.
    const states: VoiceStatus[] = [
      VOICE_OFF,
      { ...VOICE_OFF, session: "starting", mic: "acquiring" },
      LIVE,
      MUTED,
      { ...VOICE_OFF, session: "error_safe", failure: "no service" },
      { ...VOICE_OFF, session: "stopping" },
    ];
    for (const state of states) {
      for (const event of EVERY_EVENT) {
        if (event.kind === "capture_became_live") continue; // the capture layer's own observation
        const result = next(state, event);
        if (state.mic === "live" && result.mic === "live") continue; // already live, unchanged
        expect(result.mic).not.toBe("live");
      }
    }
  });

  it("only reports a live microphone when the capture layer says so", () => {
    const starting = next(VOICE_OFF, { kind: "owner_pressed_voice_on" });
    expect(starting.mic).toBe("acquiring");
    expect(micIsLive(starting)).toBe(false);
    const ready = next(starting, { kind: "session_ready" });
    expect(micIsLive(ready)).toBe(false);
    const live = next(ready, { kind: "capture_became_live" });
    expect(micIsLive(live)).toBe(true);
    expect(live.activity).toBe("listening");
  });

  it("does not become live from a capture report while Voice is off", () => {
    expect(next(VOICE_OFF, { kind: "capture_became_live" })).toBe(VOICE_OFF);
  });
});

describe("mute and unmute", () => {
  it("mute keeps the session and lets Val keep speaking", () => {
    const speaking = withActivity(LIVE, "speaking");
    const muted = next(speaking, { kind: "owner_pressed_mute" });
    expect(muted.session).toBe("active_muted");
    expect(muted.mic).toBe("released");
    expect(muted.activity).toBe("speaking");
    expect(speakerPermitted(muted)).toBe(true);
  });

  it("unmute is an explicit gesture and acquires before it claims to listen", () => {
    const unmuting = next(MUTED, { kind: "owner_pressed_unmute" });
    expect(unmuting.mic).toBe("acquiring");
    expect(micIsLive(unmuting)).toBe(false);
    expect(describeVoice(unmuting)).toContain("Unmuting");
    const live = next(unmuting, { kind: "capture_became_live" });
    expect(micIsLive(live)).toBe(true);
  });

  it("nothing unmutes automatically", () => {
    for (const event of EVERY_EVENT) {
      if (event.kind === "owner_pressed_unmute" || event.kind === "capture_became_live") continue;
      expect(next(MUTED, event).mic).not.toBe("live");
    }
  });
});

describe("failures fail closed", () => {
  it("a failure while starting ends off, never live", () => {
    const starting = next(VOICE_OFF, { kind: "owner_pressed_voice_on" });
    const denied = next(starting, { kind: "permission_denied", detail: "he said no" });
    expect(denied.session).toBe("off");
    expect(denied.mic).toBe("released");
    expect(denied.failure).toBe("he said no");
    expect(denied.shortcutRegistered).toBe(false);
  });

  it("a failure while unmuting stays muted and keeps the session", () => {
    const unmuting = next(MUTED, { kind: "owner_pressed_unmute" });
    const failed = next(unmuting, { kind: "capture_failed", detail: "the device vanished" });
    expect(failed.session).toBe("active_muted");
    expect(failed.mic).toBe("released");
    expect(failed.failure).toBe("the device vanished");
  });

  it("a transport failure ends in a safe error with nothing held", () => {
    const broken = next(LIVE, { kind: "transport_failed", detail: "the service went away" });
    expect(broken.session).toBe("error_safe");
    expect(broken.mic).toBe("released");
    expect(speakerPermitted(broken)).toBe(false);
    expect(broken.shortcutRegistered).toBe(false);
  });

  it("a conversation change and a suspend both end off with the shortcut gone", () => {
    for (const kind of ["conversation_changed", "app_or_machine_suspending"] as const) {
      const result = next(LIVE, { kind });
      expect(result.session).toBe("off");
      expect(result.mic).toBe("released");
      expect(result.shortcutRegistered).toBe(false);
    }
  });
});

describe("the labels report what happened", () => {
  it("says both dimensions when they differ", () => {
    expect(describeVoice(VOICE_OFF)).toBe("Voice Off");
    expect(describeVoice(LIVE)).toBe("Voice On · Mic Listening");
    expect(describeVoice(withActivity(LIVE, "speaking"))).toBe(
      "Voice On · Mic Listening · Val Speaking",
    );
    expect(describeVoice(withActivity(MUTED, "speaking"))).toBe(
      "Voice On · Mic Muted · Val Speaking",
    );
  });

  it("an activity change cannot make a released microphone read as live", () => {
    for (const activity of ["idle", "listening", "transcribing", "thinking", "speaking"] as const) {
      expect(micIsLive(withActivity(MUTED, activity))).toBe(false);
      expect(describeVoice(withActivity(MUTED, activity))).toContain("Mic Muted");
    }
  });

  it("the microphone control says what pressing it would do", () => {
    expect(micControlLabel(LIVE)).toBe("Mute microphone");
    expect(micControlLabel(MUTED)).toBe("Unmute microphone");
    expect(micControlLabel({ ...MUTED, mic: "acquiring" })).toBe("Unmuting…");
  });

  it("stopping keeps the failure visible and holds nothing", () => {
    const ended = stopped({ ...LIVE, failure: "the device vanished" });
    expect(ended.session).toBe("off");
    expect(ended.mic).toBe("released");
    expect(ended.failure).toBe("the device vanished");
  });

  it("records whether the shortcut is bound, without touching anything else", () => {
    const bound = withShortcut(MUTED, true);
    expect(bound.shortcutRegistered).toBe(true);
    expect(bound.mic).toBe("released");
    expect(withShortcut(bound, false).shortcutRegistered).toBe(false);
  });
});

describe("physical speech needs an owner-started session", () => {
  it("is permitted only while a session is active", () => {
    expect(speakerPermitted(LIVE)).toBe(true);
    expect(speakerPermitted(MUTED)).toBe(true);
    expect(speakerPermitted(VOICE_OFF)).toBe(false);
    expect(speakerPermitted({ ...VOICE_OFF, session: "starting" })).toBe(false);
    expect(speakerPermitted({ ...VOICE_OFF, session: "stopping" })).toBe(false);
    expect(speakerPermitted({ ...VOICE_OFF, session: "error_safe" })).toBe(false);
  });
});
