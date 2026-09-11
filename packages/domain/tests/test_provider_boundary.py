"""The provider-neutral boundary lives in the domain — Val Core Phase 1, 11 September 2026.

The core depends on `val_domain.provider`; the providers package re-exports the
same objects so no existing import moved. Streaming is a declared capability,
never inferred.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from val_domain.gateway import CacheTtl, Message, ModelConfig, TerminalState
from val_domain.provider import (
    DeltaSink,
    ProviderEvent,
    ProviderResult,
    StreamingProviderAdapter,
    TextDelta,
    supports_streaming,
)


class _Completing:
    name = "completing"

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> ProviderResult:
        return ProviderResult("done", TerminalState.COMPLETE, 1, 1, "r")


class _Streaming(_Completing):
    name = "streaming"

    def stream(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> Iterator[ProviderEvent]:
        yield TextDelta("do")
        yield TextDelta("ne")
        yield ProviderResult("done", TerminalState.COMPLETE, 1, 1, "r")


def test_streaming_is_declared_by_implementing_stream_never_inferred() -> None:
    assert not supports_streaming(_Completing())
    assert supports_streaming(_Streaming())
    assert isinstance(_Streaming(), StreamingProviderAdapter)
    assert not isinstance(_Completing(), StreamingProviderAdapter)


def test_a_streamed_call_ends_in_the_same_result_a_completion_returns() -> None:
    events = list(_Streaming().stream(None, (), None, 10))  # type: ignore[arg-type]
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["do", "ne"]
    assert isinstance(events[-1], ProviderResult)
    assert events[-1] == _Completing().complete(None, (), None, 10)  # type: ignore[arg-type]
    assert "".join(e.text for e in events[:-1] if isinstance(e, TextDelta)) == events[-1].text


def test_the_boundary_types_carry_no_sdk_vocabulary() -> None:
    """The domain module imports nothing from any provider SDK or package."""
    import ast

    import val_domain.provider as boundary

    tree = ast.parse(open(boundary.__file__, encoding="utf-8").read())
    imported = [
        name.name if isinstance(node, ast.Import) else (node.module or "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for name in (node.names if isinstance(node, ast.Import) else [None])
    ]
    assert imported, "the module has imports to check"
    for module in imported:
        top = module.split(".")[0]
        assert top not in ("anthropic", "openai", "val_providers"), module
        assert top in ("__future__", "collections", "dataclasses", "typing", "val_domain"), module
    sink: DeltaSink = lambda text: None  # noqa: E731 - the type is the point
    sink("ok")
