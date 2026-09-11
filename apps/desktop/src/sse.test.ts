// The server-sent event parser — chunks never respect frame boundaries.

import { describe, expect, it } from "vitest";

import { EventFrameParser } from "./sse";

const frames =
  'event: delta\ndata: {"text": "Good "}\n\n' +
  'event: delta\ndata: {"text": "evening."}\n\n' +
  'event: settled\ndata: {"kind": "answered", "val_message": {"content": "Good evening."}}\n\n';

describe("event frames", () => {
  it("parses whole frames in order", () => {
    const parser = new EventFrameParser();
    const events = parser.feed(frames);
    expect(events.map((e) => e.event)).toEqual(["delta", "delta", "settled"]);
    expect(events.slice(0, 2).map((e) => (e.data as { text: string }).text).join("")).toBe(
      "Good evening.",
    );
    expect(parser.pending).toBe(false);
  });

  it("reassembles frames split at every possible byte boundary", () => {
    for (let size = 1; size <= 17; size += 1) {
      const parser = new EventFrameParser();
      const events = [];
      for (let at = 0; at < frames.length; at += size) {
        events.push(...parser.feed(frames.slice(at, at + size)));
      }
      expect(events.map((e) => e.event), `chunk size ${size}`).toEqual(["delta", "delta", "settled"]);
      const streamed = events
        .filter((e) => e.event === "delta")
        .map((e) => (e.data as { text: string }).text)
        .join("");
      const last = events[2];
      if (last === undefined) throw new Error("no settled event");
      const settled = (last.data as { val_message: { content: string } }).val_message.content;
      expect(streamed, `chunk size ${size}`).toBe(settled);
      expect(parser.pending).toBe(false);
    }
  });

  it("holds a partial frame until it completes, and reports it if it never does", () => {
    const parser = new EventFrameParser();
    expect(parser.feed('event: delta\ndata: {"te')).toEqual([]);
    expect(parser.pending).toBe(true);
    expect(parser.feed('xt": "…"}\n\n')).toEqual([{ event: "delta", data: { text: "…" } }]);
    expect(parser.pending).toBe(false);
    parser.feed("event: settled\ndata: {");
    expect(parser.pending).toBe(true);
  });
});
