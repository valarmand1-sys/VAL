// VAL's answers render as prose, not as their own control syntax.
//
// Owner defect report, 20 September 2026: the first genuine image answer showed
// `### Characters and action` literally in the thread. The renderer put the
// message into a text node, and a text node shows what it is given.
//
// These pin the reader. The renderer that consumes it builds React elements from
// this structure and never HTML, so what is proven here — that model text stays
// *text* in every branch — is what keeps markup and scripts out of the thread.

import { describe, expect, it } from "vitest";

import { parseInline, parseMarkdown } from "./markdown";

const text = (value: string) => ({ kind: "text", text: value });

describe("blocks", () => {
  it("reads a heading rather than showing its hashes", () => {
    const blocks = parseMarkdown("### Characters and action");
    expect(blocks).toEqual([
      { kind: "heading", level: 3, spans: [text("Characters and action")] },
    ]);
  });

  it("reads every heading level", () => {
    for (let level = 1; level <= 6; level += 1) {
      const blocks = parseMarkdown(`${"#".repeat(level)} Title`);
      expect(blocks[0]).toMatchObject({ kind: "heading", level });
    }
  });

  it("joins the lines of a paragraph and splits on a blank line", () => {
    const blocks = parseMarkdown("One line\nand its continuation.\n\nA second paragraph.");
    expect(blocks).toEqual([
      { kind: "paragraph", spans: [text("One line and its continuation.")] },
      { kind: "paragraph", spans: [text("A second paragraph.")] },
    ]);
  });

  it("reads bullet lists written either way", () => {
    for (const marker of ["-", "*"]) {
      const blocks = parseMarkdown(`${marker} first\n${marker} second`);
      expect(blocks).toEqual([
        { kind: "bullets", items: [[text("first")], [text("second")]] },
      ]);
    }
  });

  it("reads numbered lists and keeps their order", () => {
    const blocks = parseMarkdown("1. first\n2. second\n3. third");
    expect(blocks).toEqual([
      {
        kind: "numbers",
        items: [[text("first")], [text("second")], [text("third")]],
      },
    ]);
  });

  it("does not run a bullet list into a numbered one", () => {
    const blocks = parseMarkdown("- a\n1. b");
    expect(blocks.map((block) => block.kind)).toEqual(["bullets", "numbers"]);
  });

  it("keeps a heading, its prose and its list apart", () => {
    const blocks = parseMarkdown("## Setting\nA living room.\n\n- a sofa\n- a window");
    expect(blocks.map((block) => block.kind)).toEqual(["heading", "paragraph", "bullets"]);
  });

  it("leaves ordinary prose entirely alone", () => {
    const plain = "Good evening, my lord. The frame reads well.";
    expect(parseMarkdown(plain)).toEqual([{ kind: "paragraph", spans: [text(plain)] }]);
  });

  it("returns nothing for an empty message rather than an empty paragraph", () => {
    expect(parseMarkdown("")).toEqual([]);
    expect(parseMarkdown("   \n\n  ")).toEqual([]);
  });
});

describe("inline", () => {
  it("reads bold, italics and code", () => {
    expect(parseInline("**bold**")).toEqual([{ kind: "bold", text: "bold" }]);
    expect(parseInline("*slanted*")).toEqual([{ kind: "italic", text: "slanted" }]);
    expect(parseInline("`code`")).toEqual([{ kind: "code", text: "code" }]);
  });

  it("does not read bold as two italics", () => {
    expect(parseInline("**strong**")).toEqual([{ kind: "bold", text: "strong" }]);
  });

  it("keeps the text around a span", () => {
    expect(parseInline("before **middle** after")).toEqual([
      text("before "),
      { kind: "bold", text: "middle" },
      text(" after"),
    ]);
  });

  it("leaves markup inside code literal", () => {
    expect(parseInline("`**not bold**`")).toEqual([{ kind: "code", text: "**not bold**" }]);
  });

  it("leaves an unmatched marker as ordinary text", () => {
    expect(parseInline("2 * 3 = 6")).toEqual([text("2 * 3 = 6")]);
    expect(parseInline("a lone ** here")).toEqual([text("a lone ** here")]);
  });
});

describe("underscores belong to names, not to emphasis", () => {
  // Owner correction, 20 September 2026. Val discusses column names,
  // configuration keys, filenames and model identifiers constantly; reading the
  // middle of one as italics would mangle the very word she is being precise
  // about. Asterisks mark emphasis; an underscore is a character in a name.
  it.each([
    "model_call_image_inputs",
    "attachment_processing_events",
    "message_attachments",
    "gpt_5_6",
    "some_file_name",
    "VAL_OPENAI_API_KEY",
    "__init__",
    "a_b_c_d_e",
  ])("leaves %s exactly as written", (identifier) => {
    expect(parseInline(identifier)).toEqual([text(identifier)]);
  });

  it("leaves an identifier alone inside a sentence", () => {
    const line = "The binding lands on model_call_image_inputs, as the contract says.";
    expect(parseInline(line)).toEqual([text(line)]);
  });

  it("leaves a whole paragraph of identifiers alone", () => {
    const line = "Both attachment_representations and attachment_processing_events are append-only.";
    expect(parseMarkdown(line)).toEqual([{ kind: "paragraph", spans: [text(line)] }]);
  });

  it("still emphasises with asterisks in the same sentence", () => {
    expect(parseInline("*see* model_call_image_inputs")).toEqual([
      { kind: "italic", text: "see" },
      text(" model_call_image_inputs"),
    ]);
  });

  it("leaves a snake_case identifier inside a list item alone", () => {
    expect(parseMarkdown("- model_call_image_inputs")).toEqual([
      { kind: "bullets", items: [[text("model_call_image_inputs")]] },
    ]);
  });

  it("leaves a snake_case identifier inside a heading alone", () => {
    expect(parseMarkdown("### attachment_processing_events")).toEqual([
      { kind: "heading", level: 3, spans: [text("attachment_processing_events")] },
    ]);
  });
});

describe("what it deliberately does not do", () => {
  it("never yields markup or a script — every branch is text", () => {
    const hostile = [
      "<script>alert(1)</script>",
      "<img src=x onerror=alert(1)>",
      "# <b>heading</b>",
      "- <iframe></iframe>",
      "1. <a href='javascript:alert(1)'>click</a>",
      "**<svg onload=alert(1)>**",
      "`</div><script>`",
    ].join("\n\n");
    const seen: string[] = [];
    for (const block of parseMarkdown(hostile)) {
      const spans = "spans" in block ? [block.spans] : block.items;
      for (const run of spans) for (const span of run) seen.push(span.text);
    }
    // The angle brackets survive as characters, which is the point: they are
    // text, and the view renders them through React as text.
    expect(seen.join("")).toContain("<script>alert(1)</script>");
    expect(seen.every((value) => typeof value === "string")).toBe(true);
  });

  it("renders no links, so a model-authored URL is never clickable", () => {
    const blocks = parseMarkdown("See [the site](https://example.com) for more.");
    expect(blocks).toEqual([
      { kind: "paragraph", spans: [text("See [the site](https://example.com) for more.")] },
    ]);
  });

  it("renders no images, so only governed attachments appear in a thread", () => {
    const blocks = parseMarkdown("![a picture](https://example.com/x.png)");
    expect(JSON.stringify(blocks)).toContain("![a picture]");
    expect(blocks[0]!.kind).toBe("paragraph");
  });

  it("does not rewrite the durable message: the text is carried through", () => {
    const original = "### Setting\n\nA **living room**, with a window.";
    const carried = parseMarkdown(original)
      .flatMap((block) => ("spans" in block ? block.spans : block.items.flat()))
      .map((span) => span.text)
      .join(" ");
    for (const word of ["Setting", "living room", "with a window"]) {
      expect(carried).toContain(word);
    }
  });
});
