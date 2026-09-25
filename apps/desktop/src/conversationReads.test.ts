// The read rule on its own — owner diagnostic, 25 September 2026.

import { describe, expect, it } from "vitest";

import { latestIssuedWins } from "./conversationReads";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("conversation reads", () => {
  it("apply in arrival order when nothing newer has been shown", async () => {
    const shown: string[] = [];
    const reads = latestIssuedWins<string>((value) => shown.push(value));
    const first = deferred<string>();
    const second = deferred<string>();
    const a = reads.read(() => first.promise);
    const b = reads.read(() => second.promise);
    first.resolve("his words");
    await a;
    second.resolve("his words and her answer");
    await b;
    expect(shown).toEqual(["his words", "his words and her answer"]);
  });

  it("never let an older read replace a newer one already shown", async () => {
    const shown: string[] = [];
    const reads = latestIssuedWins<string>((value) => shown.push(value));
    const first = deferred<string>();
    const second = deferred<string>();
    const a = reads.read(() => first.promise);
    const b = reads.read(() => second.promise);
    second.resolve("his words and her answer");
    expect((await b).applied).toBe(true);
    first.resolve("his words");
    expect((await a).applied).toBe(false);
    expect(shown).toEqual(["his words and her answer"]);
  });

  it("drop every read in flight when the screen was changed another way", async () => {
    const shown: string[] = [];
    const reads = latestIssuedWins<string>((value) => shown.push(value));
    const pending = deferred<string>();
    const a = reads.read(() => pending.promise);
    reads.invalidate();
    pending.resolve("the conversation he just left");
    expect((await a).applied).toBe(false);
    expect(shown).toEqual([]);
  });
});
