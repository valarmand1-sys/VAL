"""Read-only rendered-equivalence check, before any inference (owner ruling, 18 September 2026).

Usage: rendered_equivalence.py OUT.json SLUG

Only the server's read-only surface is touched: `/props`, `/v1/models`, `/apply-template`
and `/metrics`. Nothing is generated.

What is established, and how:

1. The template identity under the narrow rule — raw official, canonical official
   (the raw file minus its ONE terminal LF) and active, all three hashes kept.
2. The running server was launched with `--chat-template-file` naming the raw pinned
   official file itself (read from the process table), so the server's rendering IS
   this runtime's rendering of the pinned official template.
3. One harmless canonical chat body — the adapter's own `wire_body`, the body the
   preflight counts and inference sends — is rendered through `/apply-template`, twice,
   in each thinking state. The renderings are recorded whole with their SHA-256 and
   must be identical across the two calls.
4. The one byte the runtime drops follows a right-trimming `-%}` tag, so it cannot
   reach any rendering; that is checked on the pinned bytes, not assumed.

What is NOT available and is said so: a second engine to render the raw file
independently. No Jinja engine is installed in the project or on the machine, none may
be added without a ruling, and llama.cpp b10360 accepts no per-request template — the
server can only ever hold the form it read from the pinned file.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

OUT, SLUG = Path(sys.argv[1]), sys.argv[2]
KEY_FILE = Path.home() / ".config/val/llamacpp.key"
os.environ["VAL_LLAMACPP_API_KEY"] = KEY_FILE.read_text().strip()

ROOT = Path("/Users/josepharmand/Projects/val")
PINNED_TEMPLATE = ROOT / "docs/reviews/qualification/runs/2026-09-18-gemma-4-31b-contract-reassessment/official-chat_template@842da37.jinja"

from val_domain.gateway import Message  # noqa: E402
from val_domain.registry import by_slug  # noqa: E402
from val_gateway.startup import build_adapters  # noqa: E402
from val_policy.budget import CONVERSATION_MAX_OUTPUT_TOKENS  # noqa: E402
from val_providers.llamacpp_adapter import wire_body  # noqa: E402
from val_providers.llamacpp_inspector import compare_with_pinned_template  # noqa: E402

out: dict[str, object] = {"checks": [], "stop": None}


def check(name: str, ok: bool, detail: object) -> None:
    out["checks"].append({"check": name, "ok": bool(ok), "detail": detail})  # type: ignore[union-attr]
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        out["stop"] = name
        OUT.write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False))
        print("STOP:", name, "|", detail)
        sys.exit(4)


entry = by_slug(SLUG)
assert entry is not None, SLUG
adapters, problems = build_adapters({"llamacpp"})
assert not problems, problems
inspector = adapters["llamacpp"]._inspector

# --- 1. identity under the narrow rule -------------------------------------------------------
pinned = PINNED_TEMPLATE.read_bytes()
identity = compare_with_pinned_template(pinned, str(inspector.props().get("chat_template") or ""))
out["template_identity"] = {
    "raw_official_sha256": identity.raw_official_sha256,
    "canonical_official_sha256": identity.canonical_official_sha256,
    "active_sha256": identity.active_sha256,
    "RAW OFFICIAL == ACTIVE": identity.raw_equal,
    "CANONICAL OFFICIAL == ACTIVE": identity.canonical_equal,
}
check("template identity accepted under the one-terminal-LF rule", identity.accepted, out["template_identity"])

# --- 2. the server was launched from the raw pinned file ---------------------------------------
table = subprocess.run(["ps", "-axo", "command"], capture_output=True, text=True, check=True).stdout
launches = [line for line in table.splitlines() if line.lstrip().startswith("llama-server ") or "/llama-server " in line]
out["server_launch_commands"] = launches  # the key is a file path on the command line, never a value
check("exactly one llama-server is running", len(launches) == 1, len(launches))
check("it was launched with --chat-template-file naming the raw pinned official file",
      f"--chat-template-file {PINNED_TEMPLATE}" in launches[0], str(PINNED_TEMPLATE))

# --- 3. the dropped byte cannot reach a rendering -----------------------------------------------
tail = pinned[-16:]
out["pinned_tail_bytes"] = tail.decode("utf-8")
check("the pinned file ends `-%}` then exactly one LF (a right-trimming tag strips what follows)",
      pinned.endswith(b"-%}\n") and not pinned.endswith(b"\n\n"), repr(tail))

# --- 4. the harmless canonical body, rendered by the active template -----------------------------
messages = (
    Message(role="user", content="Please name one primary colour."),
    Message(role="assistant", content="Blue."),
    Message(role="user", content="Thank you. Name one more."),
)
SYSTEM = "You are a courteous assistant. Answer briefly."
renderings = {}
for label, thinking in (("thinking_off", False), ("thinking_on", True)):
    config = entry.model_copy(update={"thinking_enabled": thinking})
    body = wire_body(config, messages, SYSTEM, CONVERSATION_MAX_OUTPUT_TOKENS)
    first, second = inspector.render(body), inspector.render(body)
    renderings[label] = {
        "input_body": body,
        "rendered_prompt": first,
        "rendered_sha256": hashlib.sha256(first.encode("utf-8")).hexdigest(),
        "second_render_sha256": hashlib.sha256(second.encode("utf-8")).hexdigest(),
        "input_tokens": inspector.count(body),
    }
    check(f"{label}: the rendering is deterministic (two calls, one prompt)", first == second, renderings[label]["rendered_sha256"])
    check(f"{label}: the rendering does not end in a stray newline from the template's tail",
          not first.endswith("\n\n"), repr(first[-40:]))
    check(f"{label}: the thinking switch is in the rendering as the official template writes it",
          ("<|think|>" in first) is thinking, "<|think|>" in first)
out["renderings"] = renderings
check("the two thinking states render differently (the declared state reaches the template)",
      renderings["thinking_off"]["rendered_sha256"] != renderings["thinking_on"]["rendered_sha256"], None)

out["rendered_equivalence"] = True
out["basis"] = (
    "CANONICAL OFFICIAL == ACTIVE byte for byte; the server was launched from the raw pinned file, so its "
    "rendering is this runtime's rendering of the pinned official template; the rendering is deterministic; "
    "the one dropped byte follows a right-trimming tag and cannot reach a rendering."
)
out["limitation"] = (
    "No second engine rendered the raw file independently: no Jinja engine is installed and none was added; "
    "llama.cpp b10360 accepts no per-request template."
)
OUT.write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False))
print("rendered equivalence = TRUE |", OUT)
