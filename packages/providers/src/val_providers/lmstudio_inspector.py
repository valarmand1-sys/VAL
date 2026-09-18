"""The LM Studio runtime/context inspector — read-only, by ruling (16 September 2026).

The house's inference transport to LM Studio is the OpenAI-compatible HTTP
adapter (`lmstudio_adapter`). This module is the *other* thing the ruling of
16 September 2026 authorised, and nothing more: the official `lmstudio` Python
SDK (pinned `1.6.0b1`, the release that carries API-token authentication) used
as a **read-only measurement instrument** against a model that is **already
loaded**:

- enumerate the already-loaded instances;
- select the intended canonical instance deterministically, or refuse;
- read that instance's own context length and identity facts;
- apply that instance's own prompt template to the exact message structure the
  inference request will carry;
- count the resulting serialisation with that instance's own tokenizer.

It never generates, streams, embeds, loads, unloads, reloads, configures or
retries anything, and it never takes the SDK's "get or load" path
(`client.llm.model(...)`), which would load an absent model. The credential is
the house's one LM Studio token, passed programmatically into a scoped client
and never through the SDK's environment fallback; it is not logged, returned
or recorded.

What the count is: the runtime's own rendering and its own tokenizer, which is
why it may be treated as authoritative — subject to the parity gate the ruling
sets: on every admitted call the count is compared with the server's reported
`usage.prompt_tokens`, and exact agreement is evidence only for the calls that
ran. Known hazards, left to that gate and never compensated for here: the SDK's
`Chat` merges consecutive user messages; the server's reasoning-effort
handling on the OpenAI-compatible path may not be represented by the SDK's
template helper.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

import lmstudio

from val_domain.provider import ContextFeasibility, ContextInspectionUnavailableError

_LOGGER = logging.getLogger("val.providers.lmstudio.inspector")

#: Hosts that are this machine. The inspector refuses any other.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

#: The measurement's name on every evidence row.
SOURCE = "lmstudio-sdk"

#: How the preflight asks the runtime to render (owner ruling, 18 September 2026).
#: LM Studio's chat-completions ingress renders historical assistant turns WITHOUT
#: the template's end-of-sequence token; the template RPC, by default, emits it —
#: one token per assistant message in history (Mistral Small 3.2: `</s>`; the
#: synthetic four-message diagnostic, evidence index §75). The SDK's own documented
#: rendering option makes the RPC render exactly as the ingress does — byte-equal
#: on the diagnostic — so the preflight renders with it. A general rule for every
#: model on this runtime, not a per-template correction: no token is removed by the
#: house, no count is adjusted; the runtime renders both paths the same way.
INGRESS_RENDER_OPTIONS: Mapping[str, bool] = {"omitEosToken": True}


def inspector_host_of(base_url: str) -> str:
    """`host:port` for the SDK, from the adapter's OpenAI-compatible base URL."""
    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{host}:{port}"


def is_loopback_host(api_host: str) -> bool:
    host = api_host.rsplit(":", 1)[0].strip("[]") if ":" in api_host else api_host
    return host in LOOPBACK_HOSTS


class _LoadedHandle(Protocol):
    """The slice of an SDK loaded-model handle the inspector uses. Nothing generative."""

    def get_info(self) -> object: ...
    def get_context_length(self) -> int: ...
    def apply_prompt_template(self, history: object, opts: Mapping[str, bool]) -> str: ...
    def count_tokens(self, input: str) -> int: ...


class _LoadedModels(Protocol):
    def list_loaded(self) -> Sequence[_LoadedHandle]: ...


class _ClientLike(Protocol):
    llm: _LoadedModels

    def close(self) -> None: ...


#: How a client is made — injectable so tests never open a socket.
ClientFactory = Callable[[str, str], _ClientLike]


def _default_client(api_host: str, token: str) -> _ClientLike:
    # The explicit scoped client, the token passed directly: never
    # `configure_default_client`, never the environment fallback.
    return lmstudio.Client(api_host, api_token=token)  # type: ignore[return-value]


@dataclass(frozen=True)
class LoadedInstance:
    """The already-loaded instance the measurement is taken against."""

    identifier: str
    model_key: str
    context_length: int
    max_context_length: int | None
    format: str | None
    architecture: str | None
    path: str | None


class LMStudioContextInspector:
    """Read-only measurement of already-loaded LM Studio instances."""

    def __init__(
        self,
        api_host: str,
        token: str | None,
        *,
        client_factory: ClientFactory = _default_client,
    ) -> None:
        if not is_loopback_host(api_host):
            raise ValueError(
                "lmstudio inspector: the API host must name this machine "
                f"(one of {sorted(LOOPBACK_HOSTS)}); a remote server is not inspected"
            )
        if not token:
            raise ValueError(
                "lmstudio inspector: the local server requires its API token "
                "(VAL_LMSTUDIO_API_TOKEN); the inspector is not constructed without it"
            )
        self._api_host = api_host
        self._token = token
        self._factory = client_factory
        self._client: _ClientLike | None = None
        self.sdk_version = lmstudio.__version__

    # --- session --------------------------------------------------------------------

    def _session(self) -> _ClientLike:
        if self._client is None:
            try:
                self._client = self._factory(self._api_host, self._token)
            except Exception as error:
                raise ContextInspectionUnavailableError(
                    f"lmstudio inspector: the runtime session could not be opened at "
                    f"{self._api_host}: {type(error).__name__}"
                ) from error
        return self._client

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    # --- loaded-instance selection ----------------------------------------------------

    def loaded_instance(self, model_identifier: str) -> tuple[LoadedInstance, _LoadedHandle]:
        """Exactly one already-loaded instance whose identifier is the requested one.

        Zero matches, more than one match, an identity that cannot be read, or
        a missing context length all refuse. Only `list_loaded` is consulted:
        nothing here can cause a load.
        """
        try:
            handles = list(self._session().llm.list_loaded())
        except ContextInspectionUnavailableError:
            raise
        except Exception as error:
            raise ContextInspectionUnavailableError(
                f"lmstudio inspector: could not enumerate loaded models: {type(error).__name__}"
            ) from error
        matches: list[tuple[LoadedInstance, _LoadedHandle]] = []
        for handle in handles:
            try:
                info = handle.get_info()
                identifier = str(getattr(info, "identifier", ""))
                model_key = str(getattr(info, "model_key", ""))
            except Exception as error:
                raise ContextInspectionUnavailableError(
                    "lmstudio inspector: a loaded model's identity could not be read: "
                    f"{type(error).__name__}"
                ) from error
            if identifier != model_identifier and model_key != model_identifier:
                continue
            context_length = getattr(info, "context_length", None)
            if not isinstance(context_length, int) or context_length <= 0:
                raise ContextInspectionUnavailableError(
                    f"lmstudio inspector: loaded instance {identifier!r} reports no context length"
                )
            matches.append(
                (
                    LoadedInstance(
                        identifier=identifier,
                        model_key=model_key,
                        context_length=context_length,
                        max_context_length=(
                            getattr(info, "max_context_length", None)
                            if isinstance(getattr(info, "max_context_length", None), int)
                            else None
                        ),
                        format=_optional_str(getattr(info, "format", None)),
                        architecture=_optional_str(getattr(info, "architecture", None)),
                        path=_optional_str(getattr(info, "path", None)),
                    ),
                    handle,
                )
            )
        if not matches:
            raise ContextInspectionUnavailableError(
                f"lmstudio inspector: no loaded instance is {model_identifier!r}; the model is "
                "not resident and the inspector never loads one"
            )
        if len(matches) > 1:
            raise ContextInspectionUnavailableError(
                f"lmstudio inspector: {len(matches)} loaded instances answer to "
                f"{model_identifier!r}; the intended instance cannot be chosen unambiguously"
            )
        return matches[0]

    # --- measurement -----------------------------------------------------------------

    def measure(
        self, model_identifier: str, turns: Sequence[Mapping[str, str]]
    ) -> ContextFeasibility:
        """The exact serialised prompt of `turns` against the loaded instance's window.

        `turns` is the chat-completion message list the adapter will transmit
        (`role` / `content`, in order). It is placed into the SDK's `Chat`
        through its supported entry points — system prompt, user message,
        assistant response — with no separators, splits, merges or offsets of
        this module's own; the runtime's template and tokenizer do the rest.
        """
        instance, handle = self.loaded_instance(model_identifier)
        try:
            chat = lmstudio.Chat()
            for turn in turns:
                role, content = turn["role"], turn["content"]
                if role == "system":
                    chat.add_system_prompt(content)
                elif role == "user":
                    chat.add_user_message(content)
                elif role == "assistant":
                    chat.add_assistant_response(content)
                else:
                    raise ContextInspectionUnavailableError(
                        f"lmstudio inspector: unsupported role {role!r} in the request"
                    )
            rendered = handle.apply_prompt_template(chat, dict(INGRESS_RENDER_OPTIONS))
            prompt_tokens = handle.count_tokens(rendered)
            context_tokens = handle.get_context_length()
        except ContextInspectionUnavailableError:
            raise
        except Exception as error:
            raise ContextInspectionUnavailableError(
                f"lmstudio inspector: the runtime refused the measurement: {type(error).__name__}"
            ) from error
        if not isinstance(prompt_tokens, int) or prompt_tokens <= 0:
            raise ContextInspectionUnavailableError(
                "lmstudio inspector: the runtime returned no usable token count"
            )
        if not isinstance(context_tokens, int) or context_tokens <= 0:
            raise ContextInspectionUnavailableError(
                "lmstudio inspector: the runtime returned no usable context length"
            )
        return ContextFeasibility(
            prompt_tokens=prompt_tokens,
            context_tokens=context_tokens,
            source=SOURCE,
            details={
                "sdk_version": self.sdk_version,
                "api_host": self._api_host,
                "instance_identifier": instance.identifier,
                "model_key": instance.model_key,
                "loaded_context_length": instance.context_length,
                "max_context_length": instance.max_context_length,
                "format": instance.format,
                "architecture": instance.architecture,
                "path": instance.path,
                "rendered_chars": len(rendered),
                "render_options": dict(INGRESS_RENDER_OPTIONS),
                "turns": len(turns),
            },
        )


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)
