// How a message's revision state is described — ruling, 12 September 2026.
//
// Pure functions, tested directly, and the only place the interface turns
// revision and retraction records into words. Invariant 29: nothing here says
// more than the record supports. A corrected message is never presented as what
// was originally said; Val's answer is never presented as answering wording she
// did not receive; a withdrawn message is never presented as gone.

import type { MessageView } from "./api";

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
