// Her words, shown as she says them — owner order, 25 September 2026 (Voice-mode repair §4).
//
// His stated preference: "VAL's displayed answer should progress with the
// corresponding speech." Not the whole answer seconds before she speaks, and not her
// speech half-way through (or finished) before its text appears. Before this, the
// desktop read her answer only once every segment had been synthesised, which put
// the text mid-way through a two-segment answer and near the end of a three-segment
// one — exactly what he saw.
//
// So each segment's text is revealed when **that segment's playback starts** — the
// strongest boundary this window has (`SpeechPlayer.onStarted`, the moment the buffer
// is scheduled on the output device). Not at synthesis, not at download, not by a
// timer or an estimated speaking rate. Segments are the delivery's own: contiguous
// slices of the visible answer, in order, covering it exactly, so what is revealed is
// always a prefix of the canonical message and reconciles into it without duplicates.
//
// Failure is explicit rather than silent: an interruption, a failed or stalled
// delivery, or Voice ending reveals the rest at once, marked as not spoken — generated
// text is never stranded, and never presented as heard.

/** The id a segment carries when it was voiced before her answer was written. */
export const UNBOUND_MESSAGE = "00000000-0000-0000-0000-000000000000";

/** No playback progress for this long, with text waiting, means speech has stalled. */
export const STALL_MS = 12_000;

export type SpokenState =
  | "awaiting" // her answer exists; no segment has started playing yet
  | "speaking" // segments are playing; text follows them
  | "complete" // every segment has started: the whole answer is shown
  | "interrupted" // stopped — barge-in; the rest was not spoken
  | "failed" // synthesis or playback failed; the rest was not spoken
  | "stalled" // no progress for STALL_MS; the rest is shown, not yet spoken
  | "released"; // Voice ended; the rest was not spoken

export interface SpokenSegment {
  index: number;
  text: string;
  startedAt: number;
  endedAt: number | null;
  shownAt: number | null;
}

export interface SpokenAnswer {
  /** Her message, once known; `null` while every segment so far was voiced unbound. */
  messageId: string | null;
  /** His message this answers — what keeps a late segment out of the wrong turn. */
  turn: string | null;
  state: SpokenState;
  /** The segments that have started playing, in order. */
  segments: SpokenSegment[];
  /** Their text, concatenated: always a prefix of the canonical answer. */
  revealed: string;
  offered: number;
  allOffered: boolean;
  lastProgressAt: number;
}

export interface Presented {
  /** What is on screen as said (or being said). */
  shown: string;
  /** Generated but not spoken — shown only once speech can no longer carry it. */
  unspoken: string;
  /** True while text is being paced to her speech. */
  pacing: boolean;
  note: string | null;
}

const TERMINAL: ReadonlySet<SpokenState> = new Set([
  "complete",
  "interrupted",
  "failed",
  "stalled",
  "released",
]);

const NOTES: Partial<Record<SpokenState, string>> = {
  interrupted: "Not spoken — Val was interrupted.",
  failed: "Not spoken — her voice failed; the text is complete.",
  stalled: "Her voice is delayed; the text is shown in full.",
  released: "Not spoken — Voice ended.",
};

export function isTerminal(answer: SpokenAnswer | null): boolean {
  return answer !== null && TERMINAL.has(answer.state);
}

/**
 * How one message should be displayed, given the spoken answer being paced.
 *
 * Anything other than the paced answer is shown whole, exactly as before: ordinary
 * text presentation is unchanged. If the revealed text is somehow not a prefix of the
 * canonical content, the whole message is shown — never a mangled one.
 */
export function present(content: string, messageId: string, answer: SpokenAnswer | null): Presented {
  const whole: Presented = { shown: content, unspoken: "", pacing: false, note: null };
  if (answer === null || answer.messageId !== messageId) return whole;
  if (!content.startsWith(answer.revealed)) return whole;
  if (answer.state === "complete") return whole;
  if (answer.state === "awaiting" || answer.state === "speaking") {
    return { shown: answer.revealed, unspoken: "", pacing: true, note: null };
  }
  const unspoken = content.slice(answer.revealed.length);
  return {
    shown: answer.revealed,
    unspoken,
    pacing: false,
    note: unspoken.trim() === "" ? null : (NOTES[answer.state] ?? null),
  };
}

/**
 * The state machine behind `present`. Every input is a playback or delivery fact;
 * none is a clock guess, except the stall check, which only ever reveals *more*.
 */
export class SpokenPresentation {
  private answer: SpokenAnswer | null = null;

  constructor(
    private readonly onChange: (answer: SpokenAnswer | null) => void,
    private readonly now: () => number,
  ) {}

  get current(): SpokenAnswer | null {
    return this.answer;
  }

  /** His message is committed: a new turn. Anything still pacing ends, unspoken. */
  turn(ownerMessageId: string): void {
    if (this.answer !== null && this.answer.turn === ownerMessageId) return;
    if (this.answer !== null && !isTerminal(this.answer)) this.finish("released");
    this.answer = {
      messageId: null,
      turn: ownerMessageId,
      state: "awaiting",
      segments: [],
      revealed: "",
      offered: 0,
      allOffered: false,
      lastProgressAt: this.now(),
    };
    this.emit();
  }

  /** Her answer to that turn is written: its id, for the thread to pace. */
  answered(ownerMessageId: string, messageId: string): void {
    if (this.answer === null || this.answer.turn !== ownerMessageId) this.turn(ownerMessageId);
    const answer = this.answer as SpokenAnswer;
    if (answer.messageId === messageId) return;
    answer.messageId = messageId;
    answer.lastProgressAt = this.now();
    this.emit();
  }

  /** Whether a segment belongs to the answer being paced (or may be adopted by it). */
  belongs(messageId: string): boolean {
    const answer = this.answer;
    if (answer === null || isTerminal(answer)) return false;
    return messageId === UNBOUND_MESSAGE || answer.messageId === null || answer.messageId === messageId;
  }

  offered(messageId: string): void {
    if (!this.belongs(messageId)) return;
    const answer = this.answer as SpokenAnswer;
    if (messageId !== UNBOUND_MESSAGE && answer.messageId === null) answer.messageId = messageId;
    answer.offered += 1;
    answer.lastProgressAt = this.now();
  }

  /**
   * Whether a delivery's reported state concerns the answer being paced. The service
   * repeats a delivery's state on every poll until the next delivery replaces it, so
   * the previous answer's `completed` or stop is still being reported while his next
   * turn is thought about — and must not land on the new answer.
   */
  concerns(deliveryMessageId: string | null): boolean {
    const answer = this.answer;
    if (answer === null || isTerminal(answer)) return false;
    if (deliveryMessageId === null || deliveryMessageId === UNBOUND_MESSAGE) {
      // An unwritten answer's delivery: only one that has already handed us audio.
      return answer.messageId === null && answer.offered > 0;
    }
    return answer.messageId === deliveryMessageId;
  }

  /** The delivery of this answer says every segment has been handed over. */
  allOffered(deliveryMessageId: string | null): void {
    if (!this.concerns(deliveryMessageId)) return;
    const answer = this.answer as SpokenAnswer;
    answer.allOffered = true;
    this.completeIfDone();
  }

  /** The delivery of this answer stopped: interrupted, or failed. */
  stopped(deliveryMessageId: string | null, failed: boolean): void {
    if (!this.concerns(deliveryMessageId)) return;
    this.finish(failed ? "failed" : "interrupted");
  }

  started(messageId: string, index: number, text: string): number | null {
    if (!this.belongs(messageId)) return null;
    const answer = this.answer as SpokenAnswer;
    if (messageId !== UNBOUND_MESSAGE && answer.messageId === null) answer.messageId = messageId;
    if (answer.segments.some((segment) => segment.index === index)) return null;
    const at = this.now();
    answer.segments.push({ index, text, startedAt: at, endedAt: null, shownAt: null });
    answer.revealed += text;
    answer.state = "speaking";
    answer.lastProgressAt = at;
    this.emit();
    this.completeIfDone();
    return at;
  }

  ended(messageId: string, index: number): void {
    const answer = this.answer;
    if (answer === null) return;
    if (messageId !== UNBOUND_MESSAGE && answer.messageId !== null && answer.messageId !== messageId) {
      return;
    }
    const segment = answer.segments.find((item) => item.index === index);
    if (segment !== undefined && segment.endedAt === null) segment.endedAt = this.now();
    answer.lastProgressAt = this.now();
  }

  /** The thread's React commit that first showed this many revealed characters. */
  shown(messageId: string, revealedLength: number, at: number): void {
    const answer = this.answer;
    if (answer === null || answer.messageId !== messageId) return;
    let covered = 0;
    for (const segment of answer.segments) {
      covered += segment.text.length;
      if (covered <= revealedLength && segment.shownAt === null) segment.shownAt = at;
    }
  }

  interrupted(): void {
    this.finish("interrupted");
  }

  failed(): void {
    this.finish("failed");
  }

  released(): void {
    this.finish("released");
  }

  /** Called on every session poll: a delivery that has stopped moving reveals the rest. */
  checkStall(): void {
    const answer = this.answer;
    if (answer === null || isTerminal(answer) || answer.messageId === null) return;
    // A segment still playing is progress, however long the sentence: only a wait
    // for the *next* segment to begin can be a stall.
    const last = answer.segments.at(-1);
    if (last !== undefined && last.endedAt === null) return;
    if (this.now() - answer.lastProgressAt >= STALL_MS) this.finish("stalled");
  }

  /** Text reveal less playback start, per segment, in ms — where the DOM has confirmed it. */
  offsets(): number[] {
    return (this.answer?.segments ?? [])
      .filter((segment) => segment.shownAt !== null)
      .map((segment) => Math.round((segment.shownAt as number) - segment.startedAt));
  }

  /** The silence between consecutive segments: next start less previous end, in ms. */
  gaps(): number[] {
    const segments = this.answer?.segments ?? [];
    const out: number[] = [];
    for (let i = 1; i < segments.length; i += 1) {
      const previous = segments[i - 1] as SpokenSegment;
      const next = segments[i] as SpokenSegment;
      if (previous.endedAt !== null) out.push(Math.round(next.startedAt - previous.endedAt));
    }
    return out;
  }

  private completeIfDone(): void {
    const answer = this.answer;
    if (answer === null || isTerminal(answer)) return;
    if (answer.allOffered && answer.segments.length >= answer.offered && answer.offered > 0) {
      answer.state = "complete";
      this.emit();
    }
  }

  private finish(state: SpokenState): void {
    const answer = this.answer;
    if (answer === null || isTerminal(answer)) return;
    answer.state = state;
    this.emit();
  }

  private emit(): void {
    const answer = this.answer;
    this.onChange(answer === null ? null : { ...answer, segments: [...answer.segments] });
  }
}
