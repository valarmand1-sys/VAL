"""One stage of the checkpoint-and-layout experiment — remaining latency work, 28 Sept 2026, §2-§3.

Stages (one frozen code, three switches of the experiment):

- `A`: the qualified candidate layout (`envelope_in_system`) with renewal, no divergence
  checkpoint — the established result;
- `B`: the same layout with the divergence checkpoint;
- `C`: the divergence checkpoint with the split layout (`split_state`).

A scripted conversation is sent live through the real Core path (`send`, spoken and
sealed, so every call is local and $0) against the EXPERIMENT instance only, with both
persona entries re-primed between turns as a Voice session does, and the real router
choosing LOW for his courtesies and MEDIUM for everything else. Part-way through, the
events the order names: a correction of an earlier message, a withdrawal, a switch to
another conversation and back, a turn that draws House recall, and a persona change.

For every model request it records the **rendered input** as the runtime reports it
(`lms log stream`), tokenized by the instance's own tokenizer; the engine's own line for
that request ("Prompt cache: using N/M"), attributed by instance and prompt length; the
hook's own decision line (boundary, store size, active memory); time to first token.
**Validity:** a request may reuse at most the longest prefix it shares with an earlier
request's rendered input — every stored key is a prefix of one — so N above that bound
would be a cache serving content Core did not send. The bound is checked on every
request, and the reuse reached is reported.

Also records each call's exact request body (the adapter's own `_request` result) for the
cached-versus-uncached comparison (`cached_vs_uncached.py`).

Usage: checkpoint_stage.py A|B|C OUT.json
"""

from __future__ import annotations

import glob
import json
import os
import plistlib
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

STAGE = sys.argv[1]
OUT = Path(sys.argv[2])
LAYOUT = {"A": "envelope_in_system", "B": "envelope_in_system", "C": "split_state"}[STAGE]
DIVERGENCE = STAGE in ("B", "C")
EXPERIMENT = "val-exp-gpt-oss-20b"
LMS = str(Path.home() / ".lmstudio/bin/lms")
CLONE = str(Path.home() / ".lmstudio/models/val-experiment/gpt-oss-20b-MXFP4-Q8-renewal")
ALLOWLIST = Path.home() / ".lmstudio/val-cache-renewal.json"
HOOK_LOG = Path.home() / ".lmstudio/val-cache-renewal.log"

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        if name != "VAL_DATABASE_URL":
            os.environ[name] = value
URL = "postgresql+psycopg://localhost:5433/val_ckpt_test"
os.environ["VAL_DATABASE_URL"] = URL
os.environ["VAL_FAST_ROUTE_TIERS"] = "1"
os.environ["VAL_TIER1_ROUTE"] = "low"
os.environ["VAL_REQUEST_CONSTRUCTION"] = LAYOUT
for key in ("VAL_SPECULATION", "VAL_ADAPTIVE_GRACE", "VAL_OWNER_PRECEDENCE", "VAL_ADAPTIVE_ENDPOINT"):
    os.environ.pop(key, None)

ALLOWLIST.write_text(
    json.dumps({"model_paths": [CLONE], "renewal": True, "divergence_checkpoint": DIVERGENCE}, indent=2)
    + "\n"
)
# The same empty cache for every stage.
subprocess.run([LMS, "unload", EXPERIMENT], capture_output=True)
subprocess.run(
    [LMS, "load", "gpt-oss-20b-renewal", "--identifier", EXPERIMENT, "-c", "32768", "--parallel", "1", "-y"],
    capture_output=True,
    check=True,
)
hook_log_start = HOOK_LOG.stat().st_size if HOOK_LOG.exists() else 0

import lmstudio  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

import val_domain.registry as registry  # noqa: E402
import val_providers.lmstudio_adapter as lmstudio_adapter  # noqa: E402
from val_domain.persona import PersonaSource, digest_of, read_source  # noqa: E402
from val_gateway import conversations  # noqa: E402
from val_gateway.deliberate import send  # noqa: E402
from val_gateway.persona import create_revision, seed  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.revisions import retract, revise  # noqa: E402
from val_gateway.seal import SealRoute  # noqa: E402
from val_gateway.startup import start  # noqa: E402
from val_policy.project_resolution import ExplicitNoProject  # noqa: E402

registry.REGISTRY = tuple(
    c.model_copy(update={"model_identifier": EXPERIMENT}) if c.model_identifier == "openai/gpt-oss-20b" else c
    for c in registry.REGISTRY
)
ROOT = Path(__file__).resolve().parents[5]

subprocess.run(["dropdb", "-h", "localhost", "-p", "5433", "--if-exists", "val_ckpt_test"], check=True)
subprocess.run(["createdb", "-h", "localhost", "-p", "5433", "val_ckpt_test"], check=True)
config = Config(str(ROOT / "alembic.ini"))
config.set_main_option("script_location", str(ROOT / "packages/domain/migrations"))
config.set_main_option("sqlalchemy.url", URL)
command.upgrade(config, "head")
engine = create_engine(URL)
seed(engine, ROOT)
started = start(engine)
gateway = started.gateway
catalogue = load_catalogue(engine)

bodies: list[dict] = []
_original_request = lmstudio_adapter.LMStudioAdapter._request


def _capturing(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
    body = _original_request(self, *args, **kwargs)
    bodies.append({"at": time.time(), "body": json.loads(json.dumps(body, default=str))})
    return body


lmstudio_adapter.LMStudioAdapter._request = _capturing  # type: ignore[method-assign]

stream = subprocess.Popen([LMS, "log", "stream", "--source", "model", "--json"],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
captured: list[tuple[float, dict]] = []


def _drain() -> None:
    assert stream.stdout is not None
    for line in stream.stdout:
        try:
            captured.append((time.time(), json.loads(line)))
        except ValueError:
            pass


threading.Thread(target=_drain, daemon=True).start()
time.sleep(1.5)
model = lmstudio.Client("127.0.0.1:1234", api_token=os.environ["VAL_LMSTUDIO_API_TOKEN"]).llm.model(EXPERIMENT)

events: list[dict] = []


def mark(kind: str, **detail: object) -> None:
    events.append({"at": time.time(), "kind": kind, **detail})


def turn(conversation: object, words: str) -> None:
    gateway.prime_prefix()  # both persona entries, as a Voice session refreshes them
    began = time.time()
    got = send(engine, gateway, words, catalogue=catalogue, conversation_id=conversation, spoken=True,
               seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=started.fast_route,
               on_delta=lambda _s: None)
    answered = hasattr(got, "turn")
    mark("turn", words=words, began=began, ended=time.time(),
         answer=(got.turn.val_message.content[:200] if answered else None),  # type: ignore[attr-defined]
         user_message=str(got.turn.user_message.id if answered else got.user_message.id))  # type: ignore[attr-defined]


def message_id(words: str) -> object:
    with engine.connect() as c:
        return c.execute(text("select m.id from messages m join messages_current mc on mc.id = m.id "
                              "where m.role = 'user' and mc.content = :w order by m.sequence limit 1"),
                         {"w": words}).scalar_one()


first = conversations.create(engine, scope=ExplicitNoProject(), title="checkpoint stage").id
second = conversations.create(engine, scope=ExplicitNoProject(), title="another conversation").id
for words in ("Good evening, Val.",
              "Name two ways to end a chapter so the reader turns the page.",
              "Which of those works best in a night scene?",
              "Give me one line of advice on pacing a chase sequence.",
              "Thank you.",
              "Explain the difference between suspense and surprise in a scene."):
    turn(first, words)
revise(engine, message_id("Give me one line of advice on pacing a chase sequence."),
       "Give me one line of advice on pacing a film scene.")
mark("event", what="correction of an earlier message")
turn(first, "Which of those works better in a short story?")
retract(engine, message_id("Name two ways to end a chapter so the reader turns the page."))
mark("event", what="withdrawal of an earlier message")
turn(first, "What is a caesura?")
mark("event", what="conversation switch")
turn(second, "Tell me about a good opening line.")
mark("event", what="conversation switch back")
turn(first, "How long should a first chapter be?")
turn(first, "What did we say in our other conversation about opening lines?")
mark("event", what="a turn that draws House recall (above)")
turn(first, "Name a famous ghost story.")
source = read_source(ROOT)
changed = source.content + "\n"
create_revision(engine, PersonaSource(content=changed, sha256=digest_of(changed),
                                      semantic_version=source.semantic_version, path=source.path),
                activate=True, authored_by="checkpoint stage (scratch store only)")
mark("event", what="persona change (a new revision activated in the scratch store)")
turn(first, "Which of those is best known?")
time.sleep(1.5)
stream.terminate()

# --- per request: rendered input, tokens, the engine's line, the hook's line -------------
inputs = [(t, e["data"]) for t, e in captured if e.get("data", {}).get("type") == "llm.prediction.input"]
outputs = [(t, e["data"]) for t, e in captured if e.get("data", {}).get("type") == "llm.prediction.output"]
engine_lines: list[tuple[float, int, int, str | None]] = []
for path in sorted(glob.glob(str(Path.home() / ".lmstudio/server-logs/2026-09/2026-09-2*.log")))[-1:]:
    lines = open(path, errors="replace").read().splitlines()
    for index, line in enumerate(lines):
        hit = re.search(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\].*Prompt cache: using (\d+)/(\d+) tokens", line)
        if hit:
            at = time.mktime(time.strptime(hit.group(1), "%Y-%m-%d %H:%M:%S"))
            named = next((re.search(r"\]\[INFO\]\[([^\]]+)\] Prompt processing", f) for f in lines[index + 1:index + 6]
                          if re.search(r"\]\[INFO\]\[([^\]]+)\] Prompt processing", f)), None)
            engine_lines.append((at, int(hit.group(2)), int(hit.group(3)), named.group(1) if named else None))
hook_lines = [
    json.loads(line.split(" request ", 1)[1])
    | {"at": time.mktime(time.strptime(line[:19], "%Y-%m-%dT%H:%M:%S"))}
    for line in HOOK_LOG.read_text()[hook_log_start:].splitlines()
    if " request " in line
]

requests: list[dict] = []
previous_tokens: list[list[int]] = []
for index, (at, data) in enumerate(inputs):
    ids = [int(t) for t in model.tokenize(data.get("input", ""))]
    bound = max((next((i for i, (x, y) in enumerate(zip(p, ids)) if x != y), min(len(p), len(ids)))
                 for p in previous_tokens), default=0)
    line = next((e for e in engine_lines if e[3] == EXPERIMENT and e[2] == len(ids) and abs(e[0] - at) <= 3), None)
    stats = next((d.get("stats", {}) for t, d in outputs if t >= at), {})
    hook = next(
        (h for h in hook_lines if h.get("total") == len(ids) and abs(h["at"] - at) <= 4), None
    )
    requests.append({
        "at": at, "tokens": len(ids), "cached": None if line is None else line[1],
        "reuse_bound": bound, "valid": None if line is None else line[1] <= bound,
        "uncached": None if line is None else len(ids) - line[1],
        "ttft_s": stats.get("timeToFirstTokenSec"),
        "boundary": None if hook is None else hook.get("boundary"),
        "why": None if hook is None else hook.get("why"),
        "update_cache_ms": None if hook is None else hook.get("update_cache_ms"),
        "entries": None if hook is None else hook.get("entries"),
        "store_bytes": None if hook is None else hook.get("store_bytes"),
        "active_memory": None if hook is None else hook.get("active_memory"),
    })
    previous_tokens.append(ids)
for request in requests:
    turn_event = next(
        (e for e in events if e["kind"] == "turn" and e["began"] <= request["at"] <= e["ended"] + 0.5),
        None,
    )
    request["turn"] = None if turn_event is None else turn_event["words"]

OUT.write_text(json.dumps({"stage": STAGE, "layout": LAYOUT, "divergence": DIVERGENCE, "events": events,
                           "requests": requests, "bodies": bodies}, indent=1, ensure_ascii=False) + "\n")
turns = [r for r in requests if r["tokens"] > 5200]
print(f"stage {STAGE} ({LAYOUT}, divergence {'on' if DIVERGENCE else 'off'}): requests {len(requests)}, "
      f"invalid {sum(1 for r in requests if r['valid'] is False)}, unattributed {sum(1 for r in requests if r['cached'] is None)}")
for r in turns:
    print(f"  {str(r['turn'])[:44]:44s} tokens {r['tokens']:5d} cached {r['cached']} bound {r['reuse_bound']} "
          f"ttft {r['ttft_s']} boundary {r['boundary']} mem {r['active_memory']}")
