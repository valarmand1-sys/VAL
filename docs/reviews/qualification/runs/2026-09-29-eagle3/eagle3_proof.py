"""One small proof: GPT-OSS-20B MEDIUM on llama.cpp (Metal), EAGLE3 off against on.

Owner order of 29 September 2026 ("resolve one specific supported same-model acceleration
opportunity"); registered in EAGLE3_PROOF.md before any measured request. One invocation
is one block: it starts its own `llama-server` on the loopback interface (the installed
official build), runs its cases through Val Core, and stops the server.

- Target: `gpt-oss-20b-MXFP4.gguf`; draft (on only): `eagle3-gpt-oss-20b-BF16.gguf`; both
  from `ggml-org/gpt-oss-20b-GGUF` @ `ef9b12f2…`, digests checked before the server starts.
- The same flags in both conditions except the draft: window 32,768, one slot, `--swa-full`,
  MEDIUM through the chat template. The draft's own settings are the runtime's defaults.
- Through Val Core: production's request construction (no `envelope_in_system`), the
  persona whole, spoken sealed conversations in a scratch store. The house's llama.cpp
  adapter carries the request; for this proof only, the harness adds what that adapter
  does not yet transmit (the graded effort, min-p and the repeat penalty), in the one
  function that builds the body the preflight counts and the call sends.
- Before every measured request the static prefix is prepared the same way in both
  conditions: one request of the persona and a short filler, one token generated.

Measured per request: dispatch to first streamed chunk, to first visible answer text and
to the first complete speech-safe segment (the delivery's own segmenter); the runtime's
reasoning-token count; the server's own timing lines for that request (prompt tokens
evaluated and reused, generation rate, draft acceptance); stream integrity (the streamed
text against the settled answer). Per block: the server's memory footprint and swap.
Block B ends with one cancellation check. Local, $0.

Usage: eagle3_proof.py off|on A|B OUT.json
"""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
import secrets
import statistics
import subprocess
import sys
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        if name != "VAL_DATABASE_URL":
            os.environ[name] = value
URL = "postgresql+psycopg://localhost:5433/val_eagle_test"
os.environ["VAL_DATABASE_URL"] = URL
for key in ("VAL_FAST_ROUTE_TIERS", "VAL_TIER1_ROUTE", "VAL_SPECULATION", "VAL_ADAPTIVE_GRACE",
            "VAL_OWNER_PRECEDENCE", "VAL_REQUEST_CONSTRUCTION", "VAL_COMBINE_CONTINUATIONS",
            "VAL_ORDINARY_LOW", "VAL_ADAPTIVE_ENDPOINT", "VAL_TTS_LENGTH_BOUND", "VAL_EXPERIMENT_COGNITION"):
    os.environ.pop(key, None)
PORT = 8099
KEY = secrets.token_hex(24)  # a throwaway key for this block's server; never printed or stored
os.environ["VAL_LLAMACPP_API_KEY"] = KEY
os.environ["VAL_LLAMACPP_BASE_URL"] = f"http://127.0.0.1:{PORT}/v1"

import httpx  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

import val_domain.registry as registry  # noqa: E402
import val_providers.llamacpp_adapter as llamacpp  # noqa: E402
from val_domain import timings  # noqa: E402
from val_domain.conversation import StoredRole  # noqa: E402
from val_domain.gateway import Admission, CapabilityProfile, ReasoningEffort  # noqa: E402
from val_gateway import conversations  # noqa: E402
from val_gateway.context import STATE_ENVELOPE_MARKER  # noqa: E402
from val_gateway.deliberate import send  # noqa: E402
from val_gateway.persona import seed  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.seal import SealRoute  # noqa: E402
from val_gateway.startup import start  # noqa: E402
from val_policy.light_conversation import FastRoute  # noqa: E402
from val_policy.project_resolution import ExplicitNoProject  # noqa: E402
from val_policy.speech_segments import SpeechSegmenter  # noqa: E402

CONDITION, BLOCK, OUT = sys.argv[1], sys.argv[2], Path(sys.argv[3])
assert CONDITION in ("off", "on") and BLOCK in ("A", "B")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
MODELS = Path.home() / ".val-models/llamacpp-exp"
TARGET, DRAFT = MODELS / "gpt-oss-20b-MXFP4.gguf", MODELS / "eagle3-gpt-oss-20b-BF16.gguf"
PINS = json.loads((MODELS / "pins.json").read_text())
SERVER = "/opt/homebrew/bin/llama-server"
ALIAS = "val-exp-gpt-oss-llamacpp"
SCRATCH = Path(os.environ.get("VAL_EAGLE_SCRATCH", "/private/tmp"))
LOG = SCRATCH / f"llama-server-{CONDITION}-{BLOCK}.log"
SAMPLING = {"min_p": 0.05, "repeat_penalty": 1.1}

downloaded = dict(line.split()[::-1] for line in (MODELS / "downloaded.sha256").read_text().splitlines())
for path in (TARGET, DRAFT):
    assert downloaded[path.name] == PINS["files"][path.name]["sha256"], f"{path.name} does not match its pin"

# The body the preflight counts is the body sent: the three fields are added in that one place.
_wire_body = llamacpp.wire_body


def wire_body(config, messages, system, max_output_tokens):  # noqa: ANN001, ANN201
    body = _wire_body(config, messages, system, max_output_tokens)
    body.update(SAMPLING)
    body["chat_template_kwargs"] = {**body.get("chat_template_kwargs", {}), "reasoning_effort": "medium"}
    return body


llamacpp.wire_body = wire_body  # type: ignore[assignment]

PARTNER = "gpt-oss-20b-mxfp4-mlx-lmstudio-partner"
partner = registry.by_slug(PARTNER)
assert partner is not None
candidate = partner.model_copy(update={
    "id": __import__("uuid").uuid5(partner.id, "eagle3-proof-2026-09-29"),
    "slug": "gpt-oss-20b-mxfp4-gguf-llamacpp-experiment",
    "provider": "llamacpp", "model_identifier": ALIAS,
    "display_name": "GPT-OSS 20B (MXFP4 GGUF, llama.cpp — EAGLE3 proof, this process only)",
    # MEDIUM is applied in the request body and the server's template default; the house
    # adapter refuses a declared graded effort, so none is declared on this copy.
    "reasoning_effort": ReasoningEffort.NOT_APPLICABLE,
    "temperature": 0.8, "top_p": 0.8, "top_k": 40,
    "admission": Admission.PROVISIONALLY_ADMITTED,
})
registry.REGISTRY = tuple(
    c.model_copy(update={"capability_profiles": c.capability_profiles - {CapabilityProfile.PARTNER}})
    if c.slug == PARTNER else c for c in registry.REGISTRY
) + (candidate,)


def swap_mb() -> float:
    out = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True).stdout
    return float(re.search(r"used = ([\d.]+)M", out).group(1))  # type: ignore[union-attr]


def footprint_gb(pid: int) -> float | None:
    out = subprocess.run(["footprint", "-p", str(pid)], capture_output=True, text=True).stdout
    found = re.search(r"Footprint:\s*([\d.]+)\s*(GB|MB)", out)
    return None if not found else round(float(found.group(1)) / (1 if found.group(2) == "GB" else 1024), 2)


keyfile = SCRATCH / f"llama-key-{os.getpid()}"
keyfile.write_text(KEY)
keyfile.chmod(0o600)
flags = [SERVER, "-m", str(TARGET), "--alias", ALIAS, "--ctx-size", "32768", "--parallel", "1", "--jinja",
         "-ngl", "999", "--host", "127.0.0.1", "--port", str(PORT), "--api-key-file", str(keyfile),
         "--swa-full", "-b", "2048", "-ub", "2048", "--no-webui",
         "--chat-template-kwargs", '{"reasoning_effort":"medium"}']
if CONDITION == "on":
    flags += ["-md", str(DRAFT), "--spec-type", "draft-eagle3", "-ngld", "999"]
swap_start = swap_mb()
loaded_at = time.monotonic()
server = subprocess.Popen(flags, stdout=open(LOG, "w"), stderr=subprocess.STDOUT)
HEADERS = {"Authorization": f"Bearer {KEY}"}


def stop(code: int, why: str) -> None:
    server.terminate()
    keyfile.unlink(missing_ok=True)
    print("STOPPED:", why)
    OUT.write_text(json.dumps({"condition": CONDITION, "block": BLOCK, "stopped": why, "rows": ROWS,
                               "server_log_tail": log_lines(0)[-40:]}, indent=1, default=str) + "\n")
    sys.exit(code)


def log_lines(start: int) -> list[str]:
    return LOG.read_text(errors="replace").splitlines()[start:]


ROWS: list[dict] = []
for _ in range(600):
    if server.poll() is not None:
        stop(2, "the server exited while loading")
    try:
        if httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=2).status_code == 200:
            break
    except httpx.HTTPError:
        pass
    time.sleep(0.5)
else:
    stop(2, "the server did not become ready in 300 s")
load_seconds = round(time.monotonic() - loaded_at, 1)
props = httpx.get(f"http://127.0.0.1:{PORT}/props", headers=HEADERS, timeout=10).json()
startup_log = [line for line in log_lines(0) if re.search(r"eagle|specul|draft|swa|metal|offload|n_ctx|build|checkpoint", line, re.I)]


def fresh_store() -> None:
    admin = create_engine(URL.replace("/val_eagle_test", "/postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        if not connection.execute(text("select 1 from pg_database where datname = 'val_eagle_test'")).first():
            connection.execute(text("create database val_eagle_test"))
    admin.dispose()
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
OFF_ROUTE = FastRoute()
with engine.connect() as _c:
    PERSONA = _c.execute(text("select content from personas where is_active order by activated_at desc limit 1")).scalar_one()

STAGE_A = {t["id"]: t for t in json.loads((HERE.parent / "2026-09-16-gpt-oss-stage-a/benchmark.json").read_text())["tasks"]}
F1_T1_ANSWER = next(t for t in json.loads(
    (HERE.parent / "2026-09-23-gpt-oss-effort-paired/results-medium.json").read_text())["tasks"]
    if t["id"] == "F1")["turns"][0]["visible_answer"]
GREETING = [("Good evening, Val.", "Good evening, my lord.")]
TENSE = ("Three, my lord. Withhold the wide shot, so the audience never knows what stands outside the frame. "
         "Let a sound continue past the point where it should have stopped. And hold on a face that has decided "
         "something before the others in the room have noticed.")
CASES = {
    "A": [
        ("O1-substantive", GREETING, "Explain the difference between suspense and surprise in a scene."),
        ("O2-follow-up", [("Explain three ways to make a film scene feel tense without using dialogue.", TENSE)],
         "Which of those would work best in a night scene, and why?"),
        ("C6-nonexistent-work", [], STAGE_A["E1"]["turns"][0]),
        ("C1-correction", [(STAGE_A["F1"]["turns"][0], F1_T1_ANSWER)], STAGE_A["F1"]["turns"][1]),
    ],
    "B": [
        ("O3-creative", GREETING, "Explain three ways to make a film scene feel tense without using dialogue."),
        ("C5-missing-information", GREETING, "What do you think of the second act?"),
        ("C2-withdrawn-fact", [("The read-through is on Thursday.", "Thursday, my lord; noted."),
                               ("Scratch that — I haven't fixed a day for it yet.", "Understood, my lord: no day is set.")],
         "When is the read-through?"),
    ],
}[BLOCK]


def direct(messages: list[dict], max_tokens: int, stream: bool = False) -> dict:
    body = {"model": ALIAS, "messages": messages, "max_tokens": max_tokens, "temperature": 0.8, "top_p": 0.8,
            "top_k": 40, **SAMPLING, "chat_template_kwargs": {"reasoning_effort": "medium"}, "stream": stream}
    began = time.monotonic()
    if not stream:
        reply = httpx.post(f"http://127.0.0.1:{PORT}/v1/chat/completions", headers=HEADERS, json=body, timeout=600).json()
        return {"seconds": round(time.monotonic() - began, 3), "timings": reply.get("timings"), "usage": reply.get("usage")}
    seen = {"reasoning": False, "content": ""}
    with httpx.Client(timeout=600) as client, client.stream(
            "POST", f"http://127.0.0.1:{PORT}/v1/chat/completions", headers=HEADERS, json=body) as response:
        for line in response.iter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            for choice in json.loads(line[6:]).get("choices", []):
                delta = choice.get("delta") or {}
                seen["reasoning"] = seen["reasoning"] or bool(delta.get("reasoning_content"))
                seen["content"] += delta.get("content") or ""
            if len(seen["content"]) > 40:
                break  # the stream is closed here, mid-answer
    return {"closed_after_s": round(time.monotonic() - began, 3), "content_chars_before_close": len(seen["content"])}


def prime() -> dict:
    """The static prefix, prepared identically in both conditions: persona, a filler, one token."""
    return direct([{"role": "system", "content": PERSONA}, {"role": "user", "content": "ok"}], 1)


def prepare(label: str, history: list[tuple[str, str]]) -> object:
    conversation = conversations.create(engine, scope=ExplicitNoProject(), title=label[:60])
    for said, reply in history:
        conversations.append(engine, conversation.id, role=StoredRole.USER, content=said)
        conversations.append(engine, conversation.id, role=StoredRole.VAL, content=reply)
    return conversation.id


INTERESTING = re.compile(r"prompt eval time|eval time|total time|draft|accept|cache|sim_best|checkpoint|n_past|truncat|error|fail", re.I)
for label, history, words in CASES:
    if server.poll() is not None:
        stop(3, f"the server exited before {label}")
    conversation = prepare(f"{label} [{CONDITION}]", history)
    primed = prime()
    log_from = len(log_lines(0))
    deltas: list[tuple[float, str]] = []
    with timings.recording() as recorder:
        got = send(engine, gateway, words, catalogue=catalogue, conversation_id=conversation, spoken=True,
                   seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=OFF_ROUTE,
                   on_delta=lambda piece, sink=deltas: sink.append((time.monotonic(), piece)))
    marks: dict[str, float] = {}
    for name, at in recorder.marks:
        marks.setdefault(name, at - recorder.started_at)
    segmenter, first_segment = SpeechSegmenter(), None
    for at, piece in deltas:
        if segmenter.feed(piece) and first_segment is None:
            first_segment = at - recorder.started_at
    answered = hasattr(got, "turn")
    answer = got.turn.val_message.content if answered else None  # type: ignore[attr-defined]
    user_id = got.turn.user_message.id if answered else got.user_message.id  # type: ignore[attr-defined]
    with engine.connect() as c:
        call = c.execute(text(
            "select mc.tokens_in, mc.tokens_out, x.reasoning_output_tokens, mc.model_config_id, x.reasoning_present "
            "from model_calls mc left join model_call_measurements x on x.model_call_id = mc.id where mc.message_id = :m "
            "and mc.task_type::text = 'conversation' order by mc.created_at desc limit 1"), {"m": user_id}).first() \
            or (None,) * 5
    dispatch = marks.get("provider_dispatch")

    def since(name: str, marks: dict[str, float] = marks, dispatch: float | None = dispatch) -> float | None:
        at = marks.get(name)
        return None if at is None or dispatch is None else round(at - dispatch, 3)

    time.sleep(0.5)
    streamed = "".join(piece for _, piece in deltas)
    row = {
        "case": label, "condition": CONDITION, "block": BLOCK, "answered": answered, "answer": answer,
        "unanswered": None if answered else str(getattr(got, "reason", got))[:400],
        "routed_to_candidate": call[3] == candidate.id,
        "tokens_in": call[0], "tokens_out": call[1], "reasoning_tokens": call[2], "reasoning_present": call[4],
        "dispatch_to_first_chunk_s": since("provider_chunk"),
        "dispatch_to_first_visible_s": since("provider_visible_text"),
        "dispatch_to_first_segment_s": None if first_segment is None or dispatch is None else round(first_segment - dispatch, 3),
        "stream_matches_answer": answered and streamed.strip() == (answer or "").strip(),
        "reasoning_in_answer": bool(re.search(r"<\|channel\|>|<\|start\|>|<\|message\|>|\banalysis\b.*\bfinal\b", answer or "")),
        "prime": primed,
        "server_lines": [line[-220:] for line in log_lines(log_from) if INTERESTING.search(line)],
        "server_footprint_gb": footprint_gb(server.pid),
    }
    fc, fv = row["dispatch_to_first_chunk_s"], row["dispatch_to_first_visible_s"]
    row["reasoning_s"] = None if fc is None or fv is None else round(fv - fc, 3)
    ROWS.append(row)
    print(json.dumps({k: v for k, v in row.items() if k not in ("answer", "server_lines", "prime")}), flush=True)
    print("   prime:", json.dumps(primed)[:300], flush=True)
    for line in row["server_lines"][-8:]:
        print("   |", line, flush=True)
    if not answered:
        stop(4, f"{label} was not answered: {row['unanswered']}")
    if row["reasoning_in_answer"] or not row["stream_matches_answer"]:
        stop(5, f"{label}: the stream or the answer is not intact")

cancellation = None
if BLOCK == "B":
    prime()
    closed = direct([{"role": "system", "content": PERSONA},
                     {"role": "user", "content": "Explain the difference between suspense and surprise in a scene."}],
                    2048, stream=True)
    after = prime()
    cancellation = {"closed": closed, "next_request_seconds": after["seconds"], "next_request_timings": after["timings"]}
    print("cancellation:", json.dumps(cancellation), flush=True)

result = {
    "condition": CONDITION, "block": BLOCK, "load_seconds": load_seconds,
    "server": {"binary": SERVER, "flags": [f for f in flags if f != str(keyfile)],
               "build": props.get("build_info"), "n_ctx": (props.get("default_generation_settings") or {}).get("n_ctx"),
               "chat_template_sha256": hashlib.sha256((props.get("chat_template") or "").encode()).hexdigest(),
               "default_generation_settings": {k: v for k, v in ((props.get("default_generation_settings") or {}).get("params") or {}).items()
                                               if k in ("temperature", "top_k", "top_p", "min_p", "repeat_penalty", "repeat_last_n", "samplers")},
               "startup_log": [line[-200:] for line in startup_log][:60]},
    "artifacts": {p.name: PINS["files"][p.name] for p in ((TARGET, DRAFT) if CONDITION == "on" else (TARGET,))},
    "envelope_marker": STATE_ENVELOPE_MARKER,
    "medians": {k: (round(statistics.median([r[k] for r in ROWS if r.get(k) is not None]), 3)
                    if any(r.get(k) is not None for r in ROWS) else None)
                for k in ("dispatch_to_first_chunk_s", "reasoning_s", "reasoning_tokens",
                          "dispatch_to_first_visible_s", "dispatch_to_first_segment_s")},
    "server_footprint_gb_peak": max((r["server_footprint_gb"] or 0) for r in ROWS) if ROWS else None,
    "swap_mb": {"start": swap_start, "end": swap_mb()},
    "cancellation": cancellation,
    "rows": ROWS,
}
server.terminate()
keyfile.unlink(missing_ok=True)
OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str) + "\n")
print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "server")}, indent=1, default=str))
