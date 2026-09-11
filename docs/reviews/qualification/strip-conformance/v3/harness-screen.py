"""Strip candidates through the real gateway's evaluation door (ruling, 10 September 2026).

Usage: run_strip_v3_screen.py OUT.json CAP_USD CASES route:runs [route:runs ...]
  CASES  comma-separated case ids, or "all"
  route  a registry slug registered for evaluation only (NOT_ADMITTED, no profile)

Each call goes through `val_gateway.deliberate._strip` pinned to the exact
registered configuration with `evaluation=True`, in the scratch store, so the
reservation, the retry rule (no retry on `truncated`), the model_calls row and
the settlement all run as they do live. After every call the cumulative measured
cost is read back from model_calls; the run stops when it exceeds CAP_USD.
"""

import json
import logging
import os
import plistlib
import statistics
import sys
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    env = plistlib.load(f)["EnvironmentVariables"]
for k in ("VAL_ANTHROPIC_API_KEY", "VAL_OPENAI_API_KEY"):
    os.environ[k] = env[k]
os.environ["VAL_CACHE_TTL"] = "1h"

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

ROOT = Path("/Users/josepharmand/Projects/val")
URL = "postgresql+psycopg://localhost:5433/val_test"
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

from val_domain.gateway import Classification
from val_domain.project import ExplicitNoProject
from val_domain.registry import by_slug
from val_gateway.deliberate import _strip
from val_gateway.persona import seed
from val_gateway.startup import start
from val_policy.deliberation import _collapse, same_text

seed(engine, ROOT)
logging.getLogger("val").setLevel(logging.ERROR)
gateway = start(engine).gateway

out_path = Path(sys.argv[1])
cap = float(sys.argv[2])
case_filter = None if sys.argv[3] == "all" else set(sys.argv[3].split(","))
plan = [(s.split(":")[0], int(s.split(":")[1])) for s in sys.argv[4:]]
suite = json.load(open(ROOT / "docs/reviews/qualification/strip-conformance/v3/suite.json"))["cases"]
cases = [c for c in suite if case_filter is None or c["id"] in case_filter]


def judge(case, attempts):
    v = attempts.validation
    exp = case

    def residue_ok(r):
        return same_text(r, exp["expected_residue"] or "") or any(
            same_text(r, a) for a in exp.get("expected_residue_alternatives", [])
        )

    if exp["expected_preference_present"] is False:
        ok = v.state == "no_preference"
        return ("conformant" if ok else "BLOCKING"), ([] if ok else [f"expected no_preference, got {v.state}: " + "; ".join(v.reasons)])
    if exp["expected_separable"] is False:
        if v.state == "not_separable":
            return "conformant", []
        return ("BLOCKING" if v.state == "enforceable" else "false-contamination"), [f"got {v.state}"]
    if v.state == "enforceable":
        problems = []
        for s in exp["expected_spans"]:
            if _collapse(s["text"]).strip() in (v.residue or ""):
                problems.append(f"{s['kind']} survives: {s['text']!r}")
        if not residue_ok(v.residue or ""):
            problems.append("residue differs from expected")
        return ("conformant" if not problems else "BLOCKING"), problems
    return "false-contamination", [f"got {v.state}: " + "; ".join(v.reasons)]


def calls_since(marker):
    with engine.connect() as c:
        rows = c.execute(
            text(
                "select id, tokens_in, tokens_out, cost, latency_ms, terminal_state::text "
                "from model_calls where task_type = 'strip' and created_at > :m order by created_at"
            ),
            {"m": marker},
        ).all()
        total = c.execute(text("select coalesce(sum(cost), 0) from model_calls")).scalar_one()
    return [dict(id=str(r[0]), tokens_in=r[1], tokens_out=r[2], cost=float(r[3]), latency_ms=r[4], terminal=r[5]) for r in rows], float(total)


results = []
stopped = None
for slug, runs in plan:
    config = by_slug(slug)
    assert config is not None, slug
    for case in cases:
        for run in range(1, runs + 1):
            with engine.connect() as c:
                marker = c.execute(text("select now()")).scalar_one()
            t = time.monotonic()
            attempts = _strip(
                gateway, case["message"], ExplicitNoProject(), Classification.PROTECTED,
                configuration=config, evaluation=(config.admission.value == "not_admitted"),
            )
            ms = int((time.monotonic() - t) * 1000)
            calls, total = calls_since(marker)
            verdict, problems = judge(case, attempts)
            rec = {
                "route": slug, "case": case["id"], "run": run, "ms": ms,
                "states": list(attempts.states), "final_state": attempts.validation.state,
                "calls": calls, "cost": sum(x["cost"] for x in calls),
                "residue": attempts.validation.residue,
                "spans": [{"text": s.text, "kind": s.kind} for s in attempts.validation.spans],
                "verdict": verdict, "problems": problems,
            }
            results.append(rec)
            print(
                f"{slug:<16} {case['id']:<3} r{run} {verdict:<19} states={attempts.states} "
                f"{ms/1000:.1f}s ${rec['cost']:.4f} out={[x['tokens_out'] for x in calls]} "
                f"{'; '.join(problems)[:90]}",
                flush=True,
            )
            out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
            if total > cap:
                stopped = f"STOPPED: cumulative measured cost ${total:.4f} exceeded cap ${cap:.2f}"
                print(stopped, flush=True)
                break
        if stopped:
            break
    if stopped:
        break

print("\n=== summary ===")
for slug, _ in plan:
    rs = [r for r in results if r["route"] == slug]
    if not rs:
        continue
    conformant = sum(1 for r in rs if r["verdict"] == "conformant")
    lat = [r["ms"] for r in rs]
    print(
        f"{slug:<16} {conformant}/{len(rs)} conformant  latency median {statistics.median(lat)/1000:.1f}s "
        f"max {max(lat)/1000:.1f}s  cost ${sum(r['cost'] for r in rs):.4f}  "
        f"truncated={sum(1 for r in rs if 'truncated' in r['states'])} retried={sum(1 for r in rs if len(r['states'])>1)}"
    )
with engine.connect() as c:
    print("model_calls strip rows:", c.execute(text("select count(*) from model_calls where task_type='strip'")).scalar_one(),
          " total cost:", float(c.execute(text("select coalesce(sum(cost),0) from model_calls")).scalar_one()))
print("DONE", flush=True)
