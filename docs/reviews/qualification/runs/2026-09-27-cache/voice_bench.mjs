// The Voice qualification driver — owner order of 27 September 2026, §6; idle rule and
// wait limit corrected for the live cache experiment (remaining latency work).
//
// Drives the unmodified desktop frontend (its dev server, pointed at the isolated scratch
// service) in headless Brave, and **replaces only the microphone**: before the page loads,
// `navigator.mediaDevices.getUserMedia` is made to return a MediaStream fed from an
// AudioContext the driver controls, so each utterance can be spoken when the conversation
// calls for it — after her answer has finished playing, or while it is still being made.
// Everything downstream of the device (the frontend's capture worklet, ordered sender,
// polling, speech collection, the real playback worklet, its reports) is the shipped code.
//
// Records, per turn, the exact wall time the driver's speech started and ended, and the
// DOM as the frontend displayed it. The playback figures come from the frontend's own
// reports (the service log and the scratch store), gathered by `voice_bench_extract.py`.
//
// Usage: node voice_bench.mjs CDP_PORT PLAN.json SESSION_INDEX OUT.json [evict_first]
import { readFileSync, writeFileSync } from "node:fs";

const [port, planPath, sessionIndexRaw, out] = process.argv.slice(2);
const plan = JSON.parse(readFileSync(planPath, "utf8"));
const session = plan.sessions[Number(sessionIndexRaw)];
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
    if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 500));
    return r.result?.result?.value;
  };
  return { send, on: (fn) => listeners.push(fn), evaluate, close: () => ws.close() };
}

// The microphone, replaced: an AudioContext whose destination stream is what getUserMedia
// returns. `__valSay` plays one utterance into it and reports when it started and how long
// it lasts; between utterances the stream carries digital silence.
const MICROPHONE = `(() => {
  // The frontend's own playback worklet ("val-playback") posts started / completed /
  // underrun / stopped to the page; a listener is added beside the frontend's own, so
  // the driver knows when her audio really plays and ends, and whether it ever gapped.
  window.__valPlayback = [];
  const NativeNode = window.AudioWorkletNode;
  window.AudioWorkletNode = class extends NativeNode {
    constructor(context, name, options) {
      super(context, name, options);
      if (name === "val-playback") {
        this.port.addEventListener("message", (e) => {
          try { window.__valPlayback.push({ wall: Date.now(), ...e.data }); } catch {}
        });
      }
    }
  };
  const ctx = new AudioContext({ sampleRate: 48000 });
  const dest = ctx.createMediaStreamDestination();
  const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia = async (constraints) => {
    if (constraints && constraints.audio) { await ctx.resume(); return dest.stream; }
    return original(constraints);
  };
  window.__valSay = async (b64, rate) => {
    await ctx.resume();
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const samples = new Int16Array(bytes.buffer);
    const buffer = ctx.createBuffer(1, samples.length, rate);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < samples.length; i++) channel[i] = samples[i] / 32768;
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(dest);
    const startsAt = ctx.currentTime + 0.05;
    source.start(startsAt);
    const wallStart = Date.now() + 50 + Math.round((ctx.outputLatency || 0) * 1000);
    return { wall_start: wallStart, duration_s: samples.length / rate };
  };
})();`;

const cdp = await connect(port);
const events = [];
const consoleLines = [];
await cdp.send("Runtime.enable");
await cdp.send("Page.enable");
cdp.on((m) => {
  if (m.method === "Runtime.consoleAPICalled") {
    const text = m.params.args.map((a) => a.value ?? a.description).join(" ");
    if (text.startsWith("DOM ")) { try { events.push(JSON.parse(text.slice(4))); } catch {} }
    else consoleLines.push(text.slice(0, 300));
  }
});
await cdp.send("Page.addScriptToEvaluateOnNewDocument", { source: MICROPHONE });
await cdp.send("Page.navigate", { url: "http://127.0.0.1:5173/" });
for (let i = 0; i < 150; i++) {
  if (await cdp.evaluate(`!!document.querySelector('.voice-controls button')`)) break;
  await sleep(200);
}
await cdp.evaluate(`(() => {
  const state = () => ({
    wall: Date.now(),
    voice: document.querySelector('.voice-state')?.textContent ?? null,
    progress: document.querySelector('.response-progress')?.textContent ?? null,
  });
  let last = JSON.stringify({ ...state(), wall: 0 });
  window.__valState = state;
  const observer = new MutationObserver(() => {
    const now = state(); const s = JSON.stringify({ ...now, wall: 0 });
    if (s !== last) { last = s; console.log('DOM ' + JSON.stringify(now)); }
  });
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  return true;
})()`);

const state = () => cdp.evaluate(`window.__valState()`);
// Idle: only listening, and nothing of hers in progress. The readiness line ("Warming
// up…", truthful while a prefix is cold) is not her speaking, and waiting on it held the
// earlier driver past its limit after long answers (2026-09-26 runs C1, C4).
const idle = (s) =>
  s.voice === "Voice On · Mic Listening" && !/writing|Preparing|Thinking/.test(s.progress || "");
const busy = (s) => /Speaking|Thinking|Transcribing/.test(s.voice || "") || !!s.progress;

// Voice on, then wait for Ready as the desktop shows it.
const clickedAt = Date.now();
await cdp.evaluate(`document.querySelector('.voice-controls button').click()`);
let readyAt = null;
for (let i = 0; i < 1200; i++) {
  const s = await state();
  if (s.voice === "Voice On · Mic Listening" && !(s.progress || "").includes("Warming up")) { readyAt = s.wall; break; }
  await sleep(100);
}

// Wait until her answer has finished **playing**: the playback worklet's last event is a
// completion or a stop, nothing has played for 0.6 s, and the display is back to plain
// listening. Returns the wall time of that last completion — the end of her audio.
async function waitIdleAfterAnswer(sinceWall, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const [s, last] = await Promise.all([state(), cdp.evaluate(`(() => { const p = window.__valPlayback; return p.length ? p[p.length - 1] : null; })()`)]);
    const played = last !== null && last.wall > sinceWall;
    if (played && (last.type === "completed" || last.type === "stopped") && Date.now() - last.wall >= 600 && idle(s)) {
      return { idle_since: last.wall, saw_answer: true };
    }
    await sleep(50);
  }
  return { idle_since: null, saw_answer: false, timed_out: true };
}

const turns = [];
let previousSpeechEnd = readyAt ?? Date.now();
for (const [index, turn] of session.turns.entries()) {
  let waited = null;
  if (index > 0 && turn.when === "after_playback") {
    waited = await waitIdleAfterAnswer(previousSpeechEnd, 240000);
    const since = waited.idle_since ?? Date.now();
    const remaining = since + turn.gap_s * 1000 - Date.now();
    if (remaining > 0) await sleep(remaining);
  } else if (index > 0 && turn.when === "after_speech") {
    const remaining = previousSpeechEnd + turn.gap_s * 1000 - Date.now();
    if (remaining > 0) await sleep(remaining);
  } else if (index === 0) {
    await sleep(1000);
  }
  const said = await cdp.evaluate(`window.__valSay(${JSON.stringify(turn.pcm16_b64)}, ${plan.rate})`);
  const speechEnd = said.wall_start + Math.round(said.duration_s * 1000);
  turns.push({
    label: turn.label, class: turn.class, text: turn.text, when: turn.when, gap_s: turn.gap_s,
    internal_pauses_s: turn.internal_pauses_s, speech_start_wall: said.wall_start, speech_end_wall: speechEnd,
    previous_answer_idle_since: waited?.idle_since ?? null, previous_wait_timed_out: waited?.timed_out ?? false,
  });
  previousSpeechEnd = speechEnd;
  await sleep(Math.max(0, speechEnd - Date.now()));
}
const last = await waitIdleAfterAnswer(previousSpeechEnd, 240000);
await sleep(1500);
const playback = await cdp.evaluate(`window.__valPlayback`);
for (const [index, turn] of turns.entries()) {
  const until = index + 1 < turns.length ? turns[index + 1].speech_start_wall : Number.MAX_SAFE_INTEGER;
  const first = playback.find((e) => e.type === "started" && e.wall > turn.speech_end_wall && e.wall < until);
  turn.worklet_first_started_wall = first ? first.wall : null;
  turn.worklet_underruns = playback.filter((e) => e.type === "underrun" && e.wall > turn.speech_end_wall && e.wall < until).length;
}
const offAt = Date.now();
await cdp.evaluate(`(() => { const b = document.querySelector('.voice-controls button'); if (b && b.textContent === 'Voice off') b.click(); })()`);
await sleep(1500);
writeFileSync(out, JSON.stringify({
  session: session.name, voice_on_click_wall: clickedAt, ready_displayed_wall: readyAt,
  voice_on_to_ready_displayed_s: readyAt === null ? null : (readyAt - clickedAt) / 1000,
  turns, last_answer_idle: last, voice_off_wall: offAt, playback_events: playback, dom_events: events, console: consoleLines.slice(0, 200),
}, null, 1) + "\n");
console.log(JSON.stringify({ session: session.name, ready_s: readyAt === null ? null : (readyAt - clickedAt) / 1000, turns: turns.length, dom_events: events.length }));
cdp.close();
process.exit(0);
