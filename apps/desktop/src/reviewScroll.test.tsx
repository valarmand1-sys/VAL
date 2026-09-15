// @vitest-environment jsdom
//
// The Review classifications view scrolls through its whole content — defect
// found in owner review, 14 September 2026: the thread is a fixed-height
// column that clips overflow, and the review block had no scroll rule, so a
// tall review's tail sat below the window edge.
//
// What these tests establish, and what they do not. jsdom has no layout
// engine: nothing here measures a viewport, a fold, or a pixel. They mount
// the real ReviewPanel against the real stylesheet and prove two things:
// (1) every control the workflow needs — the card, the second-determination
// selector, Record label, every disagreement card, Record a review and its
// form, Next — is rendered *inside* the `.review` element, and nothing
// interactive is rendered outside it; (2) `.review` is, by the stylesheet's
// cascade as applied to that rendered element, the scrolling flex region of
// the thread (overflow-y auto, min-height 0, flex-grow), and the composer and
// footer that follow it in the shell are not fixed or sticky. Physical
// reachability at a given window size is verified by hand in the native
// desktop window; the tests do not claim it.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import type { LabelledExchangeView, QueuedExchangeView, ReviewProgressView } from "./api";
// The real stylesheet, injected into the document by Vite under vitest's
// `css.include` (vite.config.ts) — without that, vitest stubs it to nothing.
import "./styles.css";

const fixtures = vi.hoisted(() => ({
  queue: [] as QueuedExchangeView[],
  disagreements: [] as LabelledExchangeView[],
  labelled: null as LabelledExchangeView | null,
}));

vi.mock("./api", async (importOriginal) => {
  const original = await importOriginal<typeof import("./api")>();
  const progress: ReviewProgressView = {
    labelled: 8,
    target: 50,
    agreements: 5,
    inclusion_disagreements: 3,
    zero_tolerance_failures: 0,
    open_disagreements: 2,
    eligible_unlabelled: 23,
  };
  return {
    ...original,
    api: {
      ...original.api,
      reviewQueue: async () => fixtures.queue,
      reviewProgress: async () => progress,
      reviewDisagreements: async () => fixtures.disagreements,
      labelExchange: async () => {
        if (fixtures.labelled === null) throw new Error("no reveal fixture");
        return fixtures.labelled;
      },
      reviewExchange: async () => {
        throw new Error("recording a review is not exercised here");
      },
    },
  };
});

import { ReviewPanel } from "./App";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean | undefined;
}

const LONG = Array.from({ length: 40 }, (_, i) => `Line ${i + 1} of a long exchange.`).join("\n");

function queued(id: string): QueuedExchangeView {
  return {
    classification_id: id,
    conversation_id: "conversation-1",
    conversation_title: "A long conversation",
    message_id: `message-${id}`,
    content: LONG,
    classified_at: "2026-09-14T19:16:52-05:00",
  };
}

function disagreement(id: string, open: boolean): LabelledExchangeView {
  return {
    classification_id: id,
    conversation_id: "conversation-1",
    conversation_title: "A long conversation",
    message_id: `message-${id}`,
    content: LONG,
    label: {
      id: `label-${id}`,
      label: "not_consequential",
      exclusion_determination: "no_choice_present",
      labelled_by: "user",
      created_at: "2026-09-14T20:00:00-05:00",
    },
    verdict: "consequential",
    hard_exclusion: null,
    agreement: "zero_tolerance_failure",
    open_disagreement: open,
    reviews: open
      ? []
      : [
          {
            id: `review-${id}`,
            conclusion: "classifier_upheld_label_wrong",
            reason: "On reflection the choice did bind later work.",
            tuning_state: null,
            tuning_change: null,
            tuning_verification: null,
            created_at: "2026-09-14T20:05:00-05:00",
          },
        ],
  };
}

const CONTROLS = "button, select, textarea, input";

let root: Root | null = null;
let host: HTMLElement | null = null;

beforeAll(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  if (document.styleSheets.length === 0) throw new Error("styles.css was not injected");
});

afterEach(async () => {
  if (root !== null) {
    const done = root;
    await act(async () => done.unmount());
    root = null;
  }
  host?.remove();
  host = null;
  fixtures.queue = [];
  fixtures.disagreements = [];
  fixtures.labelled = null;
});

/** Mount the real panel inside a `.thread` host, as the app shell does. */
async function mount(): Promise<{ thread: HTMLElement; review: HTMLElement }> {
  host = document.createElement("main");
  host.className = "thread";
  document.body.append(host);
  root = createRoot(host);
  const mounted = root;
  await act(async () => mounted.render(<ReviewPanel onRefused={() => undefined} />));
  const review = host.querySelector<HTMLElement>(".review");
  if (review === null) throw new Error("the panel did not render its .review region");
  return { thread: host, review };
}

function buttonNamed(scope: ParentNode, text: string): HTMLButtonElement {
  const match = [...scope.querySelectorAll("button")].find((b) => b.textContent?.trim() === text);
  if (match === undefined) throw new Error(`no button "${text}"`);
  return match;
}

async function click(button: HTMLButtonElement): Promise<void> {
  await act(async () => button.click());
}

/** Every interactive control lives inside the scroll region, and the last one is `text`. */
function expectAllControlsInside(thread: HTMLElement, review: HTMLElement, lastText: string): void {
  const all = [...thread.querySelectorAll<HTMLElement>(CONTROLS)];
  expect(all.length).toBeGreaterThan(0);
  for (const control of all) expect(review.contains(control)).toBe(true);
  const last = all[all.length - 1];
  expect(last?.textContent?.trim() || last?.tagName.toLowerCase()).toBe(lastText);
}

describe("the review region is the thread's scrolling flex child", () => {
  it("scrolls the rendered .review element and clips at the thread, per the real stylesheet", async () => {
    fixtures.queue = [queued("c1")];
    const { thread, review } = await mount();
    const style = getComputedStyle(review);
    expect(style.overflowY).toBe("auto");
    expect(style.minHeight).toBe("0px");
    expect(style.flexGrow).toBe("1");
    const shell = getComputedStyle(thread);
    expect(shell.display).toBe("flex");
    expect(shell.flexDirection).toBe("column");
    expect(shell.overflow).toBe("hidden");
  });

  it("does not fix or stick the composer or footer over the region", () => {
    for (const [tag, className] of [
      ["form", "composer"],
      ["footer", "signals"],
    ] as const) {
      const element = document.createElement(tag);
      element.className = className;
      document.body.append(element);
      const position = getComputedStyle(element).position;
      expect(["fixed", "sticky"]).not.toContain(position);
      element.remove();
    }
  });
});

describe("every control of the workflow is rendered inside the scroll region", () => {
  it("1. a normal card: content, the three choices and Record label", async () => {
    fixtures.queue = [queued("c1")];
    const { thread, review } = await mount();
    expect(review.querySelector(".review-card .content")?.textContent).toBe(LONG);
    expectAllControlsInside(thread, review, "Record label");
  });

  it("2. a not-consequential card adds the second-determination selector before Record label", async () => {
    fixtures.queue = [queued("c1")];
    const { thread, review } = await mount();
    await click(buttonNamed(review, "not consequential"));
    const selector = review.querySelector<HTMLSelectElement>(".review-determination select");
    expect(selector).not.toBeNull();
    expect(selector?.options.length).toBeGreaterThan(2);
    const record = buttonNamed(review, "Record label");
    expect(record.disabled).toBe(true);
    // The selector precedes Record label in document order, both inside the region.
    expect(selector?.compareDocumentPosition(record) ?? 0).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expectAllControlsInside(thread, review, "Record label");
  });

  it("3. multiple disagreement cards all render inside the region, after the current card", async () => {
    fixtures.queue = [queued("c1")];
    fixtures.disagreements = [
      disagreement("d1", false),
      disagreement("d2", false),
      disagreement("d3", false),
    ];
    const { thread, review } = await mount();
    const cards = [...review.querySelectorAll(".review-card")];
    expect(cards).toHaveLength(4);
    expect(review.querySelectorAll("h3")[0]?.textContent).toBe("Disagreements");
    expectAllControlsInside(thread, review, "Record a review");
  });

  it("4. an open disagreement: Record a review, then its form, are the region's final controls", async () => {
    fixtures.queue = [queued("c1")];
    fixtures.disagreements = [disagreement("d1", false), disagreement("d2", true)];
    const { thread, review } = await mount();
    const open = review.querySelector(".review-card.open");
    expect(open).not.toBeNull();
    expectAllControlsInside(thread, review, "Record a review");
    const openButton = [...review.querySelectorAll("button")].filter(
      (b) => b.textContent?.trim() === "Record a review",
    );
    await click(openButton[openButton.length - 1] as HTMLButtonElement);
    expect(open?.querySelector("textarea")).not.toBeNull();
    expect(open?.querySelector("select")).not.toBeNull();
    expectAllControlsInside(thread, review, "Cancel");
  });

  it("5. after a label is recorded, the reveal and its Next button are inside the region", async () => {
    fixtures.queue = [queued("c1"), queued("c2")];
    fixtures.labelled = { ...disagreement("c1", true), open_disagreement: true };
    const { thread, review } = await mount();
    await click(buttonNamed(review, "consequential"));
    await click(buttonNamed(review, "Record label"));
    expect(review.textContent).toContain("Your label is stored.");
    const next = buttonNamed(review, "Next");
    expect(review.contains(next)).toBe(true);
    await click(next);
    expect(review.querySelector(".review-card .content")?.textContent).toBe(LONG);
    expectAllControlsInside(thread, review, "Record label");
  });
});
