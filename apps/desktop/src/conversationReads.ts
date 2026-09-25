// Conversation reads, applied newest-issued-wins — owner diagnostic, 25 September 2026.
//
// A spoken turn now reads the conversation twice: once when his words are committed,
// so he can see he was heard while she thinks, and again when her answer lands. Two
// reads in flight can return in either order. Applied as they arrived, an earlier read
// returning late would put back the older conversation — his message without her
// answer, or before his message existed — and take away what he had already seen.
//
// So each read is numbered when it is **issued**, and a response is applied only if no
// read issued after it has already been applied. A later-issued read reflects a store
// at least as new (the record is append-only), so it always wins; an earlier one that
// arrives first is shown until the later one replaces it, never after. The state
// applied is the service's whole conversation, replacing the last one rather than
// being merged into it, so nothing can appear twice.

export interface ReadOutcome {
  /** Whether this response became the conversation on screen. */
  applied: boolean;
  /** Issue order, from 1. */
  issued: number;
}

export interface ConversationReads<T> {
  read(load: () => Promise<T>): Promise<ReadOutcome>;
  /**
   * The screen was changed some other way (a new chat, say): every read still in
   * flight is now older than what is shown, and none of them may replace it.
   */
  invalidate(): void;
}

export function latestIssuedWins<T>(apply: (value: T) => void): ConversationReads<T> {
  let issued = 0;
  let applied = 0;
  return {
    async read(load) {
      issued += 1;
      const mine = issued;
      const value = await load();
      if (mine < applied) return { applied: false, issued: mine };
      applied = mine;
      apply(value);
      return { applied: true, issued: mine };
    },
    invalidate() {
      issued += 1;
      applied = issued;
    },
  };
}
