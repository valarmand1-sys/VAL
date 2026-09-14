"""Stage A1 — GPT-5.6 Sol adapter preflight (owner-authorised 14 September 2026, max $0.05).

Exactly the three calls of `VAL_OpenAI_Sol_Measurement_Protocol.md` §4, on the
scratch store only, with no House material. Adapter/integration preflight: not
qualification, not admission, not the two-provider gate. Writes OUT.json.
"""

import json
import os
import plistlib
import sys
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    env = plistlib.load(f)["EnvironmentVariables"]
for k in ("VAL_ANTHROPIC_API_KEY", "VAL_OPENAI_API_KEY"):
    os.environ[k] = env[k]

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

ROOT = Path("/Users/josepharmand/Projects/val")
URL = "postgresql+psycopg://localhost:5433/val_test"
assert URL.rsplit("/", 1)[-1].endswith("_test")
engine = create_engine(URL)
with engine.begin() as c:
    c.execute(text("DROP SCHEMA public CASCADE"))
    c.execute(text("CREATE SCHEMA public"))
cfg = Config(str(ROOT / "alembic.ini"))
cfg.set_main_option("script_location", str(ROOT / "packages/domain/migrations"))
cfg.set_main_option("sqlalchemy.url", URL)
command.upgrade(cfg, "head")
engine.dispose()
engine = create_engine(URL)

from val_domain.gateway import Classification, GatewayError, GatewayRequest, Message, TaskType
from val_domain.project import ProjectAttribution
from val_domain.provider import ProviderResult, TextDelta
from val_domain.registry import by_slug
from val_gateway.persona import seed
from val_gateway.startup import start

seed(engine, ROOT)
gateway = start(engine).gateway
adapter = gateway._adapters["openai"]  # the actual adapter the service uses
sol = by_slug("gpt-5-6-sol-medium")
assert sol is not None
PROMPT = "Reply with the single word: ready."
CAP = 0.05
out: dict[str, object] = {"configuration": sol.slug, "model": sol.model_identifier, "calls": []}


def usage(r: ProviderResult) -> dict[str, object]:
    return {
        "terminal": r.terminal.value,
        "stop_reason": r.stop_reason,
        "stop_details": r.stop_details,
        "tokens_in_uncached": r.tokens_in,
        "cache_read": r.cache_read_tokens,
        "cache_write_reported": r.reported_cache_write_tokens,
        "tokens_out": r.tokens_out,
        "reasoning_tokens": r.reasoning_tokens,
        "reasoning_present": r.reasoning_present,
        "provider_request_id": r.provider_request_id,
        "text": r.text,
    }


def spent() -> float:
    with engine.connect() as c:
        return float(c.execute(text("select coalesce(sum(cost),0) from model_calls")).scalar_one())


# Call 1: the adapter's stream, directly.
t0 = time.monotonic()
deltas: list[str] = []
final: ProviderResult | None = None
first_ms = None
try:
    for event in adapter.stream(sol, (Message(role="user", content=PROMPT),), None, 1024):
        if isinstance(event, TextDelta):
            if first_ms is None:
                first_ms = int((time.monotonic() - t0) * 1000)
            deltas.append(event.text)
        elif isinstance(event, ProviderResult):
            final = event
    assert final is not None
    cost1 = round(
        (final.tokens_in or 0) * sol.cost_per_mtok_in_usd / 1e6
        + (final.cache_read_tokens or 0) * sol.cost_per_mtok_in_usd / 1e6
        + (final.tokens_out or 0) * sol.cost_per_mtok_out_usd / 1e6,
        6,
    )
    out["calls"].append(
        {
            "call": 1,
            "path": "OpenAIAdapter.stream",
            "deltas": deltas,
            "first_text_ms": first_ms,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "event_types": ["TextDelta"] * len(deltas) + ["ProviderResult"],
            "usage": usage(final),
            "cost_at_registry_rates": cost1,
        }
    )
except GatewayError as e:
    out["calls"].append({"call": 1, "path": "OpenAIAdapter.stream", "error": str(e)})
    cost1 = 0.0
    print(json.dumps(out, indent=1))
    sys.exit("call 1 failed; stopping")


def door(number: int, max_output: int) -> None:
    request = GatewayRequest(
        task_type=TaskType.TITLE,
        classification=Classification.INTERNAL,
        messages=(Message(role="user", content=PROMPT),),
        max_output_tokens=max_output,
        output_schema={
            "type": "object",
            "properties": {"word": {"type": "string"}},
            "required": ["word"],
            "additionalProperties": False,
        },
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
    )
    t = time.monotonic()
    try:
        response = gateway.evaluate_with_configuration(request, sol)
        record: dict[str, object] = {
            "call": number,
            "path": "Gateway.evaluate_with_configuration",
            "max_output_tokens": max_output,
            "terminal": response.terminal.value,
            "stop_reason": response.stop_reason,
            "stop_details": response.stop_details,
            "text": response.text,
            "tokens_in_total": response.tokens_in,
            "tokens_out": response.tokens_out,
            "cost_usd": response.cost_usd,
            "latency_ms": response.latency_ms,
            "model_call_id": str(response.model_call_id),
        }
    except GatewayError as e:
        record = {"call": number, "path": "Gateway.evaluate_with_configuration", "error": str(e)}
    with engine.connect() as c:
        record["model_calls_rows"] = [
            dict(r)
            for r in c.execute(
                text(
                    "select m.id::text, m.model_config_id::text, m.task_type::text, m.status::text, "
                    "m.terminal_state::text, m.tokens_in, m.tokens_out, m.cost::text, "
                    "m.cost_certainty::text, m.latency_ms, m.provider_request_id from model_calls m "
                    "order by created_at"
                )
            ).mappings()
        ]
        record["measurements"] = [
            dict(r)
            for r in c.execute(
                text(
                    "select model_call_id::text, streamed, first_text_ms, text_output_chars, "
                    "reasoning_present, reasoning_output_tokens, provider_cached_input_tokens, "
                    "provider_cache_write_tokens, exchange_message_id::text "
                    "from model_call_measurements order by created_at"
                )
            ).mappings()
        ]
        record["reservations"] = [
            dict(r)
            for r in c.execute(
                text(
                    "select state::text, slug, max_cost::text, settled_cost::text, "
                    "cost_certainty::text from budget_reservations order by created_at"
                )
            ).mappings()
        ]
    out["calls"].append(record)


door(2, 1024)
if cost1 + spent() < CAP:
    door(3, 16)
else:
    out["stopped"] = "cap reached before call 3"
out["store_spend_calls_2_3"] = spent()
out["total_including_call_1"] = round(cost1 + spent(), 6)
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
