"""Cache-boundary metadata is not prompt content — 14 September 2026.

The `cache_breakpoint` flag on a message changes what an adapter sends as
cache-control metadata and nothing else: the content parts the gateway
routes, bounds and scans are identical with and without it.
"""

from __future__ import annotations

from val_domain.gateway import Classification, GatewayRequest, Message, TaskType
from val_domain.project import ProjectAttribution
from val_gateway.gateway import content_parts


def test_the_breakpoint_is_metadata_not_prompt_content() -> None:
    from val_domain.gateway import GatewayRequest

    def request(flagged: bool) -> GatewayRequest:
        return GatewayRequest(
            task_type=TaskType.CLASSIFICATION,
            classification=Classification.PROTECTED,
            messages=(Message(role="user", content="x", cache_breakpoint=flagged),),
            output_schema={"type": "object"},
            project_id=None,
            project_attribution=ProjectAttribution.EXPLICIT_NONE,
        )

    assert content_parts(request(True)) == content_parts(request(False)), (
        "what leaves the machine, and therefore what routing and the bound see, is identical"
    )
