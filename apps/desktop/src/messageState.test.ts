// Revision and retraction as display logic — ruling, 12 September 2026.

import { describe, expect, it } from "vitest";

import type { MessageView, ProjectView, RevisionView } from "./api";
import {
  answeredAfter,
  answerStateLine,
  canEdit,
  canRemove,
  isLive,
  moveConfirmation,
  transitionLine,
  userStateLine,
} from "./messageState";

function fact(overrides: Partial<RevisionView> = {}): RevisionView {
  return {
    id: "fact-1",
    message_id: "m-1",
    revision_number: 1,
    kind: "revision",
    content: "Open on the close-up?",
    note: null,
    authored_by: "Lord Armand",
    created_at: "2026-09-12T18:00:00Z",
    ...overrides,
  };
}

function message(overrides: Partial<MessageView> = {}): MessageView {
  return {
    id: "m-1",
    role: "user",
    content: "Open on the wide shot?",
    sequence: 1,
    created_at: "2026-09-12T17:00:00Z",
    state: "current",
    original_content: null,
    answered_state: null,
    revisions: [],
    revision_refusal: null,
    ...overrides,
  };
}

describe("revision state words", () => {
  it("says nothing about a current message", () => {
    expect(userStateLine(message())).toBeNull();
    expect(answerStateLine(message({ role: "val" }))).toBeNull();
    expect(isLive(message())).toBe(true);
  });

  it("marks a corrected message and the reply that answered the earlier wording", () => {
    const corrected = message({
      state: "corrected",
      content: "Open on the close-up?",
      original_content: "Open on the wide shot?",
      revisions: [fact()],
    });
    expect(userStateLine(corrected)).toMatch(/^Corrected /);
    expect(answerStateLine(message({ role: "val", answered_state: "corrected" }))).toBe(
      "This reply answered the earlier wording of the message above.",
    );
    expect(isLive(corrected)).toBe(true);
  });

  it("marks a withdrawn message and its reply, and collapses both", () => {
    const withdrawn = message({ state: "withdrawn", revisions: [fact({ kind: "retraction", content: null })] });
    const reply = message({ id: "m-2", role: "val", answered_state: "withdrawn" });
    expect(userStateLine(withdrawn)).toMatch(/^Withdrawn /);
    expect(answerStateLine(reply)).toBe("This reply answered a withdrawn message.");
    expect(isLive(withdrawn)).toBe(false);
    expect(isLive(reply)).toBe(false);
  });

  it("never offers Edit on a deliberated message, but still offers Remove", () => {
    const deliberated = message({ revision_refusal: "part of a recorded decision exchange" });
    expect(canEdit(deliberated)).toBe(false);
    expect(canRemove(deliberated)).toBe(true);
  });

  it("never offers Edit or Remove on Val's words or on a withdrawn message", () => {
    expect(canEdit(message({ role: "val" }))).toBe(false);
    expect(canRemove(message({ role: "val" }))).toBe(false);
    expect(canEdit(message({ state: "withdrawn" }))).toBe(false);
    expect(canRemove(message({ state: "withdrawn" }))).toBe(false);
  });
});

describe("scope transition words", () => {
  const projects: ProjectView[] = [
    { id: "p-a", name: "Project Alpha", slug: "project-alpha", status: "active", archived: false },
    { id: "p-b", name: "Project Beta", slug: "project-beta", status: "active", archived: false },
  ];

  it("names both ends of a move, including no project", () => {
    const line = transitionLine(
      {
        id: "t-1",
        transition_number: 1,
        after_sequence: 2,
        from_project_id: "p-a",
        to_project_id: null,
        note: null,
        authored_by: "Lord Armand",
        created_at: "2026-09-12T18:00:00Z",
      },
      projects,
    );
    expect(line).toMatch(/^Moved from Project Alpha to no project · /);
    expect(line).toContain("written before the move");
  });

  it("never claims the move rewrote earlier messages", () => {
    expect(moveConfirmation("Project Beta")).toContain("Earlier messages keep the scope");
    expect(moveConfirmation("Project Beta")).toContain("nothing is rewritten");
  });
});

describe("answeredAfter — Voice Off never strands her answer", () => {
  const m = (id: string, role: "user" | "val", sequence: number) =>
    ({ id, role, content: "", sequence, created_at: "" }) as never;
  it("is false until a message of hers follows his", () => {
    expect(answeredAfter([m("his", "user", 1)], "his")).toBe(false);
    expect(answeredAfter([m("her0", "val", 1), m("his", "user", 2)], "his")).toBe(false);
    expect(answeredAfter([m("his", "user", 1), m("hers", "val", 2)], "his")).toBe(true);
    expect(answeredAfter([], "his")).toBe(false);
  });
});
