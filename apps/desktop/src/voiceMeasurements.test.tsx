// @vitest-environment jsdom
//
// The panel's owner-facing intervals — owner Step B retest, 25 September 2026, §13.1.
// Each is labelled for what it measures, and says "unavailable" rather than guessing.

import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";

import { VoiceMeasurements } from "./App";
import { NO_TIMINGS } from "./voiceController";

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

function render(timings: typeof NO_TIMINGS): string {
  const host = document.createElement("div");
  const root = createRoot(host);
  act(() => root.render(<VoiceMeasurements timings={timings} />));
  const text = host.textContent ?? "";
  act(() => root.unmount());
  return text;
}

describe("the Voice measurements panel", () => {
  it("shows the three intervals, named for their actual boundaries", () => {
    const text = render({
      ...NO_TIMINGS,
      utterance: 1,
      speechEndEstimateAt: 1_000,
      ownerShownAt: 3_150,
      firstAudibleAt: 17_400,
    });
    expect(text).toContain("speech end (est.) → your words in thread 2150 ms");
    expect(text).toContain("your words in thread → her playback start 14250 ms");
    expect(text).toContain("speech end (est.) → her playback start 16400 ms");
    expect(text).not.toContain("audible");
  });

  it("says unavailable when an end is missing, and invents nothing", () => {
    const text = render({ ...NO_TIMINGS, utterance: 1, ownerShownAt: 3_150 });
    expect(text).toContain("speech end (est.) → your words in thread unavailable");
    expect(text).toContain("your words in thread → her playback start unavailable");
    expect(text).toContain("speech end (est.) → her playback start unavailable");
  });
});
