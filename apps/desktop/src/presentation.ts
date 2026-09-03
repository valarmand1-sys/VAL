// How deliberation records may be described — invariant 29 as display logic.
//
// These are pure functions, tested directly, and they are the ONLY place the
// interface turns deliberation records into words. The two rules Lord Armand
// stated for this package (19 August 2026):
//
//   1. If ordering = contaminated, say so plainly and never present the
//      position as independently formed.
//   2. Never display held / updated / overridden / agreed_from_start until a
//      deliberations row actually supports it. Pending means pending.
//
// Rule 2 is structural before it is textual: `outcomeLabel` takes the
// deliberation-or-null, and the null branch has exactly one output. There is
// no code path from "no row" to an outcome word.

import type { BlindPositionView, DeliberationView, Outcome, TurnUnanswered } from "./api";

// An unanswered turn, described by what the record supports (ruled
// 2 September 2026). "The provider did not answer" is a claim of provider
// contact, and the interface may make it only where the durable call
// lifecycle carries a call for this turn. A refusal before contact — the
// ceiling, no eligible route — is stated as exactly that.
export function describeUnanswered(outcome: TurnUnanswered): string {
  if (outcome.provider_contacted) {
    return `The provider did not answer: ${outcome.error}. The question is history.`;
  }
  return (
    `No answer — the call was refused before any provider was contacted ` +
    `(${outcome.error_kind}): ${outcome.error}. The question is history.`
  );
}

export const OUTCOME_WORDS: Record<Outcome, string> = {
  held: "she held",
  updated: "she updated",
  overridden: "overridden by Lord Armand",
  agreed_from_start: "agreed from the start",
};

export function orderingLabel(record: BlindPositionView | DeliberationView): string {
  // The recorded ordering, verbatim in meaning. A contaminated position is
  // named as such — a contaminated position labelled clean is the failure the
  // whole mechanism exists to prevent, and that includes labels.
  if (record.ordering === "contaminated") {
    return "contaminated — the preference could not be separated; this position was NOT independently formed";
  }
  return "formed blind, before exposure to the stated preference";
}

export function confidenceLabel(confidence: "high" | "medium" | "low"): string {
  return { high: "high confidence", medium: "medium confidence", low: "low confidence" }[
    confidence
  ];
}

export function outcomeLabel(deliberation: DeliberationView | null): string {
  // No row, no outcome. "Pending" is the only thing the record supports, so
  // it is the only thing this function can say (invariant 29).
  if (deliberation === null) {
    return "outcome: pending — not yet resolved in the record";
  }
  const word = OUTCOME_WORDS[deliberation.outcome];
  if (deliberation.outcome === "updated" && deliberation.what_changed_her_mind !== null) {
    return `${word} — what moved her: ${deliberation.what_changed_her_mind}`;
  }
  return word;
}

export function captureLabel(capturedAs: "consequential" | "uncertain" | null): string | null {
  // An uncaptured exchange shows nothing at all: absence of machinery is not
  // a state to announce, and announcing it would bury the captures that are.
  if (capturedAs === null) return null;
  return capturedAs === "uncertain"
    ? "captured as uncertain — borderline, kept for tuning"
    : "consequential";
}

export interface DeliberationDisplay {
  capture: string;
  position: string;
  confidence: string;
  reasoning: string;
  ordering: string;
  contaminated: boolean;
  outcome: string;
  strippedPreference: string | null;
}

export function describeDeliberation(
  capturedAs: "consequential" | "uncertain",
  blind: BlindPositionView,
  deliberation: DeliberationView | null,
): DeliberationDisplay {
  return {
    capture: captureLabel(capturedAs) ?? "",
    position: blind.position,
    confidence: confidenceLabel(blind.confidence),
    reasoning: blind.reasoning,
    ordering: orderingLabel(blind),
    contaminated: blind.ordering === "contaminated",
    outcome: outcomeLabel(deliberation),
    strippedPreference: blind.stripped_content.trim() === "" ? null : blind.stripped_content,
  };
}

// The deliberation that resolves a given blind position, if the record holds
// one. Matching is by the explicit link, never by proximity or guesswork.
export function resolutionOf(
  blind: BlindPositionView,
  deliberations: DeliberationView[],
): DeliberationView | null {
  return deliberations.find((d) => d.blind_position_id === blind.id) ?? null;
}
