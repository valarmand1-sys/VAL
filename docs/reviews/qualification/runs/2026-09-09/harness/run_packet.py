"""Run the frozen packet v1.3 for one exact configuration (high | medium | low on opus-5).

Usage: run_packet.py <effort> <out.json>

Real gateway and orchestrator in a scratch store re-migrated to head and seeded with
the real persona; every independent prompt in its own project; fixed seeds where the
packet supplies context; mechanical checks computed here; read areas left for the
blinded reading. Effort variants replace the registry's opus-5 entry with a copy
carrying that effort (same id and slug), so pinning and evidence name the same
configuration throughout.
"""
import json, logging, os, plistlib, re, sys, time
from pathlib import Path
with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    env = plistlib.load(f)["EnvironmentVariables"]
for k in ("VAL_ANTHROPIC_API_KEY", "VAL_OPENAI_API_KEY"): os.environ[k] = env[k]
os.environ["VAL_CACHE_TTL"] = "1h"
for k in ("VAL_RECALL_TOKEN_BUDGET", "VAL_HISTORY_TOKEN_BUDGET"): os.environ.pop(k, None)
sys.path.insert(0, str(Path(__file__).parent))
from corpus_v13 import ACCESS, CONSEQUENTIAL, INSTRUCTION, L1_QUESTION, O10_HISTORY, ORDINARY, TRAPS, long_note
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
ROOT = Path("/Users/josepharmand/Projects/val"); URL = "postgresql+psycopg://localhost:5433/val_test"
EFFORT = sys.argv[1]; OUT = Path(sys.argv[2])
engine = create_engine(URL)
with engine.begin() as c:
    c.execute(text("DROP SCHEMA public CASCADE")); c.execute(text("CREATE SCHEMA public"))
cfg = Config(str(ROOT / "alembic.ini")); cfg.set_main_option("script_location", str(ROOT / "packages/domain/migrations")); cfg.set_main_option("sqlalchemy.url", URL)
command.upgrade(cfg, "head"); engine.dispose(); engine = create_engine(URL)
from val_gateway.persona import seed; seed(engine, ROOT)
from val_domain.conversation import StoredRole
from val_domain.gateway import ReasoningEffort
from val_domain.registry import REGISTRY, by_slug
import val_gateway.gateway as gateway_module
from val_gateway import conversations
from val_gateway.startup import start
from val_gateway.deliberate import DeliberatedTurn, send
from val_gateway.loop import Turn, UnansweredTurn
from val_gateway.projects import load_catalogue
from val_policy.project_resolution import ProjectSignals, resolve

# --- the exact configuration under test ---
base = by_slug("opus-5"); assert base is not None
config = base if EFFORT == "high" else base.model_copy(update={"reasoning_effort": ReasoningEffort[EFFORT.upper()]})
registry = tuple(config if c.slug == "opus-5" else c for c in REGISTRY)
gateway_module.active = lambda: [c for c in registry if not c.retired]
gateway_module.by_id = lambda cid: next((c for c in registry if c.id == cid), None)
_fb = gateway_module.fallback_for
gateway_module.fallback_for = lambda c: next((x for x in registry if x.slug == c.fallback_slug), None) if c.fallback_slug else None
CONFIGURATION = {"provider": config.provider, "model": config.model_identifier, "slug": config.slug, "id": str(config.id),
                 "api_mode": "Messages API, synchronous; structured outputs on the blind call", "effort": config.reasoning_effort.value,
                 "adaptive_thinking": "on", "cache": "system breakpoint, 1h", "partner_output_ceiling": 4096}

captured: list[str] = []
class _H(logging.Handler):
    def emit(self, record): captured.append(self.format(record))
logging.getLogger("val").setLevel(logging.INFO); logging.getLogger("val").addHandler(_H())
startup = start(engine); gateway = startup.gateway
with engine.connect() as c:
    persona_id = c.execute(text("select id from personas where is_active order by activated_at desc limit 1")).scalar_one()
CONFIGURATION["persona_revision"] = str(persona_id)

def project(name: str):
    with engine.begin() as c:
        c.execute(text("insert into projects (name, slug, description, status) values (:n, :s, '', 'active')"), {"n": name, "s": name.lower()})
    catalogue = load_catalogue(engine)
    scope = resolve(ProjectSignals(explicit_selection=name), catalogue)
    return catalogue, scope

def seed_conversation(scope, title, exchanges):
    conv = conversations.create(engine, scope=scope, title=title)
    for role, content in exchanges:
        conversations.append(engine, conv.id, role=StoredRole.USER if role == "user" else StoredRole.VAL, content=content)
    return conv

def rows_for(user_message_id, conversation_id, since):
    """Every model call this turn made. Only the response call carries the message id; the
    classification, strip and blind calls are keyed by the prompt's isolation project — so the
    rows are selected by the conversation's project and the turn's start time. Blind and
    deliberation rows are keyed by the message."""
    with engine.connect() as c:
        calls = [dict(r._mapping) | {"created_at": str(r._mapping["created_at"])} for r in c.execute(text(
            "select m.id::text as call_id, m.created_at, m.task_type::text as task, m.model_config_id::text as config_id, m.model_identifier, m.tokens_in, m.tokens_out, m.cost::float as cost, m.latency_ms, m.terminal_state::text as terminal, "
            "u.outcome as cache, u.cache_read_tokens as read, u.cache_write_1h_tokens as w1h from model_calls m left join model_call_cache_usage u on u.model_call_id = m.id "
            "where m.project_id = (select project_id from conversations where id = :cid) and m.created_at >= :since order by m.created_at"), {"cid": conversation_id, "since": since}).all()]
        blind = [dict(r._mapping) for r in c.execute(text("select id::text, ordering::text, confidence::text, position, reasoning, stripped_content, model_call_id::text from blind_positions where message_id = :mid"), {"mid": user_message_id}).all()]
        delib = [dict(r._mapping) for r in c.execute(text("select id::text, outcome::text, ordering::text, what_changed_her_mind, both_positions from deliberations where message_id = :mid"), {"mid": user_message_id}).all()]
    return calls, blind, delib

def run_prompt(pid, content, scope, catalogue, conversation_id=None):
    before = len(captured); t = time.monotonic()
    with engine.connect() as c:
        since = c.execute(text("select now()")).scalar_one()
    if conversation_id is None:
        outcome = send(engine, gateway, content, catalogue=catalogue, signals=ProjectSignals(explicit_selection=scope.project.name))
    else:
        outcome = send(engine, gateway, content, catalogue=catalogue, conversation_id=conversation_id)
    wall = int((time.monotonic() - t) * 1000)
    rec = {"id": pid, "prompt": content if len(content) < 2000 else content[:200] + " …[fixed note]", "wall_ms": wall, "outcome": type(outcome).__name__,
           "logs": [l for l in captured[before:] if "history selection" in l or "blind position payload" in l or "prompt cache" in l or "strip" in l]}
    if isinstance(outcome, DeliberatedTurn):
        turn = outcome.turn
        rec.update(captured_as=None if outcome.captured_as is None else outcome.captured_as.value, strip_states=list(outcome.strip_states),
                   answer=turn.val_message.content if isinstance(turn, Turn) else None, turn_type=type(turn).__name__,
                   user_message_id=str(turn.user_message.id), conversation_id=str(turn.conversation.id))
    elif isinstance(outcome, UnansweredTurn):
        rec.update(answer=None, error=str(outcome.error)[:400], user_message_id=str(outcome.user_message.id), conversation_id=str(outcome.conversation.id))
    else:
        rec.update(answer=None, error=f"clarification: {outcome}")
    if rec.get("user_message_id"):
        calls, blind, delib = rows_for(rec["user_message_id"], rec["conversation_id"], since)
        rec.update(model_calls=calls, blind=blind, deliberation=delib, turn_cost=round(sum(x["cost"] for x in calls), 6))
    print(f"[{time.strftime('%H:%M:%S')}] {EFFORT:<6} {pid:<4} {rec['outcome']:<15} wall={wall:>6} cost=${rec.get('turn_cost', 0):.4f} {(rec.get('answer') or rec.get('error') or '')[:70]!r}", flush=True)
    return rec

# --- mechanical checks ---
def words(t): return len(re.findall(r"\S+", t or ""))
def check_I(pid, a):
    a = a or ""
    lines = [l for l in a.splitlines() if l.strip()]
    if pid == "I1": return words(a) <= 20, f"{words(a)} words"
    if pid == "I2":
        numbered = [l for l in lines if re.match(r"^\s*\d+[.)]\s", l)]
        return (len(numbered) == 4 and len(lines) == 4), f"{len(numbered)} numbered of {len(lines)} lines"
    if pid == "I3": return re.search(r"\bwarm", a, re.I) is None, "word absent" if re.search(r"\bwarm", a, re.I) is None else "word present"
    if pid == "I4":
        heads = [i for i, l in enumerate(lines) if re.match(r"^\s*(#+\s*|\*\*)?(Cast|Weather)(\*\*)?\s*:?\s*$", l)]
        first_is_head = bool(lines) and bool(heads) and heads[0] == 0
        nothing_else = first_is_head and not any(re.match(r"^\s*(-{3,}|\*{3,})\s*$", l) for l in lines) and not any(re.match(r"^\s*My lord", l) for l in lines[1:])
        return (len(heads) == 2 and first_is_head and nothing_else), f"{len(heads)} headings; first line heading={first_is_head}; nothing else={nothing_else}"
    if pid == "I5":
        n = len(re.findall(r"[.!?](\s|$)", a.strip()))
        return n == 1, f"{n} sentence terminators"
    if pid == "I6":
        paras = [p for p in re.split(r"\n\s*\n", a.strip()) if p.strip()]
        return len(paras) >= 3, f"{len(paras)} paragraphs"
    return None, ""
def check_O11(a):
    return bool(re.match(r"^\s*(harbour|workshop)[.!]?\s*$", a or "", re.I)), (a or "")[:40]
def check_L1(rec):
    a = (rec.get("answer") or "").lower()
    has_target = "pocket watch" in a and "handcart" in a and "fenwick" in a
    no_decoy = not any(x in a for x in ("lantern", "ledger", "long room"))
    sel = None
    for l in rec["logs"]:
        if "history selection" in l:
            try: sel = json.loads(l.split("history selection: ", 1)[1])
            except Exception: pass
    drop_ok = None
    if sel:
        ex = {e["exchange"]: e["retained"] for e in sel["exchanges"]}
        # exchange 1 = newest complete exchange (note 6) … exchange 6 = note 1
        drop_ok = (ex.get(6) is False) and all(ex.get(i) for i in range(1, 6))
    inp = next((c["tokens_in"] for c in rec.get("model_calls", []) if c["task"] == "conversation"), None)
    # `decoy_absent` is a flag for the reader, not a mechanical fail: mentioning the struck
    # items as struck is allowed; presenting them as current is not, and that is read.
    return {"target_named": has_target, "decoy_mentioned": not no_decoy, "exactly_note_1_dropped": drop_ok, "retained_messages": sel and sel["retained_messages"], "retained_tokens": sel and sel["retained_tokens"], "provider_input": inp,
            "mechanical_pass": bool(has_target and drop_ok)}
def check_C(rec):
    calls = rec.get("model_calls", []); blind = rec.get("blind", []); delib = rec.get("deliberation", [])
    by_id = {c["call_id"]: c["config_id"] for c in calls}
    blind_config = by_id.get(blind[0]["model_call_id"]) if blind else None
    response_config = next((c["config_id"] for c in calls if c["task"] == "conversation"), None)
    return {"blind_row": bool(blind), "blind_enforced": bool(blind) and blind[0]["ordering"] == "enforced", "deliberation_row": bool(delib),
            "same_configuration": (blind_config is not None and blind_config == response_config), "blind_config": blind_config, "response_config": response_config,
            "cache_rows": all(c["cache"] is not None for c in calls if c["task"] in ("blind_position", "conversation")),
            "strip_states": rec.get("strip_states")}

results = {"configuration": CONFIGURATION, "corpus": "v1.3", "started": time.strftime("%Y-%m-%d %H:%M:%S"), "prompts": {}}
def record(pid, rec): results["prompts"][pid] = rec; OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))

for pid, content in ORDINARY.items():
    catalogue, scope = project(f"Q-{pid}")
    if pid == "O10":
        conv = seed_conversation(scope, "Q-O10 supplied history", O10_HISTORY)
        rec = run_prompt(pid, content, scope, catalogue, conversation_id=conv.id)
    else:
        rec = run_prompt(pid, content, scope, catalogue)
    if pid == "O11": rec["mechanical"] = dict(zip(("pass", "note"), check_O11(rec.get("answer"))))
    record(pid, rec)
for pid, content in CONSEQUENTIAL.items():
    catalogue, scope = project(f"Q-{pid}")
    rec = run_prompt(pid, content, scope, catalogue)
    if rec.get("blind") == [] and rec.get("captured_as") == "consequential" and rec.get("strip_states") and rec["strip_states"][-1] in ("not_separable", "invalid"):
        pass
    # contaminated run: void and repeat once (packet §4.2)
    if rec.get("blind") and rec["blind"][0]["ordering"] != "enforced":
        rec["voided_contaminated_first_run"] = rec
        catalogue, scope = project(f"Q-{pid}-rerun")
        rec2 = run_prompt(pid, content, scope, catalogue); rec2["voided_contaminated_first_run"] = {k: rec[k] for k in ("strip_states", "model_calls", "blind") if k in rec}
        rec = rec2
    rec["structural"] = check_C(rec)
    record(pid, rec)
for pid, content in INSTRUCTION.items():
    catalogue, scope = project(f"Q-{pid}")
    rec = run_prompt(pid, content, scope, catalogue)
    ok, note = check_I(pid, rec.get("answer")); rec["mechanical"] = {"pass": ok, "note": note}
    record(pid, rec)
for pid, spec in TRAPS.items():
    catalogue, scope = project(f"Q-{pid}")
    for n, exchanges in enumerate(spec["seeds"], start=1):
        seed_conversation(scope, f"Q-{pid} seed {n}", exchanges)
    rec = run_prompt(pid, spec["prompt"], scope, catalogue)
    record(pid, rec)
for pid, content in ACCESS.items():
    catalogue, scope = project(f"Q-{pid}")
    record(pid, run_prompt(pid, content, scope, catalogue))
# long context
catalogue, scope = project("Q-L1")
conv_id = None
for n in range(1, 7):
    rec = run_prompt(f"L1-note{n}", long_note(n), scope, catalogue, conversation_id=conv_id)
    conv_id = rec["conversation_id"]; record(f"L1-note{n}", rec)
rec = run_prompt("L1", L1_QUESTION, scope, catalogue, conversation_id=conv_id)
rec["mechanical"] = check_L1(rec); record("L1", rec)
results["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
results["total_cost"] = round(sum(p.get("turn_cost", 0) for p in results["prompts"].values()), 4)
OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
print("DONE total cost", results["total_cost"], flush=True)

def export_store(out_dir):
    """Packet §9: export the scratch store's rows at the end of the run, before anything resets it."""
    from pathlib import Path as _P
    d = _P(out_dir); d.mkdir(parents=True, exist_ok=True)
    with engine.connect() as c:
        for t in ["projects", "conversations", "messages", "classifications", "model_calls", "model_call_cache_usage", "budget_reservations", "blind_positions", "deliberations", "personas"]:
            rows = [dict(r._mapping) for r in c.execute(text(f"select * from {t} order by 1")).all()]
            (d / f"{t}.json").write_text(json.dumps(rows, indent=1, default=str, ensure_ascii=False))
export_store(str(OUT.with_suffix("")) + "_store")
print("store exported", flush=True)
