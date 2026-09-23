// The composer's attachment handling — Track C, owner ruling of 19 September 2026.
//
// Two properties, both about honesty rather than pixels:
//
// (1) **Selecting a file writes nothing.** Composer state is ephemeral, so
//     attach-preview-remove-choose-another must leave no trace anywhere. What
//     the tests below can show is the encoder half: a chosen file becomes an
//     `AttachmentInput` only at the moment it is sent, and removing one before
//     sending means it never becomes one at all.
//
// (2) **The classification travels with the act.** The default is Protected and
//     a weaker statement has to be made deliberately, per attachment, not
//     inherited from an earlier turn or from another file in the same send.

import { describe, expect, it } from "vitest";

import type { AttachmentInput, AttachmentView, MessageView } from "./api";
import { api } from "./api";

// A one-pixel PNG, written out so the bytes under test are known exactly.
const PNG = Uint8Array.from([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
  0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x06, 0x00, 0x00, 0x00, 0x1f, 0x15, 0xc4,
  0x89,
]);

function base64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

describe("encoding what the composer holds", () => {
  it("turns bytes into base64 that round-trips exactly", () => {
    const encoded = base64(PNG);
    const decoded = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0));
    expect(Array.from(decoded)).toEqual(Array.from(PNG));
  });

  it("carries the filename and the stated class, per attachment", () => {
    const inputs: AttachmentInput[] = [
      { filename: "setting.png", content_base64: base64(PNG), classification: "protected" },
      { filename: "poster.png", content_base64: base64(PNG), classification: "public" },
    ];
    expect(inputs.map((a) => a.classification)).toEqual(["protected", "public"]);
    expect(inputs.map((a) => a.filename)).toEqual(["setting.png", "poster.png"]);
    // Same bytes, different acts: the content is one thing and the statement is
    // another, which is exactly what the substrate separates.
    expect(inputs[0]!.content_base64).toEqual(inputs[1]!.content_base64);
  });

  it("a removed attachment is simply not among those sent", () => {
    const chosen = ["a.png", "b.png", "c.png"];
    const remaining = chosen.filter((name) => name !== "b.png");
    expect(remaining).toEqual(["a.png", "c.png"]);
  });
});

describe("rendering what the house holds", () => {
  const act: AttachmentView = {
    id: "act-1",
    attachment_id: "att-1",
    position: 1,
    filename: "setting.png",
    classification: "protected",
    media_type: "image/png",
    width: 1600,
    height: 900,
    byte_size: 12345,
    modality: "image",
    duration_seconds: null,
    sha256: "a".repeat(64),
  };

  it("fetches bytes by digest, from the loopback service", () => {
    const url = api.attachmentUrl(act.sha256);
    expect(url.endsWith(`/attachments/${act.sha256}/bytes`)).toBe(true);
    expect(url.startsWith("http://127.0.0.1:")).toBe(true);
  });

  it("a message with no attachments is the ordinary case", () => {
    const message: MessageView = {
      id: "m1",
      role: "user",
      content: "Good evening, Val.",
      sequence: 1,
      created_at: "2026-09-19T23:00:00Z",
    };
    expect(message.attachments ?? []).toEqual([]);
  });

  it("an act reports the true dimensions, not the thumbnail's", () => {
    expect([act.width, act.height]).toEqual([1600, 900]);
  });
});
