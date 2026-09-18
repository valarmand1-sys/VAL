"""The orthogonal thinking declaration and the extra sampling fields — ruling of 18 September 2026.

A binary thinking switch is not a graded reasoning effort: `thinking_enabled`
says ON, OFF, or "this model has no such contract" (`None`), never "whatever the
runtime's UI is set to". `preserve_thinking` speaks only about a switch that
exists and is never `True` — hidden reasoning is not replayed into history.
`top_p` and `top_k` are verbatim upstream sampling values.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from val_domain.gateway import ModelConfig
from val_domain.registry import REGISTRY, by_slug


def _base() -> dict[str, object]:
    config = by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio")
    assert config is not None
    return config.model_dump()


def test_every_field_defaults_to_not_declared() -> None:
    config = ModelConfig(**_base())  # type: ignore[arg-type]
    assert config.thinking_enabled is None and config.preserve_thinking is None
    assert config.top_p is None and config.top_k is None


def test_on_off_and_not_applicable_are_three_distinct_declarations() -> None:
    on = ModelConfig(**{**_base(), "thinking_enabled": True, "preserve_thinking": False})  # type: ignore[arg-type]
    off = ModelConfig(**{**_base(), "thinking_enabled": False, "preserve_thinking": False})  # type: ignore[arg-type]
    assert on.thinking_enabled is True and off.thinking_enabled is False
    assert on.preserve_thinking is False and off.preserve_thinking is False


def test_preserve_thinking_without_a_declared_switch_is_refused() -> None:
    with pytest.raises(ValidationError, match="declared without thinking_enabled"):
        ModelConfig(**{**_base(), "preserve_thinking": False})  # type: ignore[arg-type]


def test_preserve_thinking_true_is_never_legal() -> None:
    with pytest.raises(ValidationError, match="replay hidden reasoning"):
        ModelConfig(**{**_base(), "thinking_enabled": True, "preserve_thinking": True})  # type: ignore[arg-type]


def test_sampling_values_are_bounded_and_otherwise_verbatim() -> None:
    config = ModelConfig(**{**_base(), "top_p": 0.95, "top_k": 64})  # type: ignore[arg-type]
    assert config.top_p == 0.95 and config.top_k == 64
    for bad in ({"top_p": 0.0}, {"top_p": 1.5}, {"top_k": 0}):
        with pytest.raises(ValidationError):
            ModelConfig(**{**_base(), **bad})  # type: ignore[arg-type]


def test_only_llamacpp_entries_declare_these_fields_and_every_other_entry_is_unchanged() -> None:
    for config in REGISTRY:
        if config.provider == "llamacpp":
            continue
        assert config.thinking_enabled is None, config.slug
        assert config.preserve_thinking is None, config.slug
        assert config.top_p is None and config.top_k is None, config.slug
