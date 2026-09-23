// @vitest-environment jsdom
//
// The attachment actually renders — owner defect report, 20 September 2026.
//
// The first genuine image turn worked end to end: VAL received the image and
// described it in detail. But the thread showed only the filename, dimensions
// and classification; the image itself never appeared. The element was right,
// the URL was right, and the existing test — which asserted the URL *string* —
// passed while the user saw nothing.
//
// The cause was one directive. The webview's content security policy allowed
// `connect-src` to the loopback service, so every fetch worked, but `img-src`
// was `'self' data:` only. An `<img>` pointing at the governed byte route was
// therefore refused by the webview before any request was made, silently.
//
// So these tests deliberately cover the two halves a URL-string assertion
// cannot: that the element the view produces points at the governed route, and
// that the policy the desktop actually ships **permits that exact origin**. The
// bytes and content type are proven on the service side, in the API tests.
//
// Both halves read the shipped thing itself — owner correction, 20 September
// 2026. The renderer under test is `Attachments` from `./attachments`, the very
// component the conversation thread mounts, not a copy of its markup; the policy
// is parsed out of the shipped Tauri configuration, not restated here. A test
// that held its own copy of either could pass while the shipped code diverged or
// broke, which is precisely the defect it is meant to catch.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import type { AttachmentView } from "./api";
import { api, API_BASE } from "./api";
// The production renderer itself — the same component the thread mounts.
import { Attachments } from "./attachments";
// The policy the desktop actually ships, read from the shipped configuration
// rather than restated here — a test that restated it would pass while the
// shipped file said something else, which is the whole defect it guards.
import tauriConfig from "../src-tauri/tauri.conf.json";

const ACT: AttachmentView = {
  id: "01a0c109-8994-73d0-a194-6cf75324bb06",
  attachment_id: "01a0c109-8993-7842-b309-73b169e4a27c",
  position: 1,
  filename: "a-real-frame.png",
  classification: "protected",
  media_type: "image/png",
  width: 2752,
  height: 1536,
  byte_size: 8_371_957,
  modality: "image",
  duration_seconds: null,
  sha256: "7fc13a7c5072b69acc119d20a16beb6523dc21aa4ba6a4ef950c7ba748c12db0",
};

function policy(): Record<string, string[]> {
  const directives: Record<string, string[]> = {};
  for (const part of tauriConfig.app.security.csp.split(";")) {
    const [name, ...sources] = part.trim().split(/\s+/);
    if (name) directives[name] = sources;
  }
  return directives;
}

let root: Root | null = null;
let host: HTMLDivElement | null = null;

function render(element: React.JSX.Element): HTMLDivElement {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  act(() => root!.render(element));
  return host;
}

afterEach(() => {
  act(() => root?.unmount());
  host?.remove();
  root = null;
  host = null;
});

describe("the policy the desktop actually ships", () => {
  it("permits images from the governed loopback route", () => {
    const origin = new URL(api.attachmentUrl(ACT.sha256)).origin;
    expect(origin).toBe(API_BASE);
    const sources = policy()["img-src"] ?? [];
    expect(
      sources.includes(origin),
      `img-src is ${JSON.stringify(sources)} and must permit ${origin}; ` +
        "an <img> at that origin is otherwise refused by the webview before any request",
    ).toBe(true);
  });

  it("still permits the composer's own local previews", () => {
    const sources = policy()["img-src"] ?? [];
    expect(sources).toContain("'self'");
    expect(sources).toContain("blob:");
  });

  it("opens nothing wider than that: no wildcard, no https at large", () => {
    const sources = policy()["img-src"] ?? [];
    expect(sources).not.toContain("*");
    expect(sources).not.toContain("https:");
    expect(sources.filter((source) => source.startsWith("http")).sort()).toEqual([API_BASE]);
    // And the rest of the policy is untouched by this correction.
    expect(policy()["default-src"]).toEqual(["'self'"]);
    expect(policy()["connect-src"]).toEqual(["'self'", API_BASE]);
  });
});

describe("what the production thread renderer puts in the thread", () => {
  it("renders an image element pointing at the governed route", () => {
    const container = render(<Attachments attachments={[ACT]} />);
    const image = container.querySelector("img");
    expect(image).not.toBeNull();
    expect(image!.getAttribute("src")).toBe(
      `${API_BASE}/attachments/${ACT.sha256}/bytes`,
    );
    expect(image!.getAttribute("alt")).toBe(ACT.filename);
  });

  it("uses no external or public URL", () => {
    const container = render(<Attachments attachments={[ACT]} />);
    for (const image of container.querySelectorAll("img")) {
      const source = image.getAttribute("src") ?? "";
      expect(source.startsWith(API_BASE)).toBe(true);
      expect(source).not.toContain("://example");
      expect(new URL(source).hostname).toBe("127.0.0.1");
    }
  });

  it("carries the true dimensions, not the thumbnail's", () => {
    const container = render(<Attachments attachments={[ACT]} />);
    const image = container.querySelector("img")!;
    expect(image.getAttribute("width")).toBe("2752");
    expect(image.getAttribute("height")).toBe("1536");
  });

  it("renders nothing at all when a message carries no attachment", () => {
    const container = render(<Attachments attachments={[]} />);
    expect(container.querySelectorAll("img")).toHaveLength(0);
  });

  it("shows the filename, the true size and the stated classification", () => {
    const container = render(<Attachments attachments={[ACT]} />);
    const caption = container.querySelector("figcaption")!.textContent ?? "";
    expect(caption).toContain(ACT.filename);
    expect(caption).toContain("2752×1536");
    expect(caption).toContain("protected");
    expect(container.querySelector(".class-protected")).not.toBeNull();
  });

  it("renders one figure per attachment, in the order given", () => {
    const second: AttachmentView = { ...ACT, id: "second", position: 2, filename: "b.png", sha256: "b".repeat(64) };
    const container = render(<Attachments attachments={[ACT, second]} />);
    const names = Array.from(container.querySelectorAll("img")).map((image) =>
      image.getAttribute("alt"),
    );
    expect(names).toEqual([ACT.filename, "b.png"]);
  });

  it("renders nothing at all when the message has no attachments field", () => {
    const container = render(<Attachments attachments={undefined} />);
    expect(container.querySelector(".attachments")).toBeNull();
    expect(container.querySelectorAll("img")).toHaveLength(0);
  });

  it("a reopened conversation resolves the same bytes by the same digest", () => {
    // The URL is a pure function of the content digest, so a message read back
    // later resolves exactly what was stored — no session, no signed link, no
    // expiry.
    const first = api.attachmentUrl(ACT.sha256);
    const later = api.attachmentUrl(ACT.sha256);
    expect(later).toBe(first);
    expect(first).toContain(ACT.sha256);
  });
});

// --- video and audio, owner execution order, 22 September 2026 ------------------
//
// The same defect class as the img-src one above, one media element over: a
// <video> or <audio> at the loopback origin is refused by the webview before any
// request is made unless `media-src` permits it, and the failure looks exactly
// like a broken file rather than like a policy.

const VIDEO: AttachmentView = {
  ...ACT,
  id: "01a0cbb8-0000-7000-8000-000000000001",
  filename: "a-real-clip.mp4",
  media_type: "video/mp4",
  modality: "video",
  duration_seconds: 9,
  sha256: "b".repeat(64),
};

const RECORDING: AttachmentView = {
  ...ACT,
  id: "01a0cbb8-0000-7000-8000-000000000002",
  filename: "a-real-recording.wav",
  media_type: "audio/wav",
  modality: "audio",
  duration_seconds: 22.38,
  width: 0,
  height: 0,
  sha256: "c".repeat(64),
};

describe("the policy permits the media the owner can now attach", () => {
  it("permits video and audio from the governed loopback route", () => {
    const sources = policy()["media-src"] ?? [];
    expect(
      sources.includes(API_BASE),
      `media-src is ${JSON.stringify(sources)} and must permit ${API_BASE}; a <video> ` +
        "or <audio> at that origin is otherwise refused before any request is made",
    ).toBe(true);
    expect(sources).toContain("'self'");
    expect(sources).toContain("blob:");
  });

  it("opens nothing wider for media than for images", () => {
    const sources = policy()["media-src"] ?? [];
    expect(sources).not.toContain("*");
    expect(sources).not.toContain("https:");
    expect(sources.filter((source) => source.startsWith("http")).sort()).toEqual([API_BASE]);
    // And the rest of the policy is untouched by this addition.
    expect(policy()["default-src"]).toEqual(["'self'"]);
    expect(policy()["connect-src"]).toEqual(["'self'", API_BASE]);
  });
});

describe("the thread renders each medium as what it is", () => {
  it("a video renders as a playable video at its own digest", () => {
    const shown = render(<Attachments attachments={[VIDEO]} />);
    const element = shown.querySelector("video");
    expect(element, "a video attachment must render a <video>, not an <img>").not.toBeNull();
    expect(element!.getAttribute("src")).toBe(api.attachmentUrl(VIDEO.sha256));
    expect(element!.hasAttribute("controls")).toBe(true);
    expect(shown.querySelector("img")).toBeNull();
    expect(shown.textContent).toContain("a-real-clip.mp4");
    expect(shown.textContent).toContain("0:09");
  });

  it("a recording renders as playable audio and says its length, not its pixels", () => {
    const shown = render(<Attachments attachments={[RECORDING]} />);
    const element = shown.querySelector("audio");
    expect(element, "an audio attachment must render an <audio>").not.toBeNull();
    expect(element!.getAttribute("src")).toBe(api.attachmentUrl(RECORDING.sha256));
    expect(element!.hasAttribute("controls")).toBe(true);
    expect(shown.querySelector("img")).toBeNull();
    expect(shown.textContent).toContain("a-real-recording.wav");
    expect(shown.textContent).toContain("0:22");
    // A recording has no dimensions, and saying "0×0" would be noise dressed
    // as information.
    expect(shown.textContent).not.toContain("0×0");
  });

  it("an image is unchanged: still an <img>, still its true dimensions", () => {
    const shown = render(<Attachments attachments={[ACT]} />);
    expect(shown.querySelector("img")).not.toBeNull();
    expect(shown.querySelector("video")).toBeNull();
    expect(shown.querySelector("audio")).toBeNull();
    expect(shown.textContent).toContain("2752×1536");
  });
});
