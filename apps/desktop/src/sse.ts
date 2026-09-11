// Server-sent event framing for the streamed turn — a pure, tested parser.
//
// The service writes frames of the form `event: <name>\ndata: <json>\n\n`.
// Network chunks do not respect frame boundaries, so the parser is fed chunks
// and returns whole frames only, holding any partial tail for the next chunk.
// Nothing here interprets the events; `api.turnStream` does.

export interface ServerEvent {
  event: string;
  data: unknown;
}

export class EventFrameParser {
  private tail = "";

  /** Feed one chunk; get every complete event it completed, in order. */
  feed(chunk: string): ServerEvent[] {
    this.tail += chunk;
    const events: ServerEvent[] = [];
    let boundary = this.tail.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = this.tail.slice(0, boundary);
      this.tail = this.tail.slice(boundary + 2);
      const parsed = parseFrame(frame);
      if (parsed !== null) events.push(parsed);
      boundary = this.tail.indexOf("\n\n");
    }
    return events;
  }

  /** Whether an incomplete frame is still pending — a stream that ends here ended early. */
  get pending(): boolean {
    return this.tail.trim() !== "";
  }
}

function parseFrame(frame: string): ServerEvent | null {
  let event: string | null = null;
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice("event: ".length);
    else if (line.startsWith("data: ")) dataLines.push(line.slice("data: ".length));
  }
  if (event === null || dataLines.length === 0) return null;
  return { event, data: JSON.parse(dataLines.join("\n")) as unknown };
}
