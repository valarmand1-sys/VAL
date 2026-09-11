// The interaction model ruled 11 September 2026, tested at the functions the
// App uses to decide where a conversation belongs and what the turn sends.

import { describe, expect, it } from "vitest";

import type { ConversationView, ProjectView } from "./api";
import {
  enterProject,
  initialEntry,
  newChatEntry,
  newConversationLine,
  turnScopeFields,
} from "./scope";

const alpha: ProjectView = {
  id: "project-alpha",
  name: "Project Alpha",
  slug: "project-alpha",
  status: "active",
  archived: false,
};

const existing: ConversationView = {
  id: "conversation-1",
  project_id: "project-alpha",
  title: "An earlier conversation",
  started_at: "2026-09-11T10:00:00Z",
  last_message_at: "2026-09-11T10:05:00Z",
  archived: false,
};

describe("opening Val and starting a new chat", () => {
  it("app launch defaults to a new unassigned conversation, with no selection made", () => {
    const entry = initialEntry();
    expect(entry).toEqual({ kind: "unassigned" });
    expect(turnScopeFields(entry, null)).toEqual({ no_project: true });
  });

  it("new chat defaults to a new unassigned conversation", () => {
    expect(newChatEntry()).toEqual({ kind: "unassigned" });
    expect(turnScopeFields(newChatEntry(), null)).toEqual({ no_project: true });
  });

  it("no project selector, and no replacement 'unassigned' selector, is required first", () => {
    // The fields are complete from the default entry alone: exactly one scope
    // statement, chosen by the model, never by a selection.
    const fields = turnScopeFields(initialEntry(), null);
    expect(Object.keys(fields)).toEqual(["no_project"]);
    expect(newConversationLine(initialEntry())).not.toMatch(/project/i);
  });

  it("the previously entered project does not carry into a new chat", () => {
    const inside = enterProject(alpha);
    expect(turnScopeFields(inside, null)).toEqual({ project: "Project Alpha" });
    const afterNewChat = newChatEntry();
    expect(turnScopeFields(afterNewChat, null)).toEqual({ no_project: true });
    expect(afterNewChat).not.toHaveProperty("project");
  });
});

describe("entering a project intentionally", () => {
  it("a new conversation begun inside an entered project is project-scoped", () => {
    expect(turnScopeFields(enterProject(alpha), null)).toEqual({ project: "Project Alpha" });
    expect(newConversationLine(enterProject(alpha))).toContain("Project Alpha");
  });

  it("an existing conversation keeps its own attribution: only its id is sent", () => {
    // Whatever is entered now, a continued conversation is resolved from its
    // record; the desktop sends nothing that could reassign it.
    expect(turnScopeFields(initialEntry(), existing)).toEqual({ conversation_id: "conversation-1" });
    expect(turnScopeFields(enterProject(alpha), existing)).toEqual({ conversation_id: "conversation-1" });
  });

  it("removing the 'No project' selector leaves the service's null semantics untouched", () => {
    // The explicit no-project statement is still the one the service defines;
    // it is now sent by the model rather than chosen from a list.
    expect(turnScopeFields(initialEntry(), null)).toEqual({ no_project: true });
    expect(turnScopeFields(initialEntry(), null)).not.toHaveProperty("project");
  });
});
