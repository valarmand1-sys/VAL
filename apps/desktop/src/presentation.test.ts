// Invariant 29 at the display layer — the two rulings of 19 August 2026,
// tested against the only functions allowed to turn deliberation records into
// words. The service tests prove the payloads cannot carry unsupported
// states; these prove the rendering cannot add one.

import { describe, expect, it } from "vitest";

import type { BlindPositionView, DeliberationView } from "./api";
import {
  OUTCOME_WORDS,
  describeDeliberation,
  describeUnanswered,
  orderingLabel,
  outcomeLabel,
  resolutionOf,
} from "./presentation";

function blind(overrides: Partial<BlindPositionView> = {}): BlindPositionView {
  return {
    id: "blind-1",
    message_id: "message-1",
    position: "Open on the close-up: the film is about her hands.",
    confidence: "medium",
    reasoning: "The wide shot delays meeting the subject.",
    stripped_content: "I think we should open on the wide shot.",
    ordering: "enforced",
    independently_formed: true,
    classification: "consequential",
    classified_by: "automatic",
    created_at: "2026-08-19T12:00:00Z",
    ...overrides,
  };
}

function deliberation(overrides: Partial<DeliberationView> = {}): DeliberationView {
  return {
    id: "deliberation-1",
    message_id: "message-1",
    position: "Open on the close-up.",
    confidence: "medium",
    reasoning: "Brief.",
    stripped_content: "",
    ordering: "enforced",
    independently_formed: true,
    user_response: "I still prefer the wide shot.",
    outcome: "held",
    what_changed_her_mind: null,
    both_positions: null,
    predictions: null,
    classification: "consequential",
    classified_by: "automatic",
    blind_position_id: "blind-1",
    created_at: "2026-08-19T12:00:05Z",
    ...overrides,
  };
}

describe("pending means pending", () => {
  it("shows no outcome word when no deliberations row exists", () => {
    const label = outcomeLabel(null);
    expect(label).toContain("pending");
    for (const word of Object.values(OUTCOME_WORDS)) {
      expect(label).not.toContain(word);
    }
  });

  it("shows the recorded outcome once the row exists", () => {
    expect(outcomeLabel(deliberation({ outcome: "held" }))).toBe("she held");
    expect(outcomeLabel(deliberation({ outcome: "agreed_from_start" }))).toBe(
      "agreed from the start",
    );
    expect(outcomeLabel(deliberation({ outcome: "overridden" }))).toContain("overridden");
  });

  it("an update carries what moved her", () => {
    const label = outcomeLabel(
      deliberation({ outcome: "updated", what_changed_her_mind: "the point about scale" }),
    );
    expect(label).toContain("she updated");
    expect(label).toContain("the point about scale");
  });

  it("resolution is matched by the recorded link, never by proximity", () => {
    const stray = deliberation({ id: "other", blind_position_id: "some-other-blind" });
    expect(resolutionOf(blind(), [stray])).toBeNull();
    const linked = deliberation();
    expect(resolutionOf(blind(), [stray, linked])).toBe(linked);
  });
});

describe("contamination is named, never dressed up", () => {
  it("an enforced position is described as formed blind", () => {
    expect(orderingLabel(blind())).toContain("formed blind");
  });

  it("a contaminated position says so and never claims independence", () => {
    const label = orderingLabel(blind({ ordering: "contaminated", independently_formed: false }));
    expect(label).toContain("contaminated");
    expect(label).toContain("NOT independently formed");
    expect(label).not.toContain("formed blind");
  });

  it("the full display keeps both rules at once", () => {
    const display = describeDeliberation(
      "consequential",
      blind({ ordering: "contaminated", independently_formed: false, stripped_content: "" }),
      null,
    );
    expect(display.contaminated).toBe(true);
    expect(display.ordering).toContain("contaminated");
    expect(display.outcome).toContain("pending");
    expect(display.strippedPreference).toBeNull();
  });
});

describe("an unanswered turn claims provider contact only from the record", () => {
  const base = {
    kind: "unanswered" as const,
    conversation: {
      id: "c",
      project_id: null,
      title: "t",
      started_at: "",
      last_message_at: "",
      archived: false,
    },
    user_message: { id: "m", role: "user" as const, content: "x", sequence: 1, created_at: "" },
  };

  it("a pre-contact refusal never says the provider did not answer", () => {
    const label = describeUnanswered({
      ...base,
      error: "no_eligible_route: nothing fits under the ceiling",
      error_kind: "no_eligible_route",
      provider_contacted: false,
    });
    expect(label).not.toContain("provider did not answer");
    expect(label).toContain("before any provider was contacted");
    expect(label).toContain("no_eligible_route");
  });

  it("a recorded provider failure may say so", () => {
    const label = describeUnanswered({
      ...base,
      error: "provider_error: timed out",
      error_kind: "provider_error",
      provider_contacted: true,
    });
    expect(label).toContain("The provider did not answer");
  });
});
