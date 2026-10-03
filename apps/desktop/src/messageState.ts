// How a message's revision state is described — ruling, 12 September 2026.
//
// Pure functions, tested directly, and the only place the interface turns
// revision and retraction records into words. Invariant 29: nothing here says
// more than the record supports. A corrected message is never presented as what
// was originally said; Val's answer is never presented as answering wording she
// did not receive; a withdrawn message is never presented as gone.

import type { MessageView, ProjectView, ScopeTransitionView } from "./api";

export const REMOVE_MESSAGE_CONFIRMATION =
  "Remove this message and Val's reply from the conversation? Both stay in the House " +
  "record, marked withdrawn, with their evidence and cost. Val will no longer treat " +
  "them as part of this conversation or recall them. This makes no call to Val.";

export const EDIT_EXPLANATION =
  "Your correction replaces this message's wording from here on. What you first sent " +
  "is kept and can be viewed. Val's earlier reply stays, marked as answering the " +
  "earlier wording; nothing is regenerated.";

function when(iso: string): string {
  return new Date(iso).toLocaleString();
}

/** The line shown on Lord Armand's own message, or null when it is current. */
export function userStateLine(message: MessageView): string | null {
  if (message.role !== "user") return null;
  const newest = (message.revisions ?? []).at(-1);
  if (newest === undefined) return null;
  if (message.state === "corrected") return `Corrected ${when(newest.created_at)}`;
  if (message.state === "withdrawn") return `Withdrawn ${when(newest.created_at)}`;
  return null;
}

/** The line shown on Val's message when the message she answered has changed since. */
export function answerStateLine(message: MessageView): string | null {
  if (message.role !== "val") return null;
  if (message.answered_state === "corrected") {
    return "This reply answered the earlier wording of the message above.";
  }
  if (message.answered_state === "withdrawn") {
    return "This reply answered a withdrawn message.";
  }
  return null;
}

/** Whether a message belongs to the working conversation (not collapsed). */
export function isLive(message: MessageView): boolean {
  return message.state !== "withdrawn" && message.answered_state !== "withdrawn";
}

/** Whether Lord Armand may be offered Edit and Remove on this message. */
export function canEdit(message: MessageView): boolean {
  return (
    message.role === "user" &&
    message.state !== "withdrawn" &&
    (message.revision_refusal ?? null) === null
  );
}

export function canRemove(message: MessageView): boolean {
  return message.role === "user" && message.state !== "withdrawn";
}

export const REMOVE_CONVERSATION_CONFIRMATION =
  "Remove this conversation from active use? It leaves the sidebar, Val will not recall " +
  "it, and it cannot take new messages until you reinstate it. Nothing in it is " +
  "deleted: every message, record and cost stays in the House record.";

export const REMOVED_CONVERSATION_NOTICE =
  "This conversation has been removed from active use. It is preserved whole; " +
  "reinstate it to continue.";

function scopeName(projectId: string | null, projects: ProjectView[]): string {
  if (projectId === null) return "no project";
  return projects.find((project) => project.id === projectId)?.name ?? "a project not listed";
}

/** The marker shown in the thread where an explicit move took effect. */
export function transitionLine(transition: ScopeTransitionView, projects: ProjectView[]): string {
  return (
    `Moved from ${scopeName(transition.from_project_id, projects)} to ` +
    `${scopeName(transition.to_project_id, projects)} · ${when(transition.created_at)}. ` +
    "Messages above were written before the move."
  );
}

export function moveConfirmation(destination: string): string {
  return (
    `Move this conversation to ${destination}? From now on it belongs there, and Val will ` +
    "draw on that scope's material for new messages. Earlier messages keep the scope they " +
    "were written in, and the move is recorded; nothing is rewritten."
  );
}

/**
 * Whether Val has answered after this message of his — the thread already holds a
 * message of hers later in the conversation. Used to stop following a turn that
 * was in flight when Voice ended (owner Step B retest, 25 September 2026, §11.2).
 */
export function answeredAfter(messages: MessageView[], messageId: string): boolean {
  const at = messages.findIndex((message) => message.id === messageId);
  return at >= 0 && messages.slice(at + 1).some((message) => message.role === "val");
}

// Reinstating a withdrawn message — owner order, 2 October 2026 (§D). The wording in
// force when it was withdrawn is sent back as a revision; the service reads a revision
// that returns the withdrawn wording as a reinstatement, not a correction, and the
// answer that followed it returns with it. Nothing is generated or re-sent.
export function reinstateWording(message: MessageView): string | null {
  if (message.state !== "withdrawn") return null;
  let wording = message.original_content ?? message.content;
  let before: string | null = null;
  for (const fact of message.revisions ?? []) {
    if (fact.kind === "retraction") before = wording;
    else if (fact.content !== null) wording = fact.content;
  }
  return before ?? wording;
}

export const REINSTATE_MESSAGE_CONFIRMATION =
  "Reinstate this message and Val's reply? Both return to the conversation as they were; " +
  "nothing is sent again and no new answer is made.";

/** The versions of his messages he is viewing that are not the version in force. */
export function continuingFrom(
  messages: MessageView[],
): { message_id: string; revision_number: number } | null {
  for (const message of messages) {
    const versions = message.versions ?? [];
    if (message.role !== "user" || versions.length < 2) continue;
    const shown = message.version ?? versions.length;
    if (shown !== versions.length) {
      const chosen = versions.find((v) => v.number === shown);
      if (chosen) return { message_id: message.id, revision_number: chosen.revision_number };
    }
  }
  return null;
}

