// Her words, shown as she says them — owner order, 25 September 2026 (Voice-mode repair §4).
//
// Every assertion is about which part of the canonical answer is presented, and in
// which state, after a sequence of playback and delivery facts. No timer paces the
// text: only `started` reveals, and the stall check only ever reveals *more*.

import { describe, expect, it } from "vitest";

import { present, SpokenPresentation, STALL_MS, UNBOUND_MESSAGE, type SpokenAnswer } from "./spokenPresentation";

const HIS = "m-his";
const HERS = "m-hers";
const ANSWER = "Good evening, my lord. The lamps are lit. Shall we begin?";
const SEGMENTS = ["Good evening, my lord. ", "The lamps are lit. ", "Shall we begin?"];

function subject(start = 0) {
  const clock = { now: start };
  const seen: (SpokenAnswer | null)[] = [];
  const presentation = new SpokenPresentation((answer) => seen.push(answer), () => clock.now);
  return { presentation, clock, seen };
}

describe("text follows playback", () => {
  it("shows nothing of her answer before her voice starts, then each segment as it plays", () => {
    const { presentation } = subject();
    presentation.turn(HIS);
    presentation.answered(HIS, HERS);
    expect(present(ANSWER, HERS, presentation.current)).toEqual({
      shown: "",
      unspoken: "",
      pacing: true,
      note: null,
    });
    presentation.offered(HERS);
    presentation.started(HERS, 0, SEGMENTS[0]!);
    expect(present(ANSWER, HERS, presentation.current).shown).toBe(SEGMENTS[0]);
    presentation.offered(HERS);
    presentation.ended(HERS, 0);
    presentation.started(HERS, 1, SEGMENTS[1]!);
    expect(present(ANSWER, HERS, presentation.current).shown).toBe(SEGMENTS[0]! + SEGMENTS[1]!);
  });

  it("is complete — the whole message, no note — once every offered segment has started", () => {
    const { presentation } = subject();
    presentation.turn(HIS);
    presentation.answered(HIS, HERS);
    SEGMENTS.forEach((text, index) => {
      presentation.offered(HERS);
      presentation.started(HERS, index, text);
    });
    expect(presentation.current?.state).toBe("speaking"); // the delivery may offer more
    presentation.allOffered(HERS);
    expect(presentation.current?.state).toBe("complete");
    expect(present(ANSWER, HERS, presentation.current)).toEqual({
      shown: ANSWER,
      unspoken: "",
      pacing: false,
      note: null,
    });
  });

  it("does not complete while an offered segment has not yet started", () => {
    const { presentation } = subject();
    presentation.turn(HIS);
    presentation.answered(HIS, HERS);
    presentation.offered(HERS);
    presentation.offered(HERS);
    presentation.started(HERS, 0, SEGMENTS[0]!);
    presentation.allOffered(HERS);
    expect(presentation.current?.state).toBe("speaking");
    presentation.started(HERS, 1, SEGMENTS[1]!);
    expect(presentation.current?.state).toBe("complete");
  });

  it("reveals a segment once, however often its start is reported", () => {
    const { presentation } = subject();
    presentation.turn(HIS);
    presentation.answered(HIS, HERS);
    presentation.started(HERS, 0, SEGMENTS[0]!);
    expect(presentation.started(HERS, 0, SEGMENTS[0]!)).toBeNull();
    expect(presentation.current?.revealed).toBe(SEGMENTS[0]);
  });

  it("adopts segments voiced before her answer was written", () => {
    const { presentation } = subject();
    presentation.turn(HIS);
    expect(presentation.belongs(UNBOUND_MESSAGE)).toBe(true);
    presentation.offered(UNBOUND_MESSAGE);
    presentation.started(UNBOUND_MESSAGE, 0, SEGMENTS[0]!);
    presentation.answered(HIS, HERS);
    expect(present(ANSWER, HERS, presentation.current).shown).toBe(SEGMENTS[0]);
  });

  it("shows any other message whole — ordinary text presentation is unchanged", () => {
    const { presentation } = subject();
    presentation.turn(HIS);
    presentation.answered(HIS, HERS);
    expect(present("An earlier answer.", "m-other", presentation.current).shown).toBe("An earlier answer.");
    expect(present(ANSWER, HERS, null).shown).toBe(ANSWER);
  });

  it("never mangles a message whose text the revealed segments do not prefix", () => {
    const { presentation } = subject();
    presentation.turn(HIS);
    presentation.answered(HIS, HERS);
    presentation.started(HERS, 0, "Something she did not write. ");
    expect(present(ANSWER, HERS, presentation.current)).toEqual({
      shown: ANSWER,
      unspoken: "",
      pacing: false,
      note: null,
    });
  });
});

describe("a late segment cannot sound or reveal in the wrong turn", () => {
  it("a finished answer's repeated `completed` does not complete the next one early", () => {
    const { presentation } = subject();
    presentation.turn(HIS);
    presentation.answered(HIS, HERS);
    presentation.offered(HERS);
    presentation.started(HERS, 0, ANSWER);
    presentation.allOffered(HERS);
    presentation.turn("m-his-next");
    presentation.answered("m-his-next", "m-hers-next");
    presentation.allOffered(HERS); // still reported until the next delivery begins
    presentation.stopped(HERS, false);
    presentation.offered("m-hers-next");
    presentation.started("m-hers-next", 0, "First. ");
    expect(presentation.current?.state).toBe("speaking");
    expect(present("First. Second.", "m-hers-next", presentation.current).shown).toBe("First. ");
  });

  it("a stop with no written answer applies only to a delivery that handed us audio", () => {
    const { presentation } = subject();
    presentation.turn(HIS);
    presentation.stopped(null, false);
    expect(presentation.current?.state).toBe("awaiting");
    presentation.offered(UNBOUND_MESSAGE);
    presentation.stopped(null, true);
    expect(presentation.current?.state).toBe("failed");
  });

  it("refuses a segment of the previous answer once his next turn has begun", () => {
    const { presentation } = subject();
    presentation.turn(HIS);
    presentation.answered(HIS, HERS);
    presentation.started(HERS, 0, SEGMENTS[0]!);
    presentation.turn("m-his-next");
    presentation.answered("m-his-next", "m-hers-next");
    expect(presentation.belongs(HERS)).toBe(false);
    expect(presentation.started(HERS, 1, SEGMENTS[1]!)).toBeNull();
    expect(presentation.current?.revealed).toBe("");
  });

  it("ends the previous answer, unspoken, when his next turn begins", () => {
    const { presentation, seen } = subject();
    presentation.turn(HIS);
    presentation.answered(HIS, HERS);
    presentation.started(HERS, 0, SEGMENTS[0]!);
    presentation.turn("m-his-next");
    expect(seen.some((answer) => answer?.messageId === HERS && answer.state === "released")).toBe(true);
  });

  it("accepts nothing after the answer has been interrupted", () => {
    const { presentation } = subject();
    presentation.turn(HIS);
    presentation.answered(HIS, HERS);
    presentation.started(HERS, 0, SEGMENTS[0]!);
    presentation.interrupted();
    expect(presentation.belongs(HERS)).toBe(false);
    expect(presentation.started(HERS, 1, SEGMENTS[1]!)).toBeNull();
  });
});

describe("generated text is never stranded, and never presented as spoken", () => {
  function spokenFirstSegment() {
    const made = subject();
    made.presentation.turn(HIS);
    made.presentation.answered(HIS, HERS);
    made.presentation.offered(HERS);
    made.presentation.started(HERS, 0, SEGMENTS[0]!);
    return made;
  }

  it.each([
    ["interrupted", "Not spoken — Val was interrupted."],
    ["failed", "Not spoken — her voice failed; the text is complete."],
    ["released", "Not spoken — Voice ended."],
  ] as const)("%s: the rest appears at once, marked not spoken", (state, note) => {
    const { presentation } = spokenFirstSegment();
    presentation[state]();
    expect(present(ANSWER, HERS, presentation.current)).toEqual({
      shown: SEGMENTS[0],
      unspoken: SEGMENTS[1]! + SEGMENTS[2]!,
      pacing: false,
      note,
    });
  });

  it("a delivery that stops moving reveals the rest after the stall limit", () => {
    const { presentation, clock } = spokenFirstSegment();
    presentation.ended(HERS, 0);
    clock.now += STALL_MS - 1;
    presentation.checkStall();
    expect(presentation.current?.state).toBe("speaking");
    clock.now += 1;
    presentation.checkStall();
    expect(presentation.current?.state).toBe("stalled");
    expect(present(ANSWER, HERS, presentation.current).unspoken).toBe(SEGMENTS[1]! + SEGMENTS[2]!);
  });

  it("a long sentence still playing is not a stall", () => {
    const { presentation, clock } = spokenFirstSegment();
    clock.now += STALL_MS * 3;
    presentation.checkStall();
    expect(presentation.current?.state).toBe("speaking");
  });

  it("an answer whose voice never starts is shown after the stall limit", () => {
    const { presentation, clock } = subject();
    presentation.turn(HIS);
    presentation.answered(HIS, HERS);
    clock.now += STALL_MS;
    presentation.checkStall();
    expect(present(ANSWER, HERS, presentation.current)).toMatchObject({ shown: "", unspoken: ANSWER });
  });

  it("an interruption after the last word adds no note", () => {
    const { presentation } = subject();
    presentation.turn(HIS);
    presentation.answered(HIS, HERS);
    presentation.started(HERS, 0, ANSWER);
    presentation.interrupted();
    expect(present(ANSWER, HERS, presentation.current).note).toBeNull();
  });
});

describe("the coordination figures", () => {
  it("reports each segment's text-after-playback offset and the gaps between segments", () => {
    const { presentation, clock } = subject(1_000);
    presentation.turn(HIS);
    presentation.answered(HIS, HERS);
    clock.now = 2_000;
    presentation.started(HERS, 0, SEGMENTS[0]!);
    presentation.shown(HERS, SEGMENTS[0]!.length, 2_016);
    clock.now = 4_000;
    presentation.ended(HERS, 0);
    clock.now = 4_250;
    presentation.started(HERS, 1, SEGMENTS[1]!);
    presentation.shown(HERS, SEGMENTS[0]!.length + SEGMENTS[1]!.length, 4_262);
    expect(presentation.offsets()).toEqual([16, 12]);
    expect(presentation.gaps()).toEqual([250]);
  });
});
