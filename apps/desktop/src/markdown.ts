// A deliberately small Markdown reader — owner defect report, 20 September 2026.
//
// VAL's first genuine image answer displayed its own control syntax: the thread
// showed `### Characters and action` literally, because the renderer put the
// message's text into a text node and a text node is exactly what it says.
//
// This parses a **conservative subset** into a structure the view renders as
// ordinary React elements. Nothing here produces HTML, so there is no markup to
// inject and no script to execute: every piece of the message's own text ends up
// as a React text node, escaped by React itself. Links and images are
// deliberately NOT supported — a model-authored URL is not something this house
// renders as clickable or fetches, and the only images the thread shows are
// governed attachments it already holds.
//
// **The stored message is not touched.** This is presentation over the canonical
// content; `message.content` remains exactly what was persisted.

export type Inline =
  | { kind: "text"; text: string }
  | { kind: "bold"; text: string }
  | { kind: "italic"; text: string }
  | { kind: "code"; text: string };

export type Block =
  | { kind: "paragraph"; spans: Inline[] }
  | { kind: "heading"; level: number; spans: Inline[] }
  | { kind: "bullets"; items: Inline[][] }
  | { kind: "numbers"; items: Inline[][] };

// Bold before italic, so `**x**` is not read as an italic `*` around `*x*`.
// Inline code is matched first and its contents are never re-scanned, which is
// what makes ``**not bold**`` inside backticks stay literal.
const INLINE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\n]+\*)|(_[^_\n]+_)/;

export function parseInline(source: string): Inline[] {
  const spans: Inline[] = [];
  let rest = source;
  for (;;) {
    const found = INLINE.exec(rest);
    if (found === null || found.index === undefined) break;
    if (found.index > 0) spans.push({ kind: "text", text: rest.slice(0, found.index) });
    const marked = found[0];
    if (marked.startsWith("`")) {
      spans.push({ kind: "code", text: marked.slice(1, -1) });
    } else if (marked.startsWith("**")) {
      spans.push({ kind: "bold", text: marked.slice(2, -2) });
    } else {
      spans.push({ kind: "italic", text: marked.slice(1, -1) });
    }
    rest = rest.slice(found.index + marked.length);
  }
  if (rest.length > 0) spans.push({ kind: "text", text: rest });
  return spans.length > 0 ? spans : [{ kind: "text", text: "" }];
}

const HEADING = /^(#{1,6})\s+(.*)$/;
const BULLET = /^\s*[-*]\s+(.*)$/;
const NUMBER = /^\s*\d+[.)]\s+(.*)$/;

/** The message's text as blocks. Unrecognised syntax stays ordinary text. */
export function parseMarkdown(source: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let bullets: Inline[][] = [];
  let numbers: Inline[][] = [];

  const closeParagraph = (): void => {
    if (paragraph.length > 0) {
      blocks.push({ kind: "paragraph", spans: parseInline(paragraph.join(" ")) });
      paragraph = [];
    }
  };
  const closeLists = (): void => {
    if (bullets.length > 0) {
      blocks.push({ kind: "bullets", items: bullets });
      bullets = [];
    }
    if (numbers.length > 0) {
      blocks.push({ kind: "numbers", items: numbers });
      numbers = [];
    }
  };
  const closeAll = (): void => {
    closeParagraph();
    closeLists();
  };

  for (const line of source.split("\n")) {
    if (line.trim() === "") {
      closeAll();
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading !== null) {
      closeAll();
      blocks.push({
        kind: "heading",
        level: heading[1]!.length,
        spans: parseInline(heading[2]!.trim()),
      });
      continue;
    }
    const numbered = NUMBER.exec(line);
    if (numbered !== null) {
      closeParagraph();
      if (bullets.length > 0) closeLists();
      numbers.push(parseInline(numbered[1]!));
      continue;
    }
    const bulleted = BULLET.exec(line);
    if (bulleted !== null) {
      closeParagraph();
      if (numbers.length > 0) closeLists();
      bullets.push(parseInline(bulleted[1]!));
      continue;
    }
    closeLists();
    paragraph.push(line.trim());
  }
  closeAll();
  return blocks;
}
