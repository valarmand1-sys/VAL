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
// **One record per answer** (targeted voice latency order, 25 September 2026). In his
// successful session he spoke while she was still thinking; his words were committed
// as a new turn while her previous answer was still being spoken, for 44 s. A single
// "current answer" ended the one she was speaking — marking its remaining text "not
// spoken" while she spoke it — and let its later segments be absorbed into the new
// turn. Each answer now keeps its own record: a new turn ends nothing, a segment
// belongs to the answer that took it when it was offered (its `key`), and an answer
// waiting behind another's playback is not "stalled".
//
// Failure is explicit rather than silent: an interruption, a failed or stalled
// delivery, or Voice ending reveals the rest at once, marked as not spoken — generated
// text is never stranded, and never presented as heard.

/** The id a segment carries when it was voiced before her answer was written. */
export const UNBOUND_MESSAGE = "00000000-0000-0000-0000-000000000000";

/** No playback activity at all for this long, with text waiting, means speech has stalled. */
export const STALL_MS = 12_000;

/** How many answers are remembered; the oldest finished ones are forgotten first. */
const REMEMBERED = 6;

/**
 * How long past its own audio's length a started segment still counts as playing
 * when the device never says it ended. Not a pacing timer: it only stops a lost
 * end event from holding the stall fallback off indefinitely.
 */
export const END_GRACE_MS = 3_000;

export type SpokenState =
  | "awaiting" // her answer exists; no segment of it has started playing yet
  | "speaking" // segments are playing; text follows them
  | "complete" // every segment has started: the whole answer is shown
  | "interrupted" // stopped — barge-in; the rest was not spoken
  | "failed" // synthesis or playback failed; the rest was not spoken
  | "stalled" // no playback activity for STALL_MS; the rest is shown, not yet spoken
  | "released"; // Voice ended; the rest was not spoken

export interface SpokenSegment {
  index: number;
  text: string;
  startedAt: number;
  /** The device said it finished playing. */
  endedAt: number | null;
  /** Its playback was cut off: interrupted, failed, or Voice ended. */
  stoppedAt: number | null;
  /** When its audio should have finished, if its length is known. */
  expectedEndAt: number | null;
  shownAt: number | null;
}

export interface SpokenAnswer {
  /** This window's own handle for the answer, carried by each of its segments. */
  key: number;
  /** Her message, once known; `null` while every segment so far was voiced unbound. */
  messageId: string | null;
  /** His message this answers. */
  turn: string | null;
  /** The service's utterance number of his message, for the timing report. */
  utterance: number | null;
  state: SpokenState;
  /** The segments that have started playing, in order. */
  segments: SpokenSegment[];
  /** Their text, concatenated: always a prefix of the canonical answer. */
  revealed: string;
  offered: number;
  allOffered: boolean;
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

export function isTerminal(answer: SpokenAnswer | null | undefined): boolean {
  return answer !== null && answer !== undefined && TERMINAL.has(answer.state);
}

/**
 * How one message should be displayed, given the spoken answers being paced.
 *
 * Anything that is not a paced answer is shown whole, exactly as before: ordinary
 * text presentation is unchanged. If the revealed text is somehow not a prefix of the
 * canonical content, the whole message is shown — never a mangled one.
 */
export function present(
  content: string,
  messageId: string,
  answers: readonly SpokenAnswer[] | SpokenAnswer | null,
): Presented {
  const whole: Presented = { shown: content, unspoken: "", pacing: false, note: null };
  const list: readonly SpokenAnswer[] =
    answers === null ? [] : Array.isArray(answers) ? answers : [answers as SpokenAnswer];
  const answer = list.find((candidate) => candidate.messageId === messageId);
  if (answer === undefined) return whole;
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
  private list: SpokenAnswer[] = [];
  /** Streamed audio that arrived for a segment before the segment began playing. */
  private earlyAudio = new Map<string, number>();
  private nextKey = 1;
  /** Any segment offered, started or ended, of any answer: the stall clock. */
  private lastActivityAt: number;

  constructor(
    private readonly onChange: (answers: SpokenAnswer[]) => void,
    private readonly now: () => number,
  ) {
    this.lastActivityAt = now();
  }

  /** Every remembered answer, oldest first — copies, for rendering. */
  get answers(): SpokenAnswer[] {
    return this.list.map(copy);
  }

  /** The newest answer: the one his most recent turn will be given. */
  get current(): SpokenAnswer | null {
    return this.list.at(-1) ?? null;
  }

  byKey(key: number | undefined): SpokenAnswer | null {
    return this.list.find((answer) => answer.key === key) ?? null;
  }

  /** Her message a segment belongs to, as far as this window knows it yet. */
  messageIdOf(key: number | undefined): string | null {
    return this.byKey(key)?.messageId ?? null;
  }

  /** His message is committed: a new turn. **It ends nothing already being spoken.** */
  turn(ownerMessageId: string, utterance: number | null = null): void {
    if (this.list.some((answer) => answer.turn === ownerMessageId)) return;
    this.list.push({
      key: this.nextKey++,
      messageId: null,
      turn: ownerMessageId,
      utterance,
      state: "awaiting",
      segments: [],
      revealed: "",
      offered: 0,
      allOffered: false,
    });
    this.lastActivityAt = this.now();
    this.forget();
    this.emit();
  }

  /** Her answer to that turn is written: its id, for the thread to pace. */
  answered(ownerMessageId: string, messageId: string): void {
    let answer = this.list.find((candidate) => candidate.turn === ownerMessageId);
    if (answer === undefined) {
      this.turn(ownerMessageId);
      answer = this.list.at(-1) as SpokenAnswer;
    }
    if (answer.messageId === messageId) return;
    // Never two answers under one id.
    if (answer.messageId === null && !this.list.some((other) => other.messageId === messageId)) {
      answer.messageId = messageId;
      this.lastActivityAt = this.now();
      this.emit();
    }
  }

  /**
   * A segment has been collected: which answer takes it, or `null` if none may —
   * a segment of an answer that has ended is neither played nor revealed.
   *
   * An unbound segment was voiced before her answer was written, which only the
   * newest turn's delivery can do. A bound one belongs to the answer with that id;
   * one no answer here has seen is adopted by the newest answer still unnamed.
   */
  offered(messageId: string): number | null {
    const answer = this.route(messageId);
    if (answer === null) return null;
    if (messageId !== UNBOUND_MESSAGE && answer.messageId === null) answer.messageId = messageId;
    answer.offered += 1;
    this.lastActivityAt = this.now();
    return answer.key;
  }

  /** Whether a segment would be taken (without taking it). */
  belongs(messageId: string): boolean {
    return this.route(messageId) !== null;
  }

  /** The delivery of this answer says every segment has been handed over. */
  allOffered(deliveryMessageId: string | null): void {
    const answer = this.concerned(deliveryMessageId);
    if (answer === null) return;
    answer.allOffered = true;
    this.completeIfDone(answer);
  }

  /**
   * The delivery of this answer stopped: interrupted, or failed. Its playback is cut
   * off even when every word of it had already started — a complete answer's last
   * segment can still be sounding, and the player has just stopped it.
   */
  stopped(deliveryMessageId: string | null, failed: boolean): void {
    const named =
      deliveryMessageId === null || deliveryMessageId === UNBOUND_MESSAGE
        ? null
        : (this.list.find((candidate) => candidate.messageId === deliveryMessageId) ?? null);
    if (named !== null) this.stopPlayback(named);
    const answer = this.concerned(deliveryMessageId);
    if (answer === null) return;
    this.finish(answer, failed ? "failed" : "interrupted");
  }

  started(
    key: number | undefined,
    index: number,
    text: string,
    durationMs: number | null = null,
  ): number | null {
    const answer = this.byKey(key);
    if (answer === null || isTerminal(answer)) return null;
    if (answer.segments.some((segment) => segment.index === index)) return null;
    const at = this.now();
    const early = this.earlyAudio.get(`${key}:${index}`) ?? 0;
    this.earlyAudio.delete(`${key}:${index}`);
    answer.segments.push({
      index,
      text,
      startedAt: at,
      endedAt: null,
      stoppedAt: null,
      expectedEndAt: durationMs === null ? null : at + durationMs + early,
      shownAt: null,
    });
    answer.revealed += text;
    answer.state = "speaking";
    this.lastActivityAt = at;
    this.emit();
    this.completeIfDone(answer);
    return at;
  }

  /**
   * More of a streamed segment has arrived: its audio will run this much longer.
   * Keeps the lost-end-event bound tied to the segment's real length.
   */
  extend(key: number | undefined, index: number, moreMs: number): void {
    const segment = this.byKey(key)?.segments.find((item) => item.index === index);
    if (segment !== undefined) {
      if (segment.expectedEndAt !== null) segment.expectedEndAt += moreMs;
      return;
    }
    const pending = `${key}:${index}`;
    this.earlyAudio.set(pending, (this.earlyAudio.get(pending) ?? 0) + moreMs);
  }

  /** The device cut this segment off (barge-in, or the player stopped). */
  playbackStopped(key: number | undefined, index: number): void {
    const answer = this.byKey(key);
    const segment = answer?.segments.find((item) => item.index === index);
    if (segment === undefined) return;
    const at = this.now();
    if (segment.endedAt === null && segment.stoppedAt === null) segment.stoppedAt = at;
    this.lastActivityAt = at;
  }

  ended(key: number | undefined, index: number): void {
    const answer = this.byKey(key);
    if (answer === null) return;
    const segment = answer.segments.find((item) => item.index === index);
    const at = this.now();
    if (segment !== undefined && segment.endedAt === null) segment.endedAt = at;
    this.lastActivityAt = at;
  }

  /** The thread's React commit that first showed this many revealed characters. */
  shown(messageId: string, revealedLength: number, at: number): void {
    const answer = this.list.find((candidate) => candidate.messageId === messageId);
    if (answer === undefined) return;
    let covered = 0;
    for (const segment of answer.segments) {
      covered += segment.text.length;
      if (covered <= revealedLength && segment.shownAt === null) segment.shownAt = at;
    }
  }

  /** A segment's playback failed: that answer's remaining text is shown, not spoken. */
  failed(key?: number): void {
    const answer = key === undefined ? this.current : this.byKey(key);
    if (answer === null) return;
    this.stopPlayback(answer);
    this.finish(answer, "failed");
  }

  /** Voice ended: nothing plays any more, and every paced answer shows the rest, not spoken. */
  released(): void {
    for (const answer of this.list) {
      this.stopPlayback(answer);
      this.finish(answer, "released");
    }
  }

  /**
   * Is any segment of any answer — finished revealing or not — still sounding?
   *
   * `complete` is a statement about text: every segment has *started*. It says
   * nothing about the last one having finished, so playback is judged here, from
   * the segments themselves, and never from an answer's state.
   */
  playing(): boolean {
    const now = this.now();
    return this.list.some((answer) => answer.segments.some((segment) => isPlaying(segment, now)));
  }

  /**
   * Called on every session poll. Only a silence of the whole output — no segment of
   * any answer offered, started or ended for `STALL_MS`, and none still playing —
   * stalls an answer. One waiting its turn behind another's playback is not stalled.
   */
  checkStall(): void {
    if (this.playing()) return;
    // Silence is measured from the last activity, or from when the last segment
    // should have finished if its end was never reported.
    const lastEnd = Math.max(
      this.lastActivityAt,
      ...this.list.flatMap((answer) =>
        answer.segments
          .filter((segment) => segment.endedAt === null && segment.stoppedAt === null)
          .map((segment) => (segment.expectedEndAt ?? segment.startedAt) + END_GRACE_MS),
      ),
    );
    if (this.now() - lastEnd < STALL_MS) return;
    for (const answer of this.list) {
      if (answer.messageId !== null) this.finish(answer, "stalled");
    }
  }

  /** Text reveal less playback start, per segment, in ms — where the DOM has confirmed it. */
  offsets(key?: number): number[] {
    return (this.pick(key)?.segments ?? [])
      .filter((segment) => segment.shownAt !== null)
      .map((segment) => Math.round((segment.shownAt as number) - segment.startedAt));
  }

  /** The silence between consecutive segments: next start less previous end, in ms. */
  gaps(key?: number): number[] {
    const segments = this.pick(key)?.segments ?? [];
    const out: number[] = [];
    for (let i = 1; i < segments.length; i += 1) {
      const previous = segments[i - 1] as SpokenSegment;
      const next = segments[i] as SpokenSegment;
      if (previous.endedAt !== null) out.push(Math.round(next.startedAt - previous.endedAt));
    }
    return out;
  }

  private pick(key?: number): SpokenAnswer | null {
    return key === undefined ? this.current : this.byKey(key);
  }

  private route(messageId: string): SpokenAnswer | null {
    if (messageId === UNBOUND_MESSAGE) {
      const newest = this.current;
      return newest !== null && !isTerminal(newest) ? newest : null;
    }
    const named = this.list.find((answer) => answer.messageId === messageId);
    if (named !== undefined) return isTerminal(named) ? null : named;
    for (let i = this.list.length - 1; i >= 0; i -= 1) {
      const answer = this.list[i] as SpokenAnswer;
      if (answer.messageId === null && !isTerminal(answer)) return answer;
    }
    return null;
  }

  /**
   * The answer a delivery state is about. The service repeats a delivery's state on
   * every poll until the next delivery replaces it, so the previous answer's
   * `completed` or stop must never land on the new one.
   */
  private concerned(deliveryMessageId: string | null): SpokenAnswer | null {
    if (deliveryMessageId === null || deliveryMessageId === UNBOUND_MESSAGE) {
      // An unwritten answer's delivery: only the newest, and only once it has
      // handed this window audio.
      const newest = this.current;
      return newest !== null &&
        !isTerminal(newest) &&
        newest.messageId === null &&
        newest.offered > 0
        ? newest
        : null;
    }
    const answer = this.list.find((candidate) => candidate.messageId === deliveryMessageId);
    return answer !== undefined && !isTerminal(answer) ? answer : null;
  }

  private completeIfDone(answer: SpokenAnswer): void {
    if (isTerminal(answer)) return;
    if (answer.allOffered && answer.segments.length >= answer.offered && answer.offered > 0) {
      answer.state = "complete";
      this.emit();
    }
  }

  private finish(answer: SpokenAnswer, state: SpokenState): void {
    if (isTerminal(answer)) return;
    if (state === "interrupted" || state === "failed" || state === "released") {
      this.stopPlayback(answer);
    }
    answer.state = state;
    this.emit();
  }

  /** Every segment of this answer still sounding has been cut off. */
  private stopPlayback(answer: SpokenAnswer): void {
    const at = this.now();
    for (const segment of answer.segments) {
      if (segment.endedAt === null && segment.stoppedAt === null) {
        segment.stoppedAt = at;
        this.lastActivityAt = at;
      }
    }
  }

  /**
   * Forget the oldest finished answers beyond `REMEMBERED` — never one whose audio
   * is still sounding, which is still needed to know that something is playing.
   */
  private forget(): void {
    const now = this.now();
    while (this.list.length > REMEMBERED) {
      const index = this.list.findIndex(
        (answer) => isTerminal(answer) && !answer.segments.some((segment) => isPlaying(segment, now)),
      );
      if (index < 0) break;
      this.list.splice(index, 1);
    }
  }

  private emit(): void {
    this.onChange(this.answers);
  }
}

/** Started, not reported finished, not cut off, and not long past its own length. */
function isPlaying(segment: SpokenSegment, now: number): boolean {
  if (segment.endedAt !== null || segment.stoppedAt !== null) return false;
  return segment.expectedEndAt === null || now < segment.expectedEndAt + END_GRACE_MS;
}

function copy(answer: SpokenAnswer): SpokenAnswer {
  return { ...answer, segments: answer.segments.map((segment) => ({ ...segment })) };
}
