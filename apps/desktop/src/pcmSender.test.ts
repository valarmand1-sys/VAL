// Order is the whole contract — WP3 repair pass §2, §19.
//
// The defect these hold closed: fifty concurrent unawaited POSTs a second, whose
// arrival order the service could not rely on. Measured against the production
// recognizer, one block arriving two positions late turned "And so, my fellow
// Americans," into "So much homework!" — so order is not a nicety here, it is the
// difference between a transcript and a fabrication.

import { describe, expect, it } from "vitest";

import { MAX_PAYLOAD_BYTES, MAX_QUEUED_BYTES, OrderedPcmSender } from "./pcmSender";

/** A chunk whose every byte carries its sequence, so order is checkable. */
function chunk(marker: number, samples = 320): ArrayBuffer {
  return new Uint8Array(samples * 2).fill(marker).buffer;
}

function bytesOf(payload: ArrayBuffer): number[] {
  return Array.from(new Uint8Array(payload));
}

describe("the audio arrives in the order it was captured", () => {
  it("sends one request at a time and never overlaps them", async () => {
    let inFlight = 0;
    let overlapped = false;
    const order: number[] = [];
    const sender = new OrderedPcmSender(async (payload) => {
      inFlight += 1;
      if (inFlight > 1) overlapped = true;
      // A real request takes time; this is where a concurrent sender would race.
      await new Promise<void>((resolve) => setTimeout(resolve, 2));
      order.push(...new Set(bytesOf(payload)));
      inFlight -= 1;
    }, () => undefined);

    for (let marker = 1; marker <= 6; marker += 1) sender.offer(chunk(marker));
    await sender.drained();

    expect(overlapped).toBe(false);
    // Every marker present exactly once, in capture order — coalescing may join
    // them into fewer requests, and must never reorder them.
    expect(order).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it("coalesces while a request is outstanding rather than queuing races", async () => {
    let release: { resolve: (() => void) | null } = { resolve: null };
    const payloads: number[][] = [];
    const sender = new OrderedPcmSender(async (payload) => {
      payloads.push([...new Set(bytesOf(payload))]);
      if (payloads.length === 1) {
        await new Promise<void>((resolve) => {
          release.resolve = resolve;
        });
      }
    }, () => undefined);

    sender.offer(chunk(1));
    await new Promise<void>((resolve) => setTimeout(resolve, 1));
    // Four more arrive while the first request is still outstanding.
    for (const marker of [2, 3, 4, 5]) sender.offer(chunk(marker));
    expect(payloads).toEqual([[1]]);
    release.resolve?.();
    await sender.drained();

    // The four became **one** request, in order — not four racing ones.
    expect(payloads.length).toBe(2);
    expect(payloads[1]).toEqual([2, 3, 4, 5]);
    expect(sender.measured.chunks).toBe(5);
    expect(sender.measured.requests).toBe(2);
  });

  it("bounds a single payload", async () => {
    const sizes: number[] = [];
    let release: { resolve: (() => void) | null } = { resolve: null };
    const sender = new OrderedPcmSender(async (payload) => {
      sizes.push(payload.byteLength);
      if (sizes.length === 1) {
        await new Promise<void>((resolve) => {
          release.resolve = resolve;
        });
      }
    }, () => undefined);

    sender.offer(chunk(1));
    await new Promise<void>((resolve) => setTimeout(resolve, 1));
    // Far more than one payload may carry.
    for (let marker = 2; marker < 200; marker += 1) sender.offer(chunk(marker));
    release.resolve?.();
    await sender.drained();
    for (const size of sizes) expect(size).toBeLessThanOrEqual(MAX_PAYLOAD_BYTES);
  });

  it("drops the oldest rather than growing without limit, and counts it", async () => {
    // The first request never settles, so everything after it queues — which is the
    // condition a bound exists for. The queue is then closed rather than drained:
    // audio waiting behind a stalled request is stale, and the count says so.
    let sends = 0;
    const sender = new OrderedPcmSender(async () => {
      sends += 1;
      await new Promise<void>(() => undefined);
    }, () => undefined);

    sender.offer(chunk(1));
    await new Promise<void>((resolve) => setTimeout(resolve, 1));
    const chunks = Math.ceil(MAX_QUEUED_BYTES / 640) + 40;
    for (let marker = 2; marker < chunks; marker += 1) sender.offer(chunk(marker % 250));

    expect(sends).toBe(1);
    expect(sender.measured.dropped).toBeGreaterThan(0);
    // Bounded: what is still waiting fits inside the ceiling.
    expect(sender.queuedChunks * 640).toBeLessThanOrEqual(MAX_QUEUED_BYTES + 640);
    sender.close();
    expect(sender.queuedChunks).toBe(0);
  });
});

describe("failure and closing", () => {
  it("reports a transport failure once and stops sending", async () => {
    const failures: string[] = [];
    let attempts = 0;
    const sender = new OrderedPcmSender(async () => {
      attempts += 1;
      throw new Error("the service went away");
    }, (detail) => failures.push(detail));

    sender.offer(chunk(1));
    sender.offer(chunk(2));
    await new Promise<void>((resolve) => setTimeout(resolve, 5));
    expect(failures).toEqual(["the service went away"]);
    expect(attempts).toBe(1);
  });

  it("forgets unsent audio when closed, because a closed device's audio is stale", async () => {
    const sent: number[] = [];
    let release: { resolve: (() => void) | null } = { resolve: null };
    const sender = new OrderedPcmSender(async (payload) => {
      sent.push(...new Set(bytesOf(payload)));
      if (sent.length === 1) {
        await new Promise<void>((resolve) => {
          release.resolve = resolve;
        });
      }
    }, () => undefined);

    sender.offer(chunk(1));
    await new Promise<void>((resolve) => setTimeout(resolve, 1));
    sender.offer(chunk(2));
    sender.offer(chunk(3));
    sender.close();
    release.resolve?.();
    await new Promise<void>((resolve) => setTimeout(resolve, 5));
    expect(sent).toEqual([1]);
    expect(sender.queuedChunks).toBe(0);
  });

  it("accepts nothing after closing", () => {
    const sender = new OrderedPcmSender(async () => undefined, () => undefined);
    sender.close();
    sender.offer(chunk(1));
    expect(sender.measured.chunks).toBe(0);
    expect(sender.queuedChunks).toBe(0);
  });
});
