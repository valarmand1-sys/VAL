"""Evaluation-only entries — ruling, 10 September 2026.

`NOT_ADMITTED` with no capability profile: present so history resolves and
the gateway's evaluation door can reach them; absent from `active()`, and so
from routing, cost ranking, liveness and the startup description of the
serving registry. Designation is a recorded ruling that edits the entry.
"""

from __future__ import annotations

from datetime import date

from val_domain.gateway import Admission, ReasoningEffort
from val_domain.registry import (
    REGISTRY,
    active,
    by_id,
    by_slug,
    cheapest,
    declared_chain_violations,
    under_evaluation,
    unproven_routes,
)

CANDIDATES = {"sonnet-5-medium", "sonnet-5-low", "gpt-5-6-terra", "gpt-5-6-luna"}


def test_evaluation_entries_are_registered_and_excluded_from_the_serving_registry() -> None:
    assert {config.slug for config in under_evaluation()} == CANDIDATES
    assert not {config.slug for config in active()} & CANDIDATES
    assert not {config.slug for config in unproven_routes()} & CANDIDATES
    assert cheapest().slug not in CANDIDATES, "Luna is the cheapest entry and is not a route"
    for config in under_evaluation():
        assert config.admission is Admission.NOT_ADMITTED
        assert config.capability_profiles == frozenset()
        assert config.fallback_slug is None
        assert by_id(config.id) is config and by_slug(config.slug) is config
        assert config.activated_on == config.rates_verified_on == date(2026, 9, 10)


def test_active_and_under_evaluation_partition_the_unretired_registry() -> None:
    unretired = {config.slug for config in REGISTRY if not config.retired}
    assert {c.slug for c in active()} | {c.slug for c in under_evaluation()} == unretired
    assert not {c.slug for c in active()} & {c.slug for c in under_evaluation()}


def test_evaluation_entries_do_not_disturb_the_declared_chains() -> None:
    assert declared_chain_violations(active()) == []
    assert declared_chain_violations(REGISTRY) == []


def test_the_openai_candidates_state_effort_none_as_documented() -> None:
    """developers.openai.com model pages, read 10 September 2026: `none` … `max`."""
    for slug in ("gpt-5-6-terra", "gpt-5-6-luna"):
        config = by_slug(slug)
        assert config is not None
        assert config.reasoning_effort is ReasoningEffort.NONE
        assert config.long_context_threshold_tokens == 272_000
        assert (config.long_context_in_multiplier, config.long_context_out_multiplier) == (2.0, 1.5)


def test_the_sonnet_candidates_differ_from_the_registered_route_only_in_effort() -> None:
    high = by_slug("sonnet-5")
    assert high is not None
    for slug, effort in (
        ("sonnet-5-medium", ReasoningEffort.MEDIUM),
        ("sonnet-5-low", ReasoningEffort.LOW),
    ):
        candidate = by_slug(slug)
        assert candidate is not None
        assert candidate.reasoning_effort is effort
        assert candidate.model_identifier == high.model_identifier
        assert (candidate.cost_per_mtok_in_usd, candidate.cost_per_mtok_out_usd) == (
            high.cost_per_mtok_in_usd,
            high.cost_per_mtok_out_usd,
        )
