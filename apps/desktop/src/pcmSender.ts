// The audio's order is the audio — WP3 repair pass, §2.
//
// **The defect this replaces.** The controller forwarded every 20 ms chunk with
// `void this.forward(pcm)`: fifty concurrent, unawaited POSTs a second, whose
// arrival order at the service is not guaranteed by anything. The recognizer
// therefore received Lord Armand's speech slightly shuffled, and whisper.cpp does
// not degrade gracefully when that happens — it stays fluent and becomes wrong.
//
// Measured against the production recognizer with the frozen fixture, whose correct
// transcript is "And so, my fellow Americans,":
//
//   in order                      -> "And so, my fellow Americans,"
//   one block arriving 1 late     -> "And so am I fellow Americans!"
//   one block arriving 2 late     -> "So much homework!"
//   one block arriving 4 late     -> "I'm so wanted to follow the winner!"
//
// That is the shape of what he saw in acceptance: confident sentences bearing no
// relation to what he said.
//
// **What this does instead.** One sender, one request in flight, strict order, and
// chunks coalesced into a larger payload while a request is outstanding — so a slow
// request produces one bigger send rather than a backlog of racing small ones. The
// audio is still bounded: the queue has a ceiling, and passing it drops the oldest
// with a count, because live speech that could not be sent in time is stale and
// pretending otherwise would be worse than saying so.

/** How much audio one request may carry at most. 2 s at 16 kHz, mono, int16. */
export const MAX_PAYLOAD_BYTES = 16_000 * 2 * 2;

/** How much unsent audio may wait. Past this the oldest is dropped, and counted. */
export const MAX_QUEUED_BYTES = 16_000 * 2 * 8;

export interface SenderReport {
  /** Chunks accepted from the capture layer. */
  chunks: number;
  /** Requests actually made. Fewer than `chunks` when coalescing happened. */
  requests: number;
  /** Bytes handed to the service, in order. */
  sent: number;
  /** Bytes dropped because the queue was full. Not hidden. */
  dropped: number;
  /** The largest single payload sent. */
  largestPayload: number;
}

/**
 * Sends PCM to the service in the order it was captured, one request at a time.
 *
 * `send` is the transport. It is awaited, and the next payload is not begun until
 * it settles — which is the whole point: correctness of order over concurrency.
 */
export class OrderedPcmSender {
  private queue: Uint8Array[] = [];
  private queuedBytes = 0;
  private running = false;
  private closed = false;
  private readonly report: SenderReport = {
    chunks: 0,
    requests: 0,
    sent: 0,
    dropped: 0,
    largestPayload: 0,
  };

  constructor(
    private readonly send: (payload: ArrayBuffer) => Promise<void>,
    private readonly onFailure: (detail: string) => void,
  ) {}

  get measured(): SenderReport {
    return { ...this.report };
  }

  get queuedChunks(): number {
    return this.queue.length;
  }

  /** Accept one captured chunk. Never blocks the audio thread's caller. */
  offer(pcm: ArrayBuffer): void {
    if (this.closed) return;
    this.report.chunks += 1;
    this.queue.push(new Uint8Array(pcm));
    this.queuedBytes += pcm.byteLength;
    while (this.queuedBytes > MAX_QUEUED_BYTES && this.queue.length > 1) {
      const dropped = this.queue.shift();
      if (dropped === undefined) break;
      this.queuedBytes -= dropped.byteLength;
      this.report.dropped += dropped.byteLength;
    }
    void this.pump();
  }

  /** Stop accepting and forget what is unsent. Called on mute and on Voice off. */
  close(): void {
    this.closed = true;
    this.queue = [];
    this.queuedBytes = 0;
  }

  /** Everything queued has been sent. For a test, and for an orderly stop. */
  async drained(): Promise<void> {
    while (this.running || this.queue.length > 0) {
      await new Promise<void>((resolve) => setTimeout(resolve, 1));
      if (this.closed) return;
    }
  }

  private async pump(): Promise<void> {
    if (this.running || this.closed) return;
    this.running = true;
    try {
      while (!this.closed && this.queue.length > 0) {
        const payload = this.take();
        if (payload.byteLength === 0) continue;
        this.report.requests += 1;
        this.report.sent += payload.byteLength;
        this.report.largestPayload = Math.max(this.report.largestPayload, payload.byteLength);
        try {
          // Awaited. The next payload is not begun until this one has settled, which
          // is what makes the service receive the audio in the order it was spoken.
          await this.send(payload.buffer as ArrayBuffer);
        } catch (failure) {
          this.onFailure(failure instanceof Error ? failure.message : "audio could not be sent");
          return;
        }
      }
    } finally {
      this.running = false;
    }
  }

  /** As many queued chunks as fit in one payload, in order, joined. */
  private take(): Uint8Array {
    let total = 0;
    const taking: Uint8Array[] = [];
    while (this.queue.length > 0) {
      const next = this.queue[0]!;
      if (taking.length > 0 && total + next.byteLength > MAX_PAYLOAD_BYTES) break;
      this.queue.shift();
      this.queuedBytes -= next.byteLength;
      taking.push(next);
      total += next.byteLength;
    }
    const joined = new Uint8Array(total);
    let at = 0;
    for (const piece of taking) {
      joined.set(piece, at);
      at += piece.byteLength;
    }
    return joined;
  }
}
