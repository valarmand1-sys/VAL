// @vitest-environment jsdom
//
// The conversation view stays where it should — owner's physical check, 2 October 2026:
// every send and every answer returned a long conversation to the top.
//
// jsdom has no layout, so the geometry is supplied: what is tested is the rule — follow
// the newest content unless he has scrolled up, and keep his place when the scrolling
// element is replaced — not pixels. The real behaviour is his to see in the window.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { MessagesPane, newScrollMemory, type ScrollMemory } from "./messagesPane";

(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
let height = 1000;

beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  height = 1000;
  Object.defineProperty(HTMLElement.prototype, "scrollHeight", {
    configurable: true,
    get: () => height,
  });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get: () => 400,
  });
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

function show(memory: ScrollMemory, conversation: string, lines: number, key = "settled"): HTMLElement {
  act(() =>
    root.render(
      <MessagesPane key={key} memory={memory} conversation={conversation}>
        {Array.from({ length: lines }, (_, index) => (
          <p key={index}>line {index}</p>
        ))}
      </MessagesPane>,
    ),
  );
  return host.querySelector(".messages") as HTMLElement;
}

function scrollTo(pane: HTMLElement, top: number): void {
  pane.scrollTop = top;
  act(() => {
    pane.dispatchEvent(new Event("scroll", { bubbles: true }));
  });
}

describe("the conversation view", () => {
  it("follows the newest exchange while he is at the bottom", () => {
    const memory = newScrollMemory();
    const pane = show(memory, "c1", 10);
    expect(pane.scrollTop).toBe(1000);
    height = 1600;
    show(memory, "c1", 16);
    expect(pane.scrollTop).toBe(1600);
  });

  it("stays at the newest exchange when a send replaces the scrolling element", () => {
    const memory = newScrollMemory();
    show(memory, "c1", 10, "settled");
    height = 1300;
    const replaced = show(memory, "c1", 13, "streaming");
    expect(replaced.scrollTop).toBe(1300);
  });

  it("leaves him where he is reading once he has scrolled up", () => {
    const memory = newScrollMemory();
    const pane = show(memory, "c1", 10);
    scrollTo(pane, 120);
    expect(memory.following).toBe(false);
    height = 1600;
    show(memory, "c1", 16);
    expect(pane.scrollTop).toBe(120);
    const replaced = show(memory, "c1", 17, "streaming");
    expect(replaced.scrollTop).toBe(120);
  });

  it("follows again once he returns to the bottom, and in another conversation", () => {
    const memory = newScrollMemory();
    const pane = show(memory, "c1", 10);
    scrollTo(pane, 120);
    scrollTo(pane, 1000 - 400 - 10);
    expect(memory.following).toBe(true);
    scrollTo(pane, 0);
    expect(memory.following).toBe(false);
    height = 900;
    const other = show(memory, "c2", 9, "other");
    expect(other.scrollTop).toBe(900);
  });
});
