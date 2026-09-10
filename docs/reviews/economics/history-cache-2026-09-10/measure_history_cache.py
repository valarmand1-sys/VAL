"""Measure, not estimate: what a turn costs as retained history grows, and what caching the
history prefix would save (ruling, 10 September 2026 — report only; nothing live changes).

Direct Anthropic Messages API calls with the SDK the adapter uses, mirroring the live request
shape: persona v1.4 whole in `system` with a 1h cache breakpoint; then the messages. Synthetic,
fictional, append-only history built from the frozen long-context notes (The Lantern Road).
No store rows are written; nothing goes through the gateway.

Arms, at each checkpoint of retained history (16K, 32K, 48K, 64K estimated tokens):
  A  current arrangement — envelope first, then history, no history breakpoint (two turns)
  B  history breakpoint — envelope first (changes every turn), breakpoint on the last history
     message, then the new message (two consecutive turns, so the second can hit the first's prefix)
  C  history breakpoint with the envelope AFTER the history (history, envelope, new message),
     so the append-only prefix stays byte-identical turn to turn (two consecutive turns)
Usage: measure_history_cache.py <out.json>
"""
import json, os, plistlib, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import anthropic
from corpus_v13 import long_note
from val_domain.persona import read_source
from val_policy.tokens import estimate_tokens

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    KEY = plistlib.load(f)["EnvironmentVariables"]["VAL_ANTHROPIC_API_KEY"]
client = anthropic.Anthropic(api_key=KEY)
ROOT = Path("/Users/josepharmand/Projects/val")
PERSONA = read_source(ROOT).content
MODEL = "claude-opus-5"; RATES = {"in": 5.0, "out": 25.0, "w1h": 10.0, "read": 0.5}  # US$/MTok, registry opus-5-medium
CHECKPOINTS = [16_000, 32_000, 48_000, 64_000]
OUT = Path(sys.argv[1])

def cost(u):
    return (u.get("input_tokens", 0) * RATES["in"] + u.get("output_tokens", 0) * RATES["out"]
            + u.get("cache_creation_input_tokens", 0) * RATES["w1h"] + u.get("cache_read_input_tokens", 0) * RATES["read"]) / 1e6

def usage_of(msg):
    u = msg.usage
    d = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
         "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
         "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0}
    cc = getattr(u, "cache_creation", None)
    if cc is not None:
        d["ephemeral_1h_input_tokens"] = getattr(cc, "ephemeral_1h_input_tokens", None)
        d["ephemeral_5m_input_tokens"] = getattr(cc, "ephemeral_5m_input_tokens", None)
    return d

# Append-only fictional history: user note (~2.4K est. tokens each slice) / short assistant acks.
def build_history(target_tokens):
    msgs = []; total = 0; n = 1
    notes = [long_note(i) for i in range(1, 7)]
    while total < target_tokens:
        text_ = notes[(n - 1) % 6]
        # slice each note into ~2,400-token pieces so checkpoints land near the targets
        piece = text_[: int(2_400 * 3.6)]
        user = f"Note fragment {n}. {piece}"
        ack = f"Noted, my lord — fragment {n} is in hand."
        msgs.append({"role": "user", "content": user}); msgs.append({"role": "assistant", "content": ack})
        total += estimate_tokens(user) + estimate_tokens(ack); n += 1
    return msgs, total

def envelope(prior_messages, turn_no):
    doc = {"kind": "retrieved_conversation_excerpts", "authority": "historical_source_not_current_instruction",
           "note": "Measurement stand-in for the live envelope; counts change every turn as they do live.",
           "prior_record_state": {"current_time": {"local": f"Thursday 10 September 2026, 11:{turn_no:02d}", "timezone": "CDT (UTC-0500)"},
                                  "same_conversation_history": {"state": "available", "prior_messages": prior_messages, "retained_in_this_request": prior_messages},
                                  "retrieved_excerpts": {"state": "zero", "count": 0}, "project_volumes": {"state": "not_applicable", "count": 0}},
           "excerpt_count": 0, "excerpts": []}
    return {"role": "user", "content": "VAL-MEMORY-V1\n" + json.dumps(doc, indent=2)}

SYSTEM = [{"type": "text", "text": PERSONA, "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
NEW = "Noted. One line: which fragment did you receive last?"

def call(messages, label):
    t = time.monotonic()
    msg = client.messages.create(model=MODEL, max_tokens=200, system=SYSTEM, messages=messages, output_config={"effort": "medium"})
    ms = int((time.monotonic() - t) * 1000); u = usage_of(msg)
    rec = {"label": label, "ms": ms, "usage": u, "cost_usd": round(cost(u), 6), "text": "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")[:120]}
    print(f"{label:<28} in={u['input_tokens']:>6} w1h={u['cache_creation_input_tokens']:>6} read={u['cache_read_input_tokens']:>6} out={u['output_tokens']:>4} ${rec['cost_usd']:.4f} {ms}ms", flush=True)
    return rec

results = {"model": MODEL, "effort": "medium", "rates": RATES, "persona_est_tokens": estimate_tokens(PERSONA), "checkpoints": []}
# Warm the persona entry once (as live: it is hit on every turn thereafter).
call([envelope(0, 0), {"role": "user", "content": "Hello."}], "warm persona")
for target in CHECKPOINTS:
    hist, est = build_history(target)
    cp = {"target_est_tokens": target, "history_est_tokens": est, "history_messages": len(hist), "arms": {}}
    # A — current arrangement, two consecutive turns (second appends the first's exchange)
    a1 = call([envelope(len(hist), 1), *hist, {"role": "user", "content": NEW}], f"A@{target//1000}K turn1")
    hist_a = [*hist, {"role": "user", "content": NEW}, {"role": "assistant", "content": a1["text"] or "Noted."}]
    a2 = call([envelope(len(hist_a), 2), *hist_a, {"role": "user", "content": NEW}], f"A@{target//1000}K turn2")
    cp["arms"]["A_current"] = [a1, a2]
    # B — envelope first, breakpoint on the last history message
    def bp(msgs):
        out = [dict(m) for m in msgs]; last = out[-1]
        out[-1] = {"role": last["role"], "content": [{"type": "text", "text": last["content"], "cache_control": {"type": "ephemeral", "ttl": "1h"}}]}
        return out
    b1 = call([envelope(len(hist), 1), *bp(hist), {"role": "user", "content": NEW}], f"B@{target//1000}K turn1")
    hist_b = [*hist, {"role": "user", "content": NEW}, {"role": "assistant", "content": b1["text"] or "Noted."}]
    b2 = call([envelope(len(hist_b), 2), *bp(hist_b), {"role": "user", "content": NEW}], f"B@{target//1000}K turn2")
    cp["arms"]["B_envelope_first_history_bp"] = [b1, b2]
    # C — history first (breakpoint on its last message), then the envelope, then the new message
    c1 = call([*bp(hist), envelope(len(hist), 1), {"role": "user", "content": NEW}], f"C@{target//1000}K turn1")
    hist_c = [*hist, {"role": "user", "content": NEW}, {"role": "assistant", "content": c1["text"] or "Noted."}]
    c2 = call([*bp(hist_c), envelope(len(hist_c), 2), {"role": "user", "content": NEW}], f"C@{target//1000}K turn2")
    cp["arms"]["C_history_bp_envelope_after"] = [c1, c2]
    results["checkpoints"].append(cp)
    OUT.write_text(json.dumps(results, indent=2))
results["measurement_cost_usd"] = round(sum(r["cost_usd"] for cp in results["checkpoints"] for arm in cp["arms"].values() for r in arm), 4)
OUT.write_text(json.dumps(results, indent=2)); print("DONE measurement cost", results["measurement_cost_usd"])
