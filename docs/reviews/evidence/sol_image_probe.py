"""Verify Sol's image-input tokenisation and pricing against the documented formula.

Owner ruling, 19 September 2026 (Track C, §3): the minimum paid calls needed to
establish that image input can be **bounded reliably**, under a $0.50 cap for the
whole sequence. Run from the repository root:

    uv run python docs/reviews/evidence/sol_image_probe.py OUT.json

Before every paid probe this records, and prints, exactly what the ruling
requires: the test image, its transmitted dimensions, any derived
representation, the predicted image-input tokens from the documented formula,
the predicted cost of the whole request including its text, and the cumulative
projected spend. It refuses to transmit when the next call would take the
sequence past the cap.

The request is built here rather than through `OpenAIAdapter` on purpose: this
probe must establish what the **provider** does, so that the adapter can then be
written against a verified fact instead of a documented promise. It calls the
Responses API directly, with the same `input_image` shape the adapter will use.

Nothing here is a qualification and nothing is admitted. No key is printed.
"""

import io
import json
import math
import plistlib
import sys
from base64 import b64encode
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import openai
from PIL import Image

from val_domain.gateway import ImageInputSupport
from val_domain.registry import by_slug
from val_policy.attachments import admit_image
from val_policy.budget import image_input_tokens

SLUG = "gpt-5-6-sol-medium"
CAP_USD = 0.50
#: Small enough to be cheap, large enough that a reasoning route can answer.
MAX_OUTPUT_TOKENS = 64
PLIST = Path.home() / "Library/LaunchAgents/house.armand.val.api.plist"

#: The facts under verification, transcribed from developers.openai.com on
#: 19 September 2026 and carried on the registry entry once proven.
DETAIL = "high"
PATCH_PIXELS = 32
PATCH_BUDGET = 2_500
TOKEN_MULTIPLIER = 1.2

PROMPT = "Reply with one word: the dominant colour of this image."

#: The capability declaration under test, exactly as it will be registered.
SUPPORT = ImageInputSupport(
    media_types=frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"}),
    max_long_edge_pixels=2048,
    max_byte_size=50_000_000,
    detail=DETAIL,
    patch_pixels=PATCH_PIXELS,
    patch_budget=PATCH_BUDGET,
    token_multiplier=TOKEN_MULTIPLIER,
    verified_on=date(2026, 9, 19),
    source="developers.openai.com/api/docs/guides/images-vision",
)


def key() -> str:
    """The service's own OpenAI key, read in memory and never displayed."""
    return str(plistlib.loads(PLIST.read_bytes())["EnvironmentVariables"]["VAL_OPENAI_API_KEY"])


def chequerboard(width: int, height: int) -> bytes:
    """A deterministic test image: navy, with a white square in the upper left.

    Deterministic so the exact bytes under test are reproducible from this file,
    and legible so that a wrong answer means something.
    """
    image = Image.new("RGB", (width, height), "navy")
    block = Image.new("RGB", (max(1, width // 4), max(1, height // 4)), "white")
    image.paste(block, (0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def predict(width: int, height: int) -> dict[str, Any]:
    """The documented arithmetic, written out so the prediction is checkable."""
    patches = math.ceil(width / PATCH_PIXELS) * math.ceil(height / PATCH_PIXELS)
    capped = min(patches, PATCH_BUDGET)
    return {
        "patches_before_budget": patches,
        "patch_budget": PATCH_BUDGET,
        "patches_after_budget": capped,
        "token_multiplier": TOKEN_MULTIPLIER,
        "predicted_image_tokens": math.ceil(capped * TOKEN_MULTIPLIER),
        # The shipped reservation function must agree with the arithmetic above;
        # a formula that lives in two places is a formula that will disagree.
        "shipped_function_agrees": math.ceil(capped * TOKEN_MULTIPLIER)
        == image_input_tokens(width, height, SUPPORT),
        "formula": ("ceil(min(ceil(w/32) * ceil(h/32), patch_budget) * token_multiplier)"),
    }


def main(out: Path) -> int:
    config = by_slug(SLUG)
    if config is None:
        raise RuntimeError(f"{SLUG} is not in the registry")
    client = openai.OpenAI(api_key=key())
    record: dict[str, Any] = {
        "started_at": datetime.now(UTC).isoformat(),
        "configuration": {
            "slug": config.slug,
            "model_identifier": config.model_identifier,
            "cost_per_mtok_in_usd": config.cost_per_mtok_in_usd,
            "cost_per_mtok_out_usd": config.cost_per_mtok_out_usd,
        },
        "documented_facts": {
            "detail": DETAIL,
            "patch_pixels": PATCH_PIXELS,
            "patch_budget": PATCH_BUDGET,
            "token_multiplier": TOKEN_MULTIPLIER,
            "source": "developers.openai.com/api/docs/guides/images-vision",
            "read_on": "2026-09-19",
        },
        "cap_usd": CAP_USD,
        "probes": [],
    }
    committed = 0.0

    # Three sizes establish the three things the bound depends on: the patch
    # arithmetic, the per-dimension rounding, and the budget cap itself.
    for label, (width, height) in (
        ("under budget, square", (512, 512)),
        ("under budget, rectangular — per-dimension rounding", (1024, 768)),
        ("over budget — the cap the reservation relies on", (2048, 2048)),
    ):
        payload = chequerboard(width, height)
        admitted = admit_image(payload)
        forecast = predict(admitted.width, admitted.height)
        # The text side, bounded the way the budget module bounds it.
        text_tokens = len(PROMPT.encode("utf-8")) + 8
        predicted_in = forecast["predicted_image_tokens"] + text_tokens
        predicted_cost = (
            predicted_in * config.cost_per_mtok_in_usd
            + MAX_OUTPUT_TOKENS * config.cost_per_mtok_out_usd
        ) / 1_000_000
        projected = committed + predicted_cost

        before = {
            "label": label,
            "image": {
                "description": "navy field with a white square in the upper-left quarter",
                "sha256": admitted.sha256,
                "byte_size": admitted.byte_size,
                "media_type": admitted.media_type,
                "declared_dimensions": [width, height],
                "decoded_dimensions": [admitted.width, admitted.height],
            },
            "derived_representation": None,
            "transmitted": "the admitted original, unchanged",
            "prediction": forecast,
            "predicted_text_input_tokens_bound": text_tokens,
            "predicted_total_input_tokens": predicted_in,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "predicted_cost_usd": round(predicted_cost, 6),
            "cumulative_projected_spend_usd": round(projected, 6),
        }
        print(json.dumps(before, indent=1))
        if projected > CAP_USD:
            before["stopped"] = "the next call would take the sequence past the cap"
            record["probes"].append(before)
            record["stop"] = before["stopped"]
            out.write_text(json.dumps(record, indent=1))
            print("STOP:", before["stopped"])
            return 4

        response = client.responses.create(
            model=config.model_identifier,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": PROMPT},
                        {
                            "type": "input_image",
                            "detail": DETAIL,
                            "image_url": (
                                f"data:{admitted.media_type};base64,"
                                + b64encode(admitted.content).decode()
                            ),
                        },
                    ],
                }
            ],
            max_output_tokens=MAX_OUTPUT_TOKENS,
            store=False,
        )
        usage = response.usage
        if usage is None:
            raise RuntimeError("the provider returned no usage; nothing can be reconciled")
        details = getattr(usage, "input_tokens_details", None)
        actual_in, actual_out = usage.input_tokens, usage.output_tokens
        actual_cost = (
            actual_in * config.cost_per_mtok_in_usd + actual_out * config.cost_per_mtok_out_usd
        ) / 1_000_000
        committed += actual_cost
        text = (response.output_text or "").strip()

        after = {
            **before,
            "returned_usage": {
                "input_tokens": actual_in,
                "output_tokens": actual_out,
                "input_tokens_details": (
                    details.model_dump() if hasattr(details, "model_dump") else None
                ),
                "cached_tokens": getattr(details, "cached_tokens", None),
            },
            "actual_cost_usd": round(actual_cost, 6),
            "cumulative_actual_spend_usd": round(committed, 6),
            "status": response.status,
            "visible_answer": text,
            # The reconciliation the ruling asks for: the image side is what the
            # total input is, less the text the same request would have sent.
            "implied_image_tokens": actual_in - text_tokens,
            "prediction_minus_implied": forecast["predicted_image_tokens"]
            - (actual_in - text_tokens),
        }
        record["probes"].append(after)
        print(
            f"  -> input {actual_in}, output {actual_out}, ${actual_cost:.6f}; "
            f"predicted image tokens {forecast['predicted_image_tokens']}, "
            f"implied {after['implied_image_tokens']}; answer {text!r}"
        )

    record["total_actual_spend_usd"] = round(committed, 6)
    record["finished_at"] = datetime.now(UTC).isoformat()
    out.write_text(json.dumps(record, indent=1))
    print(f"\ntotal actual spend: ${committed:.6f} of the ${CAP_USD:.2f} cap -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
