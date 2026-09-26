"""LOW at the execution boundary — owner order "COMPARE EXISTING TIER-1 OPTIONS", §4.

Three questions, each answered by observation rather than by the client's label:

1. **Does the runtime receive LOW?** The adapter's own request for the promoted LOW
   entry is built and shown (`reasoning_effort`), and the same for the MEDIUM entry.
2. **Does LOW change the rendered model input, the cache identity, or both?** While one
   LOW Tier-1 call and one MEDIUM Tier-1 call go through the real Core path, LM Studio's
   own model-input log is captured (`lms log stream --source model`) and the two
   rendered prompts are compared: where they differ, and whether the persona prefix
   the prime establishes is the same bytes in both.
3. **Does a LOW call disturb the MEDIUM prefix cache?** Time to first provider event
   on a MEDIUM call over a fresh conversation (persona + envelope + one message, so the
   persona prefix is the only reusable part) measured (a) after a MEDIUM call and (b)
   after a LOW call, several trials each, interleaved. And LOW's own time to first
   event, which says whether LOW pays the persona prefill.

Production's model, quantization, context and serving configuration are untouched: the
LOW entry names the same loaded instance (`openai/gpt-oss-20b`) and the promotion is
in this process only. Scratch store `val_repro_test`. Local, $0.
Usage: low_boundary.py OUT.json [trials]
"""

from __future__ import annotations

import json
import os
import plistlib
import statistics
import subprocess
import sys
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        if name != "VAL_DATABASE_URL":
            os.environ[name] = value
URL = "postgresql+psycopg://localhost:5433/val_repro_test"
os.environ["VAL_DATABASE_URL"] = URL
os.environ["VAL_FAST_ROUTE_TIERS"] = "1"
os.environ["VAL_TIER1_ROUTE"] = "low"
for key in ("VAL_SPECULATION", "VAL_ADAPTIVE_GRACE"):
    os.environ.pop(key, None)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

import val_domain.registry as registry  # noqa: E402
from val_domain.gateway import Message, TaskType  # noqa: E402
from val_domain.project import ExplicitNoProject  # noqa: E402
from val_gateway.deliberate import send  # noqa: E402
from val_gateway.persona import seed  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.seal import SealRoute  # noqa: E402
from val_gateway.startup import start  # noqa: E402
from val_policy.light_conversation import FastRoute  # noqa: E402
from val_policy.project_resolution import ProjectSignals  # noqa: E402

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(sys.argv[1])
TRIALS = int(sys.argv[2]) if len(sys.argv) > 2 else 4


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
started = start(engine)
gateway = started.gateway
catalogue = load_catalogue(engine)
NO_PROJECT = ProjectSignals(explicit_no_project=True)
low = next(c for c in registry.REGISTRY if c.slug == "gpt-oss-20b-mxfp4-mlx-lmstudio-low")
medium = next(c for c in registry.REGISTRY if c.slug == "gpt-oss-20b-mxfp4-mlx-lmstudio-partner")
adapter = gateway._adapters["lmstudio"]  # noqa: SLF001 - inspection of the real adapter
report: dict[str, object] = {"trials": TRIALS}

# 1. The wire request, as the adapter builds it.
probe = (Message(role="user", content="Good evening, Val."),)
wire_low = adapter._request(low, probe, "PERSONA", 1024, None)  # noqa: SLF001
wire_medium = adapter._request(medium, probe, "PERSONA", 1024, None)  # noqa: SLF001
report["wire"] = {
    "low": {k: v for k, v in wire_low.items() if k != "messages"},
    "medium": {k: v for k, v in wire_medium.items() if k != "messages"},
}
print(json.dumps(report["wire"]))


# 2. The rendered model input, from the runtime's own log, for one LOW and one MEDIUM
#    Tier-1 call through Core.
def capture(seconds: float, action) -> list[dict]:  # noqa: ANN001
    proc = subprocess.Popen(
        ["lms", "log", "stream", "--source", "model", "--json"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    time.sleep(1.0)
    action()
    time.sleep(seconds)
    proc.terminate()
    out, _ = proc.communicate(timeout=10)
    entries = []
    for line in out.splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries


def tier1_turn(route_tiers: FastRoute):  # noqa: ANN201
    outcome = send(
        engine, gateway, "Good evening, Val.", catalogue=catalogue, signals=NO_PROJECT,
        spoken=True, seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=route_tiers,
    )
    return outcome


rendered: dict[str, list[dict]] = {}
rendered["low_tier1"] = capture(3.0, lambda: tier1_turn(FastRoute(frozenset({1}))))
rendered["medium_ordinary"] = capture(3.0, lambda: tier1_turn(FastRoute()))
report["rendered_log_entries"] = {k: len(v) for k, v in rendered.items()}
(OUT.with_name("low-boundary-rendered.json")).write_text(json.dumps(rendered, indent=1, ensure_ascii=False) + "\n")


# 3. Prefix-cache interference: time to first provider event on a MEDIUM call over a
#    fresh conversation, after MEDIUM and after LOW, interleaved.
def first_event_ms(fast: FastRoute, words: str) -> tuple[float, str]:
    first: list[float] = []
    started_at = time.monotonic()

    def on_delta(_: str) -> None:
        if not first:
            first.append(time.monotonic())

    outcome = send(
        engine, gateway, words, catalogue=catalogue, signals=NO_PROJECT, spoken=True,
        seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=fast, on_delta=on_delta,
    )
    slug = ""
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "select c.model_config_id::text, c.task_type::text, c.latency_ms from model_calls c "
                "where c.message_id = :m order by c.id desc limit 1"
            ),
            {"m": outcome.turn.user_message.id},  # type: ignore[attr-defined]
        ).first()
        if row is not None:
            slug = f"{row[1]}@{row[0][:8]} latency {row[2]} ms"
    elapsed = (first[0] - started_at) * 1000 if first else float("nan")
    return round(elapsed, 1), slug


SUBSTANTIVE = "Explain three ways to make a film scene feel tense without using dialogue."
# The voice path primes the spoken route (and the light route) when an utterance settles
# and after each turn; the trials do the same, so that what is measured is the primed
# state production would be in. The prime's own report says whether a LOW prime was
# established at all, and on what boundary.
primes = []
def prime() -> dict:
    result = dict(gateway.prime_prefix())
    primes.append(result)
    return result
report["prime"] = prime()
print("prime:", json.dumps({k: (v if not isinstance(v, dict) else {kk: v.get(kk) for kk in ("primed", "outcome", "slug", "boundary_tokens", "boundary_sha256", "prime_tokens", "seconds", "reason")}) for k, v in report["prime"].items()}, default=str))
sequences = {
    "medium_fresh_after_prime": [],           # warm baseline: MEDIUM over a fresh conversation
    "low_tier1_after_prime": [],              # does LOW reuse anything the prime left?
    "medium_fresh_after_low_no_reprime": [],  # did the LOW call disturb MEDIUM's checkpoint?
    "medium_tier1_after_prime": [],           # control: the same Tier-1 request at MEDIUM
    "medium_fresh_after_medium_tier1_no_reprime": [],
}
for trial in range(TRIALS):
    prime()
    sequences["medium_fresh_after_prime"].append(first_event_ms(FastRoute(), SUBSTANTIVE))
    prime()
    sequences["low_tier1_after_prime"].append(first_event_ms(FastRoute(frozenset({1})), "Good evening, Val."))
    sequences["medium_fresh_after_low_no_reprime"].append(first_event_ms(FastRoute(), SUBSTANTIVE))
    prime()
    # the control uses the MEDIUM Partner entry for the Tier-1 request: promote it beside LOW
    # is not possible in one process (one light configuration), so the ordinary route
    # carries the same words, which is what MEDIUM would do to a greeting today
    sequences["medium_tier1_after_prime"].append(first_event_ms(FastRoute(), "Good evening, Val."))
    sequences["medium_fresh_after_medium_tier1_no_reprime"].append(first_event_ms(FastRoute(), SUBSTANTIVE))
    print(json.dumps({"trial": trial, **{k: v[-1] for k, v in sequences.items()}}))
report["first_event_ms"] = {
    k: {"samples": v, "median": round(statistics.median(x[0] for x in v), 1)} for k, v in sequences.items()
}
report["primes"] = [{k: (v.get("outcome") if isinstance(v, dict) else v) for k, v in p.items() if k in ("outcome", "light", "boundary_tokens")} for p in primes]
OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
print(json.dumps(report["first_event_ms"], indent=1))
