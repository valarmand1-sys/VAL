"""The candidate lane cannot be reached from the service — ruling, 14 September 2026.

No HTTP contract names a configuration or a candidate; the application is
built on a plain `Gateway`; the live wiring constructs the same.
"""

from __future__ import annotations

import inspect

from val_api import contracts, main
from val_gateway.candidate import CandidateGateway
from val_gateway.gateway import Gateway


def test_no_turn_contract_exposes_configuration_or_candidate_selection() -> None:
    forbidden = {"configuration", "candidate", "model", "slug", "model_config_id", "route"}
    for name, model in inspect.getmembers(contracts, inspect.isclass):
        fields = getattr(model, "model_fields", None)
        if fields is None or "Request" not in name:
            continue
        assert not (set(fields) & forbidden), f"{name} exposes {set(fields) & forbidden}"


def test_the_live_wiring_never_constructs_a_candidate_gateway() -> None:
    source = inspect.getsource(main)
    assert "CandidateGateway" not in source
    assert "candidate" not in source.lower()
    assert issubclass(CandidateGateway, Gateway), "a subtype, constructed only by its factory"
