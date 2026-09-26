// The stall bound follows a streamed segment's real length — 26 September 2026.
//
// The player's own behaviour with streamed pieces is held by `speaker.test.ts`
// against the real playback worklet; this holds the presentation's side of it.

import { describe, expect, it } from "vitest";

import { SpokenPresentation } from "./spokenPresentation";

describe("the stall bound follows a streamed segment's real length", () => {
  it("extends the expected end as pieces arrive, before and after it starts", () => {
    const clock = { now: 0 };
    const presentation = new SpokenPresentation(() => undefined, () => clock.now);
    presentation.turn("h", 1);
    presentation.answered("h", "m");
    const key = presentation.offered("m") as number;
    presentation.extend(key, 1, 960); // arrived before playback began
    presentation.started(key, 1, "A long first sentence. ", 960);
    presentation.extend(key, 1, 960);
    const segment = presentation.byKey(key)!.segments[0]!;
    expect(segment.expectedEndAt).toBe(2_880);
  });
});
