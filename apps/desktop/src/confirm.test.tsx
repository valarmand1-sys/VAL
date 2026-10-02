// @vitest-environment jsdom
//
// A question he can actually answer — owner's physical check, 2 October 2026: "Remove
// does nothing." The shell's webview shows no dialog for `window.confirm`; it returns
// false at once, so every confirmed act in the app was silently declined.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { askToConfirm, ConfirmHost } from "./confirm";

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root.render(<ConfirmHost />));
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

function press(label: string): void {
  const button = [...host.querySelectorAll("button")].find((b) => b.textContent === label);
  expect(button, `a "${label}" button`).toBeDefined();
  act(() => button!.click());
}

describe("asking in the window", () => {
  it("shows the question and does the act only when he confirms", async () => {
    let answer: boolean | null = null;
    act(() => {
      void askToConfirm("Remove this conversation from active use?", "Remove").then((yes) => {
        answer = yes;
      });
    });
    expect(host.textContent).toContain("Remove this conversation from active use?");
    expect(answer).toBeNull();
    press("Remove");
    await Promise.resolve();
    expect(answer).toBe(true);
    expect(host.querySelector(".confirm")).toBeNull();
  });

  it("Cancel declines, and a second question while one is open is declined", async () => {
    let first: boolean | null = null;
    let second: boolean | null = null;
    act(() => {
      void askToConfirm("First?").then((yes) => {
        first = yes;
      });
      void askToConfirm("Second?").then((yes) => {
        second = yes;
      });
    });
    await Promise.resolve();
    expect(second).toBe(false);
    expect(host.textContent).toContain("First?");
    press("Cancel");
    await Promise.resolve();
    expect(first).toBe(false);
  });
});

describe("the app's own source", () => {
  const modules = import.meta.glob("./App.tsx", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;
  const source = modules["./App.tsx"]!;

  it("asks nothing through window.confirm, which the shell cannot show", () => {
    expect(source).not.toContain("window.confirm");
  });

  it("writes the composer from two places only: his typing, and a settled send", () => {
    // Physical check, 2 October 2026: a spoken request was reported sitting in the
    // composer after Voice off. No path writes speech into the composer; this holds it.
    const writes = source.match(/setComposer\(/g) ?? [];
    expect(writes.length).toBe(2);
    expect(source).toContain("onChange={(event) => setComposer(event.target.value)}");
    expect(source).toContain('setComposer("")');
  });

  it("labels the title's control Edit, under the title", () => {
    expect(source).toContain('<div className="conversation-title">');
    expect(source).not.toMatch(/>\s*Rename\s*</);
  });
});
