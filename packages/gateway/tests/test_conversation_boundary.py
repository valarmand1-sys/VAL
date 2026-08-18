"""There is one provider-bearing conversation path — WP-0.7 corrective round.

Independent review of `VAL_Source_Snapshot_d137925.zip` found that WP-0.7's
persistence guarantee held only for callers of `val_gateway.loop.send`. The
older `val_gateway.exchange.exchange()` still called `gateway.converse()`
directly, so a caller who picked it got a real `TaskType.CONVERSATION` provider
call with no conversation created, no message persisted, and no durable
provenance — the whole work package bypassed by choosing the older of two
functions that both looked like the front door.

**These are source and dependency assertions, not behaviour tests.** A test that
calls `loop.send` and observes rows proves that `send` persists; it cannot prove
that nothing *else* can hold a conversation without persisting. That is a claim
about the shape of the application, so it is checked against the shape: which
modules may reach a provider, and what the surviving module can still do.

Behaviour tests for the loop itself live in `test_conversation_memory.py`.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from val_gateway import exchange as exchange_module

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "val_gateway"

#: The only module that may hand a conversation to a provider. Everything else
#: in `val_gateway` either does not reach the gateway at all, or reaches it for
#: work that is not conversation.
THE_CONVERSATION_BOUNDARY = "loop.py"

#: How a provider call is actually initiated. `converse` assembles the persona
#: and is the conversation entrance; `complete` and `complete_with_configuration`
#: are the lower-level entrances the gateway itself and non-conversation work use.
PROVIDER_ENTRANCES = frozenset({"converse"})


def _module_sources() -> dict[str, str]:
    return {path.name: path.read_text() for path in sorted(SOURCE_ROOT.glob("*.py"))}


def _calls_in(source: str) -> set[str]:
    """Every attribute call made in a module, by attribute name."""
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            found.add(node.func.attr)
    return found


def test_only_the_loop_initiates_conversation_inference() -> None:
    """§1A. `converse` is called from exactly one place in the application.

    This is the assertion the review asked for. If a second module ever calls
    `converse`, that module is a second conversation boundary whether or not it
    was meant to be one, and this fails the moment it is written rather than the
    moment somebody notices a conversation left no record.
    """
    callers = {
        name: _calls_in(source) & PROVIDER_ENTRANCES for name, source in _module_sources().items()
    }
    reaching = sorted(name for name, entrances in callers.items() if entrances)

    assert reaching == [THE_CONVERSATION_BOUNDARY], (
        f"{reaching} initiate conversation inference. Exactly one module may: "
        "a second path is a way to hold a conversation that leaves no record, "
        "which is what the retired `exchange()` was."
    )


def test_the_scope_resolution_module_cannot_reach_a_provider() -> None:
    """§1B. `exchange.py` keeps its deterministic helpers and loses its teeth.

    It may still resolve scope and produce a clarification. It may not import a
    `Gateway`, so it cannot acquire the ability to call one without that import
    appearing in a diff.
    """
    source = (SOURCE_ROOT / "exchange.py").read_text()
    tree = ast.parse(source)

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    assert "val_gateway.gateway" not in imported, (
        "the scope-resolution module imports the gateway again. It has no reason "
        "to unless it is about to become a second conversation boundary."
    )
    assert not (_calls_in(source) & PROVIDER_ENTRANCES)


def test_the_retired_function_is_gone_rather_than_deprecated() -> None:
    """§1C. Not kept "for compatibility".

    The compatibility on offer was the ability to hold a conversation that left
    no record, so there was nothing worth preserving. A shim that still reached a
    provider would have been the same defect wearing a deprecation warning.
    """
    assert not hasattr(exchange_module, "exchange")

    # What it kept is what was always deterministic and provider-free.
    assert hasattr(exchange_module, "resolve_scope")
    assert hasattr(exchange_module, "ClarificationNeeded")
    assert hasattr(exchange_module, "RestrictedContentRefusedError")


def test_the_surviving_helpers_take_no_gateway() -> None:
    """The helpers cannot be handed a provider even by a determined caller."""
    signature = inspect.signature(exchange_module.resolve_scope)
    annotations = {str(p.annotation) for p in signature.parameters.values()}

    assert not any("Gateway" in annotation for annotation in annotations)


@pytest.mark.parametrize(
    "module",
    ["exchange.py", "conversations.py", "memory.py", "context.py", "projects.py"],
)
def test_no_supporting_module_initiates_conversation_inference(module: str) -> None:
    """Each module that WP-0.7 touches, named individually.

    Parameterised so a failure names the module that acquired the capability,
    rather than reporting that the set changed.
    """
    source = (SOURCE_ROOT / module).read_text()

    assert not (_calls_in(source) & PROVIDER_ENTRANCES)
