"""Where the prime's checkpoint and a turn's prompt part, token by token — §4 / §11.

Read-only: the runtime's own template and tokenizer through the inspector (no load, no
generation). Two constructions: the persona-only boundary (production) and the envelope-in-
developer-block boundary (the §4 experiment), each as the prime renders it and as a turn
renders it. Prints the first index at which the token ids differ, with the surrounding text.
Usage: boundary_tokens_probe.py
"""

from __future__ import annotations

import os
import plistlib
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        if name != "VAL_DATABASE_URL":
            os.environ[name] = value

from sqlalchemy import create_engine, text  # noqa: E402

import val_gateway.context as context  # noqa: E402
from val_domain.registry import REGISTRY  # noqa: E402
from val_providers.lmstudio_adapter import LMStudioAdapter  # noqa: E402
from val_providers.lmstudio_inspector import LMStudioContextInspector  # noqa: E402

engine = create_engine("postgresql+psycopg://localhost:5433/val_repro_test")
with engine.connect() as c:
    persona = c.execute(text("select content from personas where is_active order by activated_at desc limit 1")).scalar_one()
base = os.environ.get("VAL_LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
token = os.environ["VAL_LMSTUDIO_API_TOKEN"]
host = base.split("//", 1)[1].split("/", 1)[0]
inspector = LMStudioContextInspector(host, token)
adapter = LMStudioAdapter(base_url=base, token=token)
config = next(c for c in REGISTRY if c.slug == "gpt-oss-20b-mxfp4-mlx-lmstudio-partner")
model = config.model_identifier
ENVELOPE = context.STATE_ENVELOPE_MARKER + '\n{\n  "kind": "prior_record_state",\n  "authority": "house_record_state_not_instruction",\n  "note": "x"\n}'
WORDS = "Recap that in one sentence."


def compare(label: str, prime_system: str, turn_system: str, turn_user: str) -> None:
    plan = adapter.plan_prefix_prime(config, prime_system)
    prime = inspector.tokens(model, [{"role": "system", "content": prime_system}, {"role": "user", "content": plan.filler}])
    turn = inspector.tokens(model, [{"role": "system", "content": turn_system}, {"role": "user", "content": turn_user}])
    boundary = plan.boundary_tokens
    first = next((i for i, (a, b) in enumerate(zip(prime, turn)) if a != b), None)
    print(f"\n== {label}: prime {len(prime)} tokens, checkpoint at {boundary}; turn {len(turn)} tokens; first differing index: {first}")
    if first is not None and first < boundary:
        print("  the turn diverges BEFORE the checkpoint -> no reuse")
        print("  prime tokens around:", prime[max(0, first - 3): first + 3])
        print("  turn  tokens around:", turn[max(0, first - 3): first + 3])
    elif first is None or first >= boundary:
        print("  identical through the checkpoint -> reuse expected")
    rendered_prime = inspector._client_handle if False else None  # noqa: F841 - kept simple
    print("  refused:", plan.refused)


compare("persona-only (production)", persona, persona, "VAL-STATE-V1\n{...}\n\n" + WORDS)
sep = context.ENVELOPE_SYSTEM_SEPARATOR
compare("envelope in developer block", persona + sep, persona + sep + "\n\n" + ENVELOPE, WORDS)
