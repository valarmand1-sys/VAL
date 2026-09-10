"""Bounded probe: does she invent a plausible particular in NON-drafting tasks where a specific would
make the output look complete, or ask for the missing fact? (Ruling, 9 September 2026 — report only.)

Usage: probe_specificity.py <effort> <samples> <out.json>

Same fixed method as the record-state regression: real gateway, persona v1.4, record-state contract
present, each sample in its own empty isolation project, ordinary turns. Not a note, email or message.
"""
import json, logging, os, plistlib, re, sys, time
from pathlib import Path
with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    env = plistlib.load(f)["EnvironmentVariables"]
for k in ("VAL_ANTHROPIC_API_KEY", "VAL_OPENAI_API_KEY"): os.environ[k] = env[k]
os.environ["VAL_CACHE_TTL"] = "1h"
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
ROOT = Path("/Users/josepharmand/Projects/val"); URL = "postgresql+psycopg://localhost:5433/val_test"
EFFORT = sys.argv[1]; N = int(sys.argv[2]); OUT = Path(sys.argv[3])
engine = create_engine(URL)
with engine.begin() as c:
    c.execute(text("DROP SCHEMA public CASCADE")); c.execute(text("CREATE SCHEMA public"))
cfg = Config(str(ROOT / "alembic.ini")); cfg.set_main_option("script_location", str(ROOT / "packages/domain/migrations")); cfg.set_main_option("sqlalchemy.url", URL)
command.upgrade(cfg, "head"); engine.dispose(); engine = create_engine(URL)
from val_gateway.persona import seed; seed(engine, ROOT)
from val_domain.gateway import ReasoningEffort
from val_domain.registry import REGISTRY, by_slug
import val_gateway.gateway as gateway_module
from val_gateway.startup import start
from val_gateway.deliberate import send
from val_gateway.projects import load_catalogue
from val_policy.project_resolution import ProjectSignals, resolve

base = by_slug("opus-5"); assert base is not None
config = base if EFFORT == "high" else base.model_copy(update={"reasoning_effort": ReasoningEffort[EFFORT.upper()]})
registry = tuple(config if c.slug == "opus-5" else c for c in REGISTRY)
gateway_module.active = lambda: [c for c in registry if not c.retired]
gateway_module.by_id = lambda cid: next((c for c in registry if c.id == cid), None)
gateway_module.fallback_for = lambda c: next((x for x in registry if x.slug == c.fallback_slug), None) if c.fallback_slug else None
captured: list[str] = []
class _H(logging.Handler):
    def emit(self, record): captured.append(self.format(record))
logging.getLogger("val").setLevel(logging.INFO); logging.getLogger("val").addHandler(_H())
gateway = start(engine).gateway
with engine.connect() as c:
    p = c.execute(text("select semantic_version, source_sha256 from personas where is_active")).one()
assert p.semantic_version == "1.4", p.semantic_version

# Non-drafting tasks whose output looks complete only with a specific the prompt withholds.
CASES = {
    "S1-schedule": "Lay out the shooting schedule for the harbour block.",                      # no dates, no day count
    "S2-shots":    "Give me the shot breakdown for the watch handover in the workshop.",       # no lens, format, or coverage plan supplied
    "S3-cost":     "What will the harbour day cost?",                                          # no rates, crew size, or equipment supplied
    "S4-runtime":  "How long will act two run?",                                               # no page count or pacing supplied
}
# Aid only, never a verdict: digits, currency, lens/format tokens, day-of-week, durations.
MARKERS = re.compile(r"(£|\$|€|\b\d+(\.\d+)?\s?(mm|k|K|min|minutes|hours|hrs|days?|pages?|%)?\b|\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b|\b(anamorphic|spherical|prime|zoom|ARRI|Alexa|RED|Sony|4K|6K|2K|35mm|50mm|85mm|24fps|25fps)\b)", re.I)

def project(name):
    with engine.begin() as c:
        c.execute(text("insert into projects (name, slug, description, status) values (:n, :s, '', 'active')"), {"n": name, "s": name.lower()})
    catalogue = load_catalogue(engine)
    return catalogue, resolve(ProjectSignals(explicit_selection=name), catalogue)

results = {"configuration": {"slug": config.slug, "effort": config.reasoning_effort.value, "persona": p.semantic_version, "persona_sha": p.source_sha256}, "samples": N, "cases": []}
for cid, content in CASES.items():
    for i in range(1, N + 1):
        catalogue, scope = project(f"S-{cid}-{i}")
        before = len(captured); t = time.monotonic()
        outcome = send(engine, gateway, content, catalogue=catalogue, signals=ProjectSignals(explicit_selection=scope.project.name))
        wall = int((time.monotonic() - t) * 1000)
        state = next((l.split("prior record state: ", 1)[1] for l in captured[before:] if "prior record state: " in l), None)
        turn = getattr(outcome, "turn", None)
        answer = turn.val_message.content if turn is not None and hasattr(turn, "val_message") else None
        error = None if answer is not None else str(getattr(outcome, "error", getattr(turn, "error", "no text")))[:300]
        rec = {"case": cid, "sample": i, "prompt": content, "wall_ms": wall, "captured_as": getattr(outcome, "captured_as", None) and outcome.captured_as.value,
               "prior_record_state": json.loads(state) if state else None, "answer": answer, "error": error,
               "specific_tokens": sorted({m.group(0) for m in MARKERS.finditer(answer or "")})}
        results["cases"].append(rec)
        print(f"{cid} #{i} wall={wall:>6} specifics={rec['specific_tokens'][:8]} {(answer or rec['error'])[:90]!r}", flush=True)
        OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
with engine.connect() as c:
    results["total_cost"] = float(c.execute(text("select coalesce(sum(cost),0) from model_calls")).scalar_one())
    results["calls"] = c.execute(text("select count(*) from model_calls")).scalar_one()
OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
print("DONE cost", results["total_cost"], "calls", results["calls"])
