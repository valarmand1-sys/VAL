// The text model's state, as the desktop shows it — owner order of 2 October 2026 and his
// ruling of 3 October.
//
// Ordinary typed conversation and writing go to one local model; deep reasoning is a
// deliberate, conversation-level choice that goes to another; Voice has its own. Only one
// is held in this Mac's memory at a time, so changing between them is a preparation that
// takes time once. He accepted that delay; what he asked for is that it is shown
// truthfully, that a message sent during it is kept and answered once, and that it can be
// cancelled. Everything here reads the service's own facts (`GET /cognition`); nothing in
// it decides a route or claims a state the service did not report.

export interface CognitionState {
  configured: boolean;
  typed_model?: string | null;
  deep_model?: string | null;
  resident?: string[];
  preparing?: string | null;
  voice_holds_memory?: boolean;
  voice_open?: boolean;
  typed_ready?: boolean;
  deep_ready?: boolean;
  typed_prefix_prepared?: boolean;
}

/** The line shown above the composer, or null when there is nothing to say. */
export function cognitionLine(state: CognitionState | null, deep: boolean): string | null {
  if (state === null || !state.configured) return null;
  if (state.voice_open || state.voice_holds_memory) return null; // Voice says its own state
  const wanted = deep ? state.deep_model : state.typed_model;
  const ready = deep ? state.deep_ready : state.typed_ready;
  const what = deep ? "the deep-reasoning model" : "the text model";
  if (ready) return null;
  if (state.preparing !== null && state.preparing !== undefined && state.preparing === wanted) {
    return `Preparing ${what}… A message you send now is kept and answered when it is ready.`;
  }
  if (state.preparing) {
    return `Changing models… A message you send now is kept and answered when ${what} is ready.`;
  }
  return `${what.charAt(0).toUpperCase()}${what.slice(1)} is not loaded; your next message will prepare it first.`;
}

/** Deep reasoning is chosen per conversation; a new chat carries its choice to the
 *  conversation its first message creates. */
export const NEW_CHAT = "new";

export function deepFor(choices: Record<string, boolean>, conversationId: string | null): boolean {
  return choices[conversationId ?? NEW_CHAT] ?? false;
}

export function adoptNewChatChoice(
  choices: Record<string, boolean>,
  createdId: string,
): Record<string, boolean> {
  if (!(NEW_CHAT in choices)) return choices;
  const { [NEW_CHAT]: carried, ...rest } = choices;
  return { ...rest, [createdId]: carried ?? false };
}

/** A submission's own name, so the service answers it once and can cancel it. */
export function newRequestId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export const CANCELLED_NOTICE =
  "Cancelled. Your message is kept in the conversation, unanswered; nothing was invented in its place.";
