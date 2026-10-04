// Typed work through the real desktop frontend — 3 October 2026 (owner order §7).
//
// The unmodified `apps/desktop` source, served by its dev server and pointed at the
// isolated scratch service; headless Brave, driven over the DevTools protocol. Every
// message is typed into the composer and sent with the Send button, as he does. Onset is
// the desktop's OWN measurement — the turn clock it logs as `val.turn.timing`: Send → the
// first answer text painted on screen (`firstPaintMs`) — and completion is its
// `completeMs`. Nothing here talks to the service directly.
//
// Sequence (frozen 3 October 2026 before it was run):
//   cold     the first message, sent as soon as the page shows the composer;
//   sustain  twelve differing messages in that conversation;
//   voice    Voice on (the visible control), wait until it is Ready, Voice off, and at
//            once a typed message, then another;
//   deep     Deep reasoning ticked (his deliberate choice), wait until the desktop shows
//            no preparation line, two messages; unticked, wait, one message;
//   changed  Deep reasoning ticked and a message sent at once (the message makes the
//            change), then unticked and a message sent at once, then one more.
//
// Usage: node desktop_typed.mjs CDP_PORT OUT.json
import { writeFileSync } from "node:fs";

const [port, out] = process.argv.slice(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function connect(port) {
  let targets = [];
  for (let i = 0; i < 100; i++) {
    try {
      targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
      if (targets.some((t) => t.type === "page")) break;
    } catch {}
    await sleep(200);
  }
  const page = targets.find((t) => t.type === "page");
  if (!page) throw new Error("no page target");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0; const pending = new Map(); const listeners = [];
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    else if (m.method) for (const l of listeners) l(m);
  };
  const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  const evaluate = async (expression) => {
    const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails));
    return r.result?.result?.value;
  };
  return { send, on: (fn) => listeners.push(fn), evaluate };
}

const cdp = await connect(port);
const timings = [];
const notes = [];
await cdp.send("Runtime.enable");
await cdp.send("Page.enable");
cdp.on((m) => {
  if (m.method !== "Runtime.consoleAPICalled") return;
  const args = m.params.args.map((a) => a.value ?? a.description);
  if (args[0] === "val.turn.timing") {
    try { timings.push(JSON.parse(args[1])); } catch {}
  }
});
await cdp.send("Page.navigate", { url: "http://127.0.0.1:5173/" });
for (let i = 0; i < 150; i++) {
  if (await cdp.evaluate(`!!document.querySelector('form.composer textarea')`)) break;
  await sleep(200);
}
const T0 = Date.now();
const note = (kind, facts = {}) => { const row = { at_s: +((Date.now() - T0) / 1000).toFixed(1), kind, ...facts }; notes.push(row); console.log(JSON.stringify(row)); };

const line = () => cdp.evaluate(`document.querySelector('.notice.cognition')?.textContent ?? null`);
const busy = () => cdp.evaluate(`document.querySelector('form.composer button[type=submit]')?.textContent === '…'`);

async function type(text, label) {
  const before = timings.length;
  const shown = await line();
  await cdp.evaluate(`(() => {
    const area = document.querySelector('form.composer textarea');
    const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
    set.call(area, ${JSON.stringify(text)});
    area.dispatchEvent(new Event('input', { bubbles: true }));
  })()`);
  await sleep(150);
  const stages = new Set();
  await cdp.evaluate(`document.querySelector('form.composer button[type=submit]').click()`);
  const sent = Date.now();
  while (timings.length === before && Date.now() - sent < 600000) {
    const stage = await cdp.evaluate(`document.querySelector('.message.val.streaming .content.pending.stage')?.textContent ?? null`);
    if (stage) stages.add(stage.slice(0, 40));
    await sleep(100);
  }
  const t = timings[before] ?? null;
  note(label, {
    text,
    line_before_send: shown,
    stages_seen: [...stages],
    first_paint_s: t?.clock?.firstPaintMs != null ? +(t.clock.firstPaintMs / 1000).toFixed(2) : null,
    first_delta_s: t?.clock?.firstDeltaMs != null ? +(t.clock.firstDeltaMs / 1000).toFixed(2) : null,
    complete_s: t ? +(t.completeMs / 1000).toFixed(2) : null,
    gateway_first_output_s: t?.service?.gateway_first_output_ms != null ? +(t.service.gateway_first_output_ms / 1000).toFixed(2) : null,
    notice: await cdp.evaluate(`document.querySelector('.notice:not(.cognition)')?.textContent?.slice(0, 120) ?? null`),
  });
  while (await busy()) await sleep(100);
  await sleep(1500); // he reads, then types the next one
}

async function waitNoLine(limitS = 240) {
  const began = Date.now();
  while (Date.now() - began < limitS * 1000) {
    if ((await line()) === null) return +((Date.now() - began) / 1000).toFixed(1);
    await sleep(250);
  }
  return null;
}

const deepBox = `document.querySelector('.composer-actions .deep-reasoning input')`;
const setDeep = (on) => cdp.evaluate(`(() => { const b = ${deepBox}; if (b && b.checked !== ${on}) b.click(); return b ? b.checked : null; })()`);

// cold
await type("Suggest a name for a small secondhand bookshop.", "cold_first_message");
// sustain
const sustain = [
  "Why that one?",
  "What is the difference between a producer and an executive producer?",
  "Give me a title for a film about an orchard.",
  "Which of those titles do you prefer, and why?",
  "What should I say when I answer the phone at the studio?",
  "How long should a cold open be?",
  "Name a famous ghost story.",
  "And who wrote it?",
  "Develop a short scene in prose, about two hundred words: a location scout arrives at a farm at dawn.",
  "Which line of that scene is strongest?",
  "Give me one sentence I could open tomorrow's crew meeting with.",
  "Thank you.",
];
for (const [i, text] of sustain.entries()) await type(text, `sustain_${i + 1}`);

// voice
const voiceButton = `document.querySelector('.voice-controls button')`;
await cdp.evaluate(`${voiceButton}.click()`);
const on = Date.now();
// Ready, as the desktop says it: Voice On, and its "Warming up" line gone (the line is
// shown from the session's own readiness facts; never "Ready" while the model is away).
let ready = null;
let warmed = false;
for (let i = 0; i < 1200; i++) {
  const label = await cdp.evaluate(`document.querySelector('.voice-state')?.textContent ?? ''`);
  const warming = await cdp.evaluate(`document.body.innerText.includes('Warming up')`);
  if (warming) warmed = true;
  if (label.startsWith("Voice On") && !warming && (warmed || Date.now() - on > 5000)) {
    ready = +((Date.now() - on) / 1000).toFixed(1);
    break;
  }
  await sleep(250);
}
note("voice_ready", { seconds: ready, label: await cdp.evaluate(`document.querySelector('.voice-state')?.textContent ?? null`) });
await sleep(3000);
await cdp.evaluate(`(() => { const b = ${voiceButton}; if (b && /off/i.test(b.textContent)) b.click(); return b?.textContent; })()`);
await sleep(500);
await type("What should I say if the composer calls tomorrow?", "first_after_voice");
await type("And if it is the producer?", "second_after_voice");

// deep, chosen first
note("deep_ticked", { checked: await setDeep(true) });
note("deep_ready_after_tick", { seconds: await waitNoLine() });
await type("Reason it through: is it cheaper to shoot three days on location or two days on a stage that costs twice as much per day? Say what you would need to know.", "deep_1");
await type("Now add a generator at a fixed cost to the location. Does that change it?", "deep_2");
note("deep_unticked", { checked: await setDeep(false) });
note("typed_ready_after_untick", { seconds: await waitNoLine() });
await type("Thank you. One more title for the orchard film, please.", "ordinary_after_deep");

// the change made by the message itself
await setDeep(true);
await type("Reason carefully: what are the risks of a night shoot with one generator?", "deep_sent_at_once");
await setDeep(false);
await type("And a short toast for the wrap dinner, please.", "ordinary_sent_at_once");
await type("Shorter.", "ordinary_next");

writeFileSync(out, JSON.stringify({ notes, timings }, null, 1));
process.exit(0);
