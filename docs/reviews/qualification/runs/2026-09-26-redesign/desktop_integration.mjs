// Drive the real desktop frontend through the Chrome DevTools Protocol — 26 September 2026.
//
// Release-gaps order §6. The frontend under test is the unmodified `apps/desktop` source,
// served by its own dev server and pointed at the isolated scratch service; the browser
// is headless Brave whose microphone is a prepared WAV file. This script clicks the one
// door to a microphone — the visible "Voice on" control — exactly once, watches the DOM
// (the voice state label, the progress line and the thread) with a MutationObserver
// stamped on the page's clock, and clicks "Voice off" at the end. Nothing here reads
// audio, injects text or touches the service directly: what is measured is what the
// desktop displayed and when. The desktop's own timing report and playback reports
// reach the scratch service as they would production's.
//
// Usage: node desktop_integration.mjs CDP_PORT DURATION_S OUT.json
import { writeFileSync } from "node:fs";

const [port, durationS, out] = process.argv.slice(2);

async function connect(port) {
  let targets = [];
  for (let i = 0; i < 100; i++) {
    try {
      targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
      if (targets.some((t) => t.type === "page")) break;
    } catch {}
    await new Promise((r) => setTimeout(r, 200));
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
  return { send, on: (fn) => listeners.push(fn), evaluate, close: () => ws.close() };
}

const cdp = await connect(port);
const events = [];
const consoleLines = [];
await cdp.send("Runtime.enable");
await cdp.send("Page.enable");
cdp.on((m) => {
  if (m.method === "Runtime.consoleAPICalled") {
    const text = m.params.args.map((a) => a.value ?? a.description).join(" ");
    if (text.startsWith("DOM ")) { try { events.push(JSON.parse(text.slice(4))); } catch { consoleLines.push(text); } }
    else consoleLines.push(text);
  }
});
await cdp.send("Page.navigate", { url: "http://127.0.0.1:5173/" });
// Wait for the composer.
let composer = false;
for (let i = 0; i < 100 && !composer; i++) {
  composer = await cdp.evaluate(`!!document.querySelector('.voice-controls button')`);
  if (!composer) await new Promise((r) => setTimeout(r, 200));
}
if (!composer) { console.error("the desktop frontend did not render its composer: " + (await cdp.evaluate(`document.documentElement.outerHTML.slice(0, 400)`))); process.exit(2); }
const t0 = Date.now();
await cdp.evaluate(`(() => {
  const state = () => ({
    wall: Date.now(),
    voice: document.querySelector('.voice-state')?.textContent ?? null,
    progress: document.querySelector('.response-progress')?.textContent ?? null,
    messages: Array.from(document.querySelectorAll('[data-role], .message, article')).slice(-4).map((n) => (n.textContent || '').slice(0, 160)),
  });
  let last = JSON.stringify(state());
  console.log('DOM ' + last);
  const observer = new MutationObserver(() => {
    const now = state(); const s = JSON.stringify(now);
    if (s !== last) { last = s; console.log('DOM ' + s); }
  });
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  return true;
})()`);
const clickedAt = Date.now();
await cdp.evaluate(`(() => { const b = document.querySelector('.voice-controls button'); b.click(); return b.textContent; })()`);
await new Promise((r) => setTimeout(r, Number(durationS) * 1000));
const offAt = Date.now();
await cdp.evaluate(`(() => { const b = document.querySelector('.voice-controls button'); if (b && b.textContent === 'Voice off') b.click(); return b?.textContent; })()`);
await new Promise((r) => setTimeout(r, 1500));
writeFileSync(out, JSON.stringify({ page_loaded_wall: t0, voice_on_click_wall: clickedAt, voice_off_click_wall: offAt, dom_events: events, console: consoleLines.slice(0, 400) }, null, 1) + "\n");
console.log(JSON.stringify({ dom_events: events.length, console: consoleLines.length }));
cdp.close();
process.exit(0);
