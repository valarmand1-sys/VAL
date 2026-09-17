"""The local context inequality — ruling of 16 September 2026 — beside the untouched byte bound."""

from __future__ import annotations

from val_domain.registry import by_slug
from val_policy.budget import limit_overrun, local_context_overrun, raw_input_bound


def _local() -> object:
    config = by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio")
    assert config is not None
    return config


def _sol() -> object:
    config = by_slug("gpt-5-6-sol-medium")
    assert config is not None
    return config


def test_the_inequality_is_exact_prompt_plus_the_whole_output_reserve_against_the_runtime() -> None:
    local = _local()
    assert local_context_overrun(local, 26_624, 32_768, 6_144) is None  # type: ignore[arg-type]
    refused = local_context_overrun(local, 26_625, 32_768, 6_144)  # type: ignore[arg-type]
    assert refused is not None
    assert "26,625" in refused and "6,144" in refused and "32,768" in refused
    assert "reasoning and visible text together" in refused
    assert "nothing was shortened" in refused.lower()


def test_the_runtime_window_governs_not_the_registry_nominal() -> None:
    local = _local()
    assert local.context_window_tokens == 32_768  # type: ignore[attr-type]
    # registry 32,768, runtime 8,192: the same 5,417-token prompt is refused
    assert local_context_overrun(local, 5_417, 8_192, 6_144) is not None  # type: ignore[arg-type]
    # registry 32,768, runtime 32,768: admitted
    assert local_context_overrun(local, 5_417, 32_768, 6_144) is None  # type: ignore[arg-type]


def test_the_output_cap_is_still_refused_not_clamped() -> None:
    local = _local()
    refused = local_context_overrun(local, 100, 32_768, 16_385)  # type: ignore[arg-type]
    assert refused is not None and "Refused rather than clamped" in refused


def test_the_cloud_byte_bound_is_untouched() -> None:
    parts = ("persona " * 3_000, "history " * 3_000)
    assert raw_input_bound(parts) == sum(len(p.encode()) for p in parts) + 8 * len(parts)
    assert limit_overrun(_sol(), parts, 6_144) is None  # type: ignore[arg-type]
    huge = ("x" * 1_100_000,)
    refused = limit_overrun(_sol(), huge, 6_144)  # type: ignore[arg-type]
    assert refused is not None and "input bound" in refused
