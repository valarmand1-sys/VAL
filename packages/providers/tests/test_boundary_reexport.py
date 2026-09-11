"""`val_providers.base` re-exports the domain boundary unchanged — Val Core Phase 1.

Every existing import of `ProviderResult` or `ProviderAdapter` from the
providers package resolves to the domain's own object; nothing moved for a
caller, and the providers package speaks the core's terms rather than its own.
"""

from __future__ import annotations

from val_domain import provider as boundary
from val_providers import base


def test_the_providers_package_re_exports_the_domain_boundary_unchanged() -> None:
    assert base.ProviderResult is boundary.ProviderResult
    assert base.ProviderAdapter is boundary.ProviderAdapter
    assert base.StreamingProviderAdapter is boundary.StreamingProviderAdapter
    assert base.TextDelta is boundary.TextDelta
    assert base.ProviderEvent == boundary.ProviderEvent
    assert base.DeltaSink == boundary.DeltaSink
    assert base.supports_streaming is boundary.supports_streaming


def test_every_registered_provider_adapter_speaks_the_boundary() -> None:
    from val_providers.anthropic_adapter import AnthropicAdapter
    from val_providers.openai_adapter import OpenAIAdapter

    for adapter_type in (AnthropicAdapter, OpenAIAdapter):
        assert callable(getattr(adapter_type, "complete", None)), adapter_type
    assert boundary.supports_streaming(AnthropicAdapter.__new__(AnthropicAdapter))
    # OpenAI streaming is the second-provider step, not Phase 1: declared absent, not assumed.
    assert not boundary.supports_streaming(OpenAIAdapter.__new__(OpenAIAdapter))
