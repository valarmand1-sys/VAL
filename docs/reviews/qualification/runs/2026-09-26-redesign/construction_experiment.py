"""The request-construction repair experiment — release-gaps order of 26 September 2026, §4.

An isolated, authorised exception to the request-ordering (10 September) and same-role
canonicalization (17 September) rulings, for measurement only. Two conditions in two
processes, each on a fresh scratch store, through the real ordinary MEDIUM route (fast
route off):

* `as_is` — the request as production sends it: the record-state envelope and his words
  are two user messages that the local wire joins into one, so the model's last user
  block begins with a JSON envelope and ends with his words;
* `envelope_in_system` — `context.ENVELOPE_IN_SYSTEM`: the envelope follows the persona
  inside the system message, and the last user block is his words alone.

Matched recorded contexts: the recorded repeated-answer failures, "Recap that in one
sentence.", "Say that again, please.", thanks with genuine pending work, farewells after
a greeting, corrections and withdrawals, fabricated completion, capability questions,
ordinary substantive requests, and the two wrong-turn answers the desktop run of this
day produced on MEDIUM. Every answer is printed for reading; per final call the record
keeps the input tokens, the runtime's own time to first token and prompt count (from
`lms log stream`), Core's first visible text, the reasoning token count and the output
length; and, once per condition, the tail of the **rendered model input** as the runtime
logged it — the evidence of what the model actually saw. The persona checkpoint's reuse
is read from the engine's own "Prompt cache: using N/M" lines afterwards. Local, $0.

Usage: construction_experiment.py as_is|envelope_in_system OUT.json
"""

from __future__ import annotations

import json
import os
import plistlib
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        if name != "VAL_DATABASE_URL":
            os.environ[name] = value
URL = "postgresql+psycopg://localhost:5433/val_repro_test"
os.environ["VAL_DATABASE_URL"] = URL
for key in ("VAL_FAST_ROUTE_TIERS", "VAL_TIER1_ROUTE", "VAL_SPECULATION", "VAL_ADAPTIVE_GRACE", "VAL_OWNER_PRECEDENCE"):
    os.environ.pop(key, None)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

import val_gateway.context as context  # noqa: E402
from val_gateway.deliberate import send  # noqa: E402
from val_gateway.persona import seed  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.seal import SealRoute  # noqa: E402
from val_gateway.startup import start  # noqa: E402
from val_policy.light_conversation import FastRoute  # noqa: E402
from val_policy.project_resolution import ProjectSignals  # noqa: E402

CONDITION = sys.argv[1]
assert CONDITION in ("as_is", "envelope_in_system")
context.ENVELOPE_IN_SYSTEM = CONDITION == "envelope_in_system"
assert context.COMPACT_NOTES is False
import val_gateway.loop as loop  # noqa: E402

assert loop.TURN_KIND_FACT is False
ROOT = Path(__file__).resolve().parents[5]


def fresh_store() -> None:
    engine = create_engine(URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "packages/domain/migrations"))
    config.set_main_option("sqlalchemy.url", URL)
    command.upgrade(config, "head")


fresh_store()
engine = create_engine(URL)
seed(engine, ROOT)
gateway = start(engine).gateway
catalogue = load_catalogue(engine)
NO_PROJECT = ProjectSignals(explicit_no_project=True)
OFF = FastRoute()

stream = subprocess.Popen(["lms", "log", "stream", "--source", "model", "--json"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
captured: list[str] = []


def _drain() -> None:
    assert stream.stdout is not None
    for line in stream.stdout:
        captured.append(line)


threading.Thread(target=_drain, daemon=True).start()
time.sleep(1.5)
gateway.prime_prefix()

CASES = [
    ("wrong-turn d10", ["Val, explain three ways to make a film scene feel tense without using dialogue."], "Thank you, Val."),
    ("wrong-turn f08", ["Give me one line of advice on pacing a chase sequence."], "Much obliged."),
    ("wrong-turn f09", ["Explain the difference between suspense and surprise in a scene."], "Nothing else for now, thank you."),
    ("desktop-run: thanks after a misheard opener", ["Explain what a caesarean is."], "Thank you, Vowel."),
    ("desktop-run: farewell after a misheard greeting", ["Good evening, Vowel, it's me."], "Sleep well, Val. Good night."),
    ("explicit recap", ["Explain the difference between suspense and surprise in a scene."], "Recap that in one sentence."),
    ("explicit repeat", ["Give me one line of advice on pacing a chase sequence."], "Say that again, please."),
    ("pending: thanks after a draft request", ["Draft the reply to the reader."], "Thank you, Val."),
    ("pending: farewell after a cancel request", ["Cancel the meeting on Tuesday."], "Talk soon, Val."),
    ("pending: thanks after a decision question", ["Should I send the letter tonight or tomorrow?"], "Thank you."),
    ("farewell after greeting", ["Hello, Val."], "Just saying good night, Val."),
    ("thanks after greeting", ["Good evening, Val."], "Thank you, Val."),
    ("correction preserved", ["The venue is the hall.", "No, the chapel, not the hall."], "Thank you, Val."),
    ("withdrawal preserved", ["Draft the reply to the reader.", "Never mind the reply."], "Thank you."),
    ("fabricated completion", ["Good evening, Val. Did you finish the invitation?"], "Thank you, Val."),
    ("capability: speed", ["Good evening, Val."], "How fast are you, Val?"),
    ("capability: hearing", ["Good evening, Val."], "Can you hear me, Val?"),
    ("substantive", ["Good evening, Val."], "What do you think of the second act?"),
    ("substantive follow-up", ["Name two ways to end a chapter so the reader turns the page."], "Which of those works best in a night scene?"),
]
steps: list[dict] = []
rows: list[dict] = []
for label, history, utterance in CASES:
    conversation = None
    hist = []
    for line in history:
        got = send(engine, gateway, line, catalogue=catalogue, signals=NO_PROJECT if conversation is None else None,
                   conversation_id=conversation, spoken=True, seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=OFF,
                   on_delta=lambda _s: None)
        if not hasattr(got, "turn"):
            conversation = got.conversation.id  # type: ignore[attr-defined]
            hist.append({"said": line, "answer": f"UNANSWERED: {getattr(got, 'error', got)}"})
            continue
        conversation = got.turn.conversation.id
        hist.append({"said": line, "answer": got.turn.val_message.content})  # type: ignore[attr-defined]
        time.sleep(0.3)
    # As production's refresh does after every turn: both persona checkpoints re-established
    # before the measured call, so the measured call meets a warm store in both conditions
    # and the comparison reads the construction, not the store's ten-entry eviction.
    prime = gateway.prime_prefix()
    t = time.time()
    got = send(engine, gateway, utterance, catalogue=catalogue, conversation_id=conversation, spoken=True,
               seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=OFF, on_delta=lambda _s: None)
    steps.append({"label": label, "start": t, "end": time.time()})
    # An unanswered turn (the model returned no assistant content — an existing failure
    # mode, recorded as such) is a row too, never a crash of the comparison.
    user_message_id = got.user_message.id if hasattr(got, "user_message") else got.turn.user_message.id  # type: ignore[attr-defined]
    answer = got.turn.val_message.content if hasattr(got, "turn") else f"UNANSWERED: {getattr(got, 'error', got)}"  # type: ignore[attr-defined]
    with engine.connect() as c:
        call = c.execute(text(
            "select mc.tokens_in, mc.tokens_out, mc.latency_ms, x.first_text_ms, x.reasoning_output_tokens, x.text_output_chars "
            "from model_calls mc left join model_call_measurements x on x.model_call_id = mc.id "
            "where mc.message_id = :m order by mc.id desc limit 1"), {"m": user_message_id}).first() or (None,) * 6
    row = {"label": label, "history": hist, "utterance": utterance, "answer": answer,
           "prime_before": {k: (v.get("outcome") if isinstance(v, dict) else v) for k, v in dict(prime).items() if k in ("outcome", "light", "seconds")},
           "tokens_in": call[0], "tokens_out": call[1], "latency_ms": call[2], "first_text_ms": call[3],
           "reasoning_output_tokens": call[4], "text_output_chars": call[5]}
    rows.append(row)
    print(json.dumps({"label": label, "answer": row["answer"][:220], "tokens_in": row["tokens_in"], "first_text_ms": row["first_text_ms"],
                      "reasoning": row["reasoning_output_tokens"], "latency_ms": row["latency_ms"]}, ensure_ascii=False))
    time.sleep(0.3)
time.sleep(2.0)
stream.terminate()
try:
    stream.wait(timeout=10)
except subprocess.TimeoutExpired:
    stream.kill()
rendered_tail: str | None = None
rendered_last_user: str | None = None
inputs: list[tuple[float, str]] = []
for line in captured:
    try:
        e = json.loads(line)
    except ValueError:
        continue
    d = e.get("data", {})
    t = (e.get("timestamp") or 0) / 1000.0
    if d.get("type") == "llm.prediction.input":
        inputs.append((t, d.get("input", "")))
    elif d.get("type") == "llm.prediction.output":
        s = d.get("stats", {})
        m = next((x for x in steps if x["start"] - 0.5 <= t <= x["end"] + 0.5), None)
        if m and (s.get("promptTokensCount") or 0) > 1000:
            for r in rows:
                if r["label"] == m["label"] and "ttft_s" not in r:
                    r["ttft_s"] = s.get("timeToFirstTokenSec")
                    r["runtime_prompt_tokens"] = s.get("promptTokensCount")
                    break
# The rendered input of the "explicit recap" final call: where the envelope sits, and what the last user block holds.
recap = next((x for x in steps if x["label"] == "explicit recap"), None)
if recap:
    # The turn's own prompt is the longest rendering in the step's window (a prime's is shorter).
    candidates = [inp for t, inp in inputs if recap["start"] - 0.5 <= t <= recap["end"] + 0.5 and len(inp) > 5000]
    match = max(candidates, key=len) if candidates else None
    if match:
        rendered_tail = match[-2500:]
        last_user = match.rfind("<|start|>user<|message|>")
        rendered_last_user = match[last_user:last_user + 600] if last_user >= 0 else None
        positions = {
            "developer_block": match.find("<|start|>developer"),
            "system_block": match.find("<|start|>system"),
            "envelope_marker": match.find("VAL-STATE-V1"),
            "first_user_block": match.find("<|start|>user<|message|>"),
            "last_user_block": last_user,
            "length": len(match),
        }
        around_envelope = match[max(0, positions["envelope_marker"] - 300): positions["envelope_marker"] + 200] if positions["envelope_marker"] >= 0 else None
report = {"condition": CONDITION, "rows": rows, "rendered_input_tail": rendered_tail, "rendered_last_user_block": rendered_last_user,
          "rendered_positions": positions if match else None, "rendered_around_envelope": around_envelope if match else None}
Path(sys.argv[2]).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
print(CONDITION, "tokens_in median", statistics.median(r["tokens_in"] for r in rows),
      "first_text_ms median", statistics.median([r["first_text_ms"] or 0 for r in rows]),
      "ttft median", statistics.median([r.get("ttft_s") or 0 for r in rows]),
      "reasoning median", statistics.median([r["reasoning_output_tokens"] or 0 for r in rows]))
print("LAST USER BLOCK:", (rendered_last_user or "")[:400].replace("\n", "\\n"))
