// Where a new conversation belongs — the interaction model ruled 11 September 2026.
//
// Opening Val places Lord Armand in a new, unassigned conversation. New chat does
// the same. No selection is required for ordinary conversation, and "No project"
// is not a choice offered anywhere: unassigned is the absence of project scope.
// A conversation becomes project-scoped only when he intentionally enters a
// project and begins a conversation there; a previously entered project never
// carries into a new chat by itself. Existing conversations keep the attribution
// their record holds — the service resolves a continued conversation from its
// own row and never from anything sent here.
//
// The service contract is unchanged: `no_project: true` is the explicit
// statement of no project (its null state), `project` the explicit entry, and
// `conversation_id` the continuation. These pure functions decide which of the
// three the desktop sends, and are tested directly.

import type { ConversationView, ProjectView } from "./api";

export type Entry = { kind: "unassigned" } | { kind: "project"; project: ProjectView };

export const UNASSIGNED: Entry = { kind: "unassigned" };

/** Opening Val: a new, unassigned conversation, whatever was active before. */
export function initialEntry(): Entry {
  return UNASSIGNED;
}

/** New chat: a new, unassigned conversation — the previously entered project is left. */
export function newChatEntry(): Entry {
  return UNASSIGNED;
}

/** Entering a project is intentional: a new conversation there is project-scoped. */
export function enterProject(project: ProjectView): Entry {
  return { kind: "project", project };
}

export type TurnScopeFields =
  | { conversation_id: string }
  | { project: string }
  | { no_project: true };

/**
 * The scope fields of a turn request. A continued conversation sends only its id
 * (its attribution is the record's); a new conversation in an entered project
 * sends the project; a new unassigned conversation sends the explicit no-project
 * statement. Exactly one of the three, always — nothing is ever left to a
 * resolver's question, so no selector is ever required.
 */
export function turnScopeFields(entry: Entry, current: ConversationView | null): TurnScopeFields {
  if (current !== null) {
    return { conversation_id: current.id };
  }
  if (entry.kind === "project") {
    return { project: entry.project.name };
  }
  return { no_project: true };
}

/** What the empty thread says about the conversation that is about to begin. */
export function newConversationLine(entry: Entry): string {
  return entry.kind === "project"
    ? `A new conversation in ${entry.project.name}. Say something to start it.`
    : "Say something to Val to begin.";
}
