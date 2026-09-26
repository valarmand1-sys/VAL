// Her words, shown as she says them — owner order, 25 September 2026 (Voice-mode repair §4),
// held per answer since the targeted voice latency order of the same day.
//
// Every assertion is about which part of the canonical answer is presented, and in
// which state, after a sequence of playback and delivery facts. No timer paces the
// text: only `started` reveals, and the stall check only ever reveals *more*.

import { describe, expect, it } from "vitest";

import {
  present,
  SpokenPresentation,
  STALL_MS,
  UNBOUND_MESSAGE,
  type SpokenAnswer,
} from "./spokenPresentation";

const HIS = "m-his";
const HERS = "m-hers";
const ANSWER = "Good evening, my lord. The lamps are lit. Shall we begin?";
const SEGMENTS = ["Good evening, my lord. ", "The lamps are lit. ", "Shall we begin?"];

function subject(start = 0) {
  const clock = { now: start };
  const seen: SpokenAnswer[][] = [];
  const presentation = new SpokenPresentation((answers) => seen.push(answers), () => clock.now);
  return { presentation, clock, seen };
}

/** One turn, answered, with `count` segments offered and started in order. */
function speaking(count: number) {
  const made = subject();
  made.presentation.turn(HIS, 1);
  made.presentation.answered(HIS, HERS);
  const keys: number[] = [];
  for (let index = 0; index < count; index += 1) {
    const key = made.presentation.offered(HERS) as number;
    keys.push(key);
    made.presentation.started(key, index + 1, SEGMENTS[index]!);
  }
  return { ...made, key: keys[0] as number };
}

function shownOf(presentation: SpokenPresentation, id = HERS, content = ANSWER) {
  return present(content, id, presentation.answers);
}

describe("text follows playback", () => {
  it("shows nothing of her answer before her voice starts, then each segment as it plays", () => {
    const { presentation, clock } = subject();
    presentation.turn(HIS, 1);
    presentation.answered(HIS, HERS);
    expect(shownOf(presentation)).toEqual({ shown: "", unspoken: "", pacing: true, note: null });
    const key = presentation.offered(HERS) as number;
    presentation.started(key, 1, SEGMENTS[0]!);
    expect(shownOf(presentation).shown).toBe(SEGMENTS[0]);
    presentation.offered(HERS);
    clock.now += 1_000;
    presentation.ended(key, 1);
    presentation.started(key, 2, SEGMENTS[1]!);
    expect(shownOf(presentation).shown).toBe(SEGMENTS[0]! + SEGMENTS[1]!);
  });

  it("is complete — the whole message, no note — once every offered segment has started", () => {
    const { presentation } = speaking(3);
    expect(presentation.current?.state).toBe("speaking"); // the delivery may offer more
    presentation.allOffered(HERS);
    expect(presentation.current?.state).toBe("complete");
    expect(shownOf(presentation)).toEqual({ shown: ANSWER, unspoken: "", pacing: false, note: null });
  });

  it("does not complete while an offered segment has not yet started", () => {
    const { presentation } = subject();
    presentation.turn(HIS, 1);
    presentation.answered(HIS, HERS);
    const key = presentation.offered(HERS) as number;
    presentation.offered(HERS);
    presentation.started(key, 1, SEGMENTS[0]!);
    presentation.allOffered(HERS);
    expect(presentation.current?.state).toBe("speaking");
    presentation.started(key, 2, SEGMENTS[1]!);
    expect(presentation.current?.state).toBe("complete");
  });

  it("reveals a segment once, however often its start is reported", () => {
    const { presentation, key } = speaking(1);
    expect(presentation.started(key, 1, SEGMENTS[0]!)).toBeNull();
    expect(presentation.current?.revealed).toBe(SEGMENTS[0]);
  });

  it("keeps a segment voiced before her answer was written with that answer", () => {
    const { presentation } = subject();
    presentation.turn(HIS, 1);
    const key = presentation.offered(UNBOUND_MESSAGE) as number;
    // Her answer is announced between the hand-off and the playback.
    presentation.answered(HIS, HERS);
    presentation.started(key, 1, SEGMENTS[0]!);
    expect(presentation.messageIdOf(key)).toBe(HERS);
    expect(shownOf(presentation).shown).toBe(SEGMENTS[0]);
  });

  it("shows any other message whole — ordinary text presentation is unchanged", () => {
    const { presentation } = speaking(1);
    expect(present("An earlier answer.", "m-other", presentation.answers).shown).toBe(
      "An earlier answer.",
    );
    expect(present(ANSWER, HERS, []).shown).toBe(ANSWER);
  });

  it("never mangles a message whose text the revealed segments do not prefix", () => {
    const { presentation } = subject();
    presentation.turn(HIS, 1);
    presentation.answered(HIS, HERS);
    const key = presentation.offered(HERS) as number;
    presentation.started(key, 1, "Something she did not write. ");
    expect(shownOf(presentation)).toEqual({ shown: ANSWER, unspoken: "", pacing: false, note: null });
  });
});

describe("his next turn, committed while she is still speaking (his successful session)", () => {
  // Conversation 01a0db46…: "I'd like it a little bit faster" settled while she was
  // thinking, was committed 41 s later while answer 10 still had 44 s to play, and
  // answer 12 was written and voiced before answer 10 had finished.
  const TEN = "m-answer-10";
  const TWELVE = "m-answer-12";
  const TEN_TEXT = "The first part. The second part. The last part.";
  const TWELVE_TEXT = "Another answer. With more.";

  function queued() {
    const made = subject();
    const { presentation, clock } = made;
    presentation.turn("m-his-9", 5);
    const tenKey = presentation.offered(UNBOUND_MESSAGE) as number;
    presentation.started(tenKey, 1, "The first part. ");
    presentation.answered("m-his-9", TEN);
    presentation.offered(TEN);
    presentation.offered(TEN);
    presentation.allOffered(TEN); // or not seen at all: the next delivery replaced it
    clock.now += 2_000;
    presentation.ended(tenKey, 1);
    presentation.started(tenKey, 2, "The second part. ");
    // His queued words are committed; answer 10 is still playing.
    presentation.turn("m-his-11", 6);
    return { ...made, tenKey, TEN, TWELVE, TEN_TEXT, TWELVE_TEXT };
  }

  it("does not end the answer she is still speaking", () => {
    const { presentation } = queued();
    const ten = present(TEN_TEXT, TEN, presentation.answers);
    expect(ten.note).toBeNull();
    expect(ten.pacing).toBe(true);
    expect(ten.shown).toBe("The first part. The second part. ");
  });

  it("keeps each answer's segments with that answer", () => {
    const { presentation, clock, tenKey } = queued();
    const twelveKey = presentation.offered(UNBOUND_MESSAGE) as number;
    expect(twelveKey).not.toBe(tenKey);
    presentation.answered("m-his-11", TWELVE);
    // Answer 10's last segment plays, then answer 12's.
    clock.now += 2_000;
    presentation.ended(tenKey, 2);
    presentation.started(tenKey, 3, "The last part.");
    expect(present(TEN_TEXT, TEN, presentation.answers).shown).toBe(TEN_TEXT);
    expect(presentation.byKey(tenKey)?.state).toBe("complete");
    clock.now += 2_000;
    presentation.ended(tenKey, 3);
    presentation.started(twelveKey, 1, "Another answer. ");
    const twelve = present(TWELVE_TEXT, TWELVE, presentation.answers);
    expect(twelve.shown).toBe("Another answer. ");
    expect(twelve.note).toBeNull();
    expect(presentation.gaps(twelveKey)).toEqual([]);
    expect(presentation.gaps(tenKey).every((gap) => gap >= 0)).toBe(true);
  });

  it("does not stall an answer that is waiting its turn behind another's playback", () => {
    const { presentation, clock } = queued();
    presentation.offered(UNBOUND_MESSAGE);
    presentation.answered("m-his-11", TWELVE);
    // Answer 10's second segment plays on for a long sentence.
    clock.now += STALL_MS * 3;
    presentation.checkStall();
    expect(present(TWELVE_TEXT, TWELVE, presentation.answers).shown).toBe("");
    expect(present(TWELVE_TEXT, TWELVE, presentation.answers).note).toBeNull();
  });

  it("a bound segment of an older answer is never adopted by a newer one", () => {
    const { presentation, tenKey } = queued();
    presentation.answered("m-his-11", TWELVE);
    expect(presentation.offered(TEN)).toBe(tenKey);
    expect(presentation.messageIdOf(tenKey)).toBe(TEN);
  });
});

describe("a late segment cannot sound or reveal in the wrong turn", () => {
  it("a finished answer's repeated `completed` does not complete the next one early", () => {
    const { presentation } = subject();
    presentation.turn(HIS, 1);
    presentation.answered(HIS, HERS);
    const key = presentation.offered(HERS) as number;
    presentation.started(key, 1, ANSWER);
    presentation.allOffered(HERS);
    presentation.turn("m-his-next", 2);
    presentation.answered("m-his-next", "m-hers-next");
    presentation.allOffered(HERS); // still reported until the next delivery begins
    presentation.stopped(HERS, false);
    const next = presentation.offered("m-hers-next") as number;
    presentation.started(next, 1, "First. ");
    expect(presentation.current?.state).toBe("speaking");
    expect(present("First. Second.", "m-hers-next", presentation.answers).shown).toBe("First. ");
  });

  it("a stop with no written answer applies only to a delivery that handed us audio", () => {
    const { presentation } = subject();
    presentation.turn(HIS, 1);
    presentation.stopped(null, false);
    expect(presentation.current?.state).toBe("awaiting");
    presentation.offered(UNBOUND_MESSAGE);
    presentation.stopped(null, true);
    expect(presentation.current?.state).toBe("failed");
  });

  it("accepts nothing after the answer has been interrupted", () => {
    const { presentation, key } = speaking(1);
    presentation.stopped(HERS, false);
    expect(presentation.belongs(HERS)).toBe(false);
    expect(presentation.offered(HERS)).toBeNull();
    expect(presentation.started(key, 2, SEGMENTS[1]!)).toBeNull();
  });
});

describe("generated text is never stranded, and never presented as spoken", () => {
  it.each([
    ["interrupted", "Not spoken — Val was interrupted."],
    ["failed", "Not spoken — her voice failed; the text is complete."],
    ["released", "Not spoken — Voice ended."],
  ] as const)("%s: the rest appears at once, marked not spoken", (state, note) => {
    const { presentation, key } = speaking(1);
    if (state === "interrupted") presentation.stopped(HERS, false);
    else if (state === "failed") presentation.failed(key);
    else presentation.released();
    expect(shownOf(presentation)).toEqual({
      shown: SEGMENTS[0],
      unspoken: SEGMENTS[1]! + SEGMENTS[2]!,
      pacing: false,
      note,
    });
  });

  it("an output silent for the stall limit reveals the rest", () => {
    const { presentation, clock, key } = speaking(1);
    presentation.ended(key, 1);
    clock.now += STALL_MS - 1;
    presentation.checkStall();
    expect(presentation.current?.state).toBe("speaking");
    clock.now += 1;
    presentation.checkStall();
    expect(presentation.current?.state).toBe("stalled");
    expect(shownOf(presentation).unspoken).toBe(SEGMENTS[1]! + SEGMENTS[2]!);
  });

  it("a long sentence still playing is not a stall", () => {
    const { presentation, clock } = speaking(1);
    clock.now += STALL_MS * 3;
    presentation.checkStall();
    expect(presentation.current?.state).toBe("speaking");
  });

  it("an answer whose voice never starts is shown after the stall limit", () => {
    const { presentation, clock } = subject();
    presentation.turn(HIS, 1);
    presentation.answered(HIS, HERS);
    clock.now += STALL_MS;
    presentation.checkStall();
    expect(shownOf(presentation)).toMatchObject({ shown: "", unspoken: ANSWER });
  });

  it("an interruption after the last word adds no note", () => {
    const { presentation } = subject();
    presentation.turn(HIS, 1);
    presentation.answered(HIS, HERS);
    const key = presentation.offered(HERS) as number;
    presentation.started(key, 1, ANSWER);
    presentation.stopped(HERS, false);
    expect(shownOf(presentation).note).toBeNull();
  });
});

describe("the coordination figures", () => {
  it("reports each segment's text-after-playback offset and the gaps between segments", () => {
    const { presentation, clock } = subject(1_000);
    presentation.turn(HIS, 1);
    presentation.answered(HIS, HERS);
    const key = presentation.offered(HERS) as number;
    presentation.offered(HERS);
    clock.now = 2_000;
    presentation.started(key, 1, SEGMENTS[0]!);
    presentation.shown(HERS, SEGMENTS[0]!.length, 2_016);
    clock.now = 4_000;
    presentation.ended(key, 1);
    clock.now = 4_250;
    presentation.started(key, 2, SEGMENTS[1]!);
    presentation.shown(HERS, SEGMENTS[0]!.length + SEGMENTS[1]!.length, 4_262);
    expect(presentation.offsets(key)).toEqual([16, 12]);
    expect(presentation.gaps(key)).toEqual([250]);
  });
});
