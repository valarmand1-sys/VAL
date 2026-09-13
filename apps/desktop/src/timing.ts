// Turn timing and stage progress, as words — ruling, 13 September 2026.
//
// Pure functions, tested directly. Two rules govern them:
//
//   1. Figures measured from different starting points are never shown as if
//      they shared one. Everything "from Send" is measured from the moment Lord
//      Armand sent the message. The response call's time to first token is
//      measured from the start of that call alone, after all the work before it,
//      and is labelled separately.
//   2. Progress is presentation of backend-confirmed state. It is not Val's
//      answer, carries no content, and does not count toward the 1–2 second
//      generated-text requirement. It makes a necessary wait legible.
//
// The 10-second delta-to-paint gap of 13 September is undiagnosed. The window
// visibility recorded here is instrumentation for that question, not an answer
// to it.

export type TurnStage = "understanding" | "forming_view" | "preparing_response";

export const STAGE_WORDS: Record<TurnStage, string> = {
  understanding: "Considering your message…",
  forming_view: "Forming an independent view before answering…",
  preparing_response: "Preparing a response…",
};

export const PROGRESS_NOTE =
  "Progress shows what the house is doing while it works. It is not Val's answer, and it " +
  "does not count toward the 1–2 second responsiveness requirement.";

export interface VisibilityChange {
  atMs: number;
  visible: boolean;
}

// One turn's client-side moments, all in milliseconds from Send.
export interface TurnClock {
  responseStartedMs: number | null;
  firstDeltaMs: number | null;
  firstDeltaVisible: boolean | null;
  firstRenderMs: number | null;
  firstRenderVisible: boolean | null;
  firstPaintMs: number | null;
  firstPaintVisible: boolean | null;
  visibilityChanges: VisibilityChange[];
}

export function newTurnClock(): TurnClock {
  return {
    responseStartedMs: null,
    firstDeltaMs: null,
    firstDeltaVisible: null,
    firstRenderMs: null,
    firstRenderVisible: null,
    firstPaintMs: null,
    firstPaintVisible: null,
    visibilityChanges: [],
  };
}

export interface TurnTimingReport {
  clock: TurnClock;
  completeMs: number;
  // Measured by the gateway from the start of the final response call.
  responseCallFirstTokenMs: number | null;
  // Measured by the service from its receipt of the request.
  serviceResponseStartedMs: number | null;
}

function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(2)} s`;
}

export interface TimingLines {
  fromSend: string;
  responseCall: string | null;
  visibility: string | null;
}

export function timingLines(report: TurnTimingReport): TimingLines {
  const { clock } = report;
  const parts: string[] = [];
  if (clock.responseStartedMs !== null) {
    parts.push(`work before Val began answering ${seconds(clock.responseStartedMs)}`);
  } else if (report.serviceResponseStartedMs !== null) {
    parts.push(
      `work before Val began answering ${seconds(report.serviceResponseStartedMs)} (measured at the service)`,
    );
  }
  parts.push(
    clock.firstDeltaMs === null
      ? "no text was streamed"
      : `first text received ${seconds(clock.firstDeltaMs)}`,
  );
  if (clock.firstPaintMs !== null) {
    parts.push(`first words painted ${seconds(clock.firstPaintMs)}`);
  }
  parts.push(`complete ${seconds(report.completeMs)}`);

  const responseCall =
    report.responseCallFirstTokenMs === null
      ? null
      : `Response call alone, from its own start: first token after ${seconds(report.responseCallFirstTokenMs)}.`;

  return {
    fromSend: `From Send: ${parts.join(" · ")}.`,
    responseCall,
    visibility: visibilityLine(clock),
  };
}

// Says only what was recorded: whether the window was visible at each moment,
// and when it became visible again if it was not.
export function visibilityLine(clock: TurnClock): string | null {
  const hiddenAt: string[] = [];
  if (clock.firstDeltaVisible === false) hiddenAt.push("the first text arrived");
  if (clock.firstRenderVisible === false) hiddenAt.push("it was rendered");
  if (clock.firstPaintVisible === false) hiddenAt.push("it was painted");
  const after = clock.firstDeltaMs ?? 0;
  const shown = clock.visibilityChanges.find((change) => change.visible && change.atMs >= after);
  if (hiddenAt.length === 0) {
    return clock.visibilityChanges.some((change) => !change.visible)
      ? "The window was hidden for part of this turn, but visible when the first words arrived and were painted."
      : null;
  }
  const became = shown === undefined ? "" : ` It became visible at ${seconds(shown.atMs)}.`;
  return `The window was not visible when ${hiddenAt.join(", when ")}.${became}`;
}
