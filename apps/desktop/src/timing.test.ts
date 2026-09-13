// Timing words keep their clock origins apart — ruling, 13 September 2026.

import { describe, expect, it } from "vitest";

import { newTurnClock, PROGRESS_NOTE, STAGE_WORDS, timingLines, visibilityLine } from "./timing";

describe("timing lines", () => {
  it("reproduces the 13 September consequential turn without mixing origins", () => {
    const clock = {
      ...newTurnClock(),
      responseStartedMs: 48_730,
      firstDeltaMs: 61_470,
      firstDeltaVisible: true,
      firstRenderMs: 61_480,
      firstRenderVisible: true,
      firstPaintMs: 71_610,
      firstPaintVisible: true,
    };
    const lines = timingLines({
      clock,
      completeMs: 79_280,
      responseCallFirstTokenMs: 12_740,
      serviceResponseStartedMs: 48_700,
    });
    expect(lines.fromSend).toBe(
      "From Send: work before Val began answering 48.73 s · first text received 61.47 s · " +
        "first words painted 71.61 s · complete 79.28 s.",
    );
    expect(lines.responseCall).toBe(
      "Response call alone, from its own start: first token after 12.74 s.",
    );
    expect(lines.fromSend).not.toContain("12.74");
    expect(lines.visibility).toBeNull();
  });

  it("falls back to the service's figure, and says so", () => {
    const lines = timingLines({
      clock: { ...newTurnClock(), firstDeltaMs: 2_000 },
      completeMs: 3_000,
      responseCallFirstTokenMs: null,
      serviceResponseStartedMs: 1_200,
    });
    expect(lines.fromSend).toContain("1.20 s (measured at the service)");
    expect(lines.responseCall).toBeNull();
  });

  it("reports a hidden window and when it became visible, and nothing more", () => {
    const clock = {
      ...newTurnClock(),
      firstDeltaMs: 61_470,
      firstDeltaVisible: false,
      firstRenderVisible: false,
      firstPaintVisible: true,
      visibilityChanges: [
        { atMs: 20_000, visible: false },
        { atMs: 71_600, visible: true },
      ],
    };
    expect(visibilityLine(clock)).toBe(
      "The window was not visible when the first text arrived, when it was rendered. It became visible at 71.60 s.",
    );
  });

  it("says nothing about visibility when nothing was hidden", () => {
    expect(visibilityLine({ ...newTurnClock(), firstDeltaVisible: true, firstPaintVisible: true })).toBeNull();
  });
});

describe("stage words", () => {
  it("use plain language and no internal vocabulary", () => {
    const all = Object.values(STAGE_WORDS).join(" ").toLowerCase();
    for (const term of ["classif", "strip", "blind", "deliberat", "consequential", "preference", "verdict"]) {
      expect(all).not.toContain(term);
    }
  });

  it("state that progress is not the responsiveness requirement", () => {
    expect(PROGRESS_NOTE).toContain("does not count toward the 1–2 second responsiveness requirement");
  });
});
