// Versions, continuing from one, and reinstating a withdrawn message — owner order,
// 2 October 2026 (§C, §D): the desktop's own reading of the service's facts.

import { describe, expect, it } from "vitest";

import { type MessageView, viewQuery } from "./api";
import { continuingFrom, reinstateWording } from "./messageState";

function message(overrides: Partial<MessageView>): MessageView {
  return {
    id: "m1",
    role: "user",
    content: "Open on the wide shot.",
    sequence: 1,
    created_at: "2026-10-02T20:00:00Z",
    state: "current",
    ...overrides,
  } as MessageView;
}

describe("continuing from a version", () => {
  it("names the shown version only when it is not the one in force", () => {
    const versions = [
      { number: 1, revision_number: 0, content: "A", created_at: "t" },
      { number: 2, revision_number: 1, content: "B", created_at: "t" },
    ];
    expect(continuingFrom([message({ versions, version: 2 })])).toBeNull();
    expect(continuingFrom([message({ versions, version: 1 })])).toEqual({
      message_id: "m1",
      revision_number: 0,
    });
    expect(continuingFrom([message({})])).toBeNull();
  });
  it("renders the view as the service reads it", () => {
    expect(viewQuery(undefined)).toBe("");
    expect(viewQuery({ m1: 1 })).toBe("?view=m1%3A1");
  });
});

describe("reinstating a withdrawn message", () => {
  it("sends back the wording in force when it was withdrawn", () => {
    const withdrawn = message({
      state: "withdrawn",
      content: "Open on the wide shot.",
      revisions: [
        { id: "r1", message_id: "m1", revision_number: 1, kind: "revision", content: "Open on the close-up.", note: null, authored_by: "Lord Armand", created_at: "t" },
        { id: "r2", message_id: "m1", revision_number: 2, kind: "retraction", content: null, note: null, authored_by: "Lord Armand", created_at: "t" },
      ],
    });
    expect(reinstateWording(withdrawn)).toBe("Open on the close-up.");
    expect(reinstateWording(message({ state: "current" }))).toBeNull();
    expect(
      reinstateWording(
        message({
          state: "withdrawn",
          revisions: [
            { id: "r1", message_id: "m1", revision_number: 1, kind: "retraction", content: null, note: null, authored_by: "Lord Armand", created_at: "t" },
          ],
        }),
      ),
    ).toBe("Open on the wide shot.");
  });
});
