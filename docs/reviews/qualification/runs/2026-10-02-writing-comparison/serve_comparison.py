"""The scratch service for the blind writing comparison — 2 October 2026 (owner authorisation).

The same application launchd runs (`val_api.main.build`), on the scratch store (`val_test`,
rebuilt empty) and port 8766, as the earlier benches. `VAL_COMPARE` names the model that
carries **typed** turns in this process:

- `gptoss`: production's own Partner route, GPT-OSS at MEDIUM with its established
  settings, addressed as a second instance of the same model path (`val-exp-prod`), as the
  typed-cache bench did. The Voice candidate stays NOT_ADMITTED.
- `gemma`: the exact registry entry qualified for Voice (`gemma-4-26b-a4b-q4km-llamacpp-voice`,
  the pinned Q4_K_M artifact, thinking off, its own sampling), promoted in this process
  only to the Partner profile — **routable**, not pin-only — while every LM Studio
  configuration loses the Partner profile, so Val Core's ordinary typed route resolves to
  Gemma and nothing in this process can address GPT-OSS. The llama.cpp server is started
  by the service's own supervisor, as for Voice.

Everything else is Core's typed path unchanged: the persona whole, the record-state
envelope, conversation guidance, the output allowance (`CONVERSATION_MAX_OUTPUT_TOKENS`),
the typed prime (`VAL_TYPED_PRIME=on` in both runs, so cache preparation is equivalent).
No Voice session is opened. Only this process's registry changes; nothing on disk does.
Production's environment is read from its launchd definition and nothing from it is printed.
"""

from __future__ import annotations

import logging
import os
import plistlib
import sys
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        if name != "VAL_DATABASE_URL":
            os.environ[name] = value

ROOT = Path(__file__).resolve().parents[5]
URL = "postgresql+psycopg://localhost:5433/val_test"
PORT = 8766
os.environ["VAL_DATABASE_URL"] = URL
os.environ["VAL_PORT"] = str(PORT)
os.environ.pop("VAL_VOICE_MODEL", None)  # no Voice in this comparison

import uvicorn  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

import val_domain.registry as registry  # noqa: E402
from val_api.main import build, loopback_sockets  # noqa: E402
from val_domain.gateway import Admission, CapabilityProfile  # noqa: E402
from val_gateway.persona import seed  # noqa: E402

COMPARE = os.environ["VAL_COMPARE"]
assert COMPARE in ("gptoss", "gemma"), COMPARE
GEMMA = "gemma-4-26b-a4b-q4km-llamacpp-voice"

PRODUCTION_IDENTIFIER = "openai/gpt-oss-20b"
EXPERIMENT = os.environ.get("VAL_EXPERIMENT_MODEL_IDENTIFIER", "val-exp-prod")
assert EXPERIMENT != PRODUCTION_IDENTIFIER, "the experiment never addresses production's model"
registry.REGISTRY = tuple(
    config.model_copy(update={"model_identifier": EXPERIMENT})
    if config.model_identifier == PRODUCTION_IDENTIFIER
    else config
    for config in registry.REGISTRY
)
assert not any(c.model_identifier == PRODUCTION_IDENTIFIER for c in registry.REGISTRY)

if COMPARE == "gemma":
    entry = registry.by_slug(GEMMA)
    assert entry is not None, GEMMA
    promoted = entry.model_copy(
        update={
            "admission": Admission.PROVISIONALLY_ADMITTED,
            "capability_profiles": frozenset({CapabilityProfile.PARTNER}),
            "qualification_targets": frozenset(),
        }
    )

    def _typed_only(config):  # noqa: ANN001, ANN202
        if config.slug == GEMMA:
            return promoted
        if (
            config.provider == "lmstudio"
            and CapabilityProfile.PARTNER in config.capability_profiles
        ):
            return config.model_copy(
                update={
                    "capability_profiles": config.capability_profiles - {CapabilityProfile.PARTNER}
                }
            )
        return config

    registry.REGISTRY = tuple(_typed_only(c) for c in registry.REGISTRY)
    assert GEMMA not in registry.PIN_ONLY
    partners = [
        c.slug
        for c in registry.active()
        if CapabilityProfile.PARTNER in c.capability_profiles
        and c.provider in ("lmstudio", "llamacpp")
    ]
    assert partners == [GEMMA], partners

EXPERIMENT_KEY = os.environ.get("VAL_EXPERIMENT_MODEL_KEY")
if EXPERIMENT_KEY and COMPARE == "gptoss":
    import val_providers.lmstudio_runtime as _runtime

    _original_load = _runtime.LMStudioRuntime._load

    def _load_experiment(self, model_identifier, context_tokens):  # noqa: ANN001
        if model_identifier != EXPERIMENT:
            return _original_load(self, model_identifier, context_tokens)
        code, output = self._runner.run(
            [
                str(self._lms),
                "load",
                EXPERIMENT_KEY,
                "--identifier",
                EXPERIMENT,
                "--context-length",
                str(context_tokens),
                "--ttl",
                str(_runtime.IDLE_TTL_SECONDS),
                "--parallel",
                str(_runtime.SERVING_PARALLEL),
                "--yes",
            ],
            timeout=_runtime.LOAD_TIMEOUT_SECONDS,
        )
        if code != 0:
            raise _runtime.LocalRuntimeUnavailableError(
                f"{EXPERIMENT} ({EXPERIMENT_KEY}) could not be loaded: {output or 'no output'}"
            )

    _runtime.LMStudioRuntime._load = _load_experiment  # type: ignore[method-assign]


def fresh_store() -> None:
    engine = create_engine(URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "packages/domain/migrations"))
    config.set_main_option("sqlalchemy.url", URL)
    command.upgrade(config, "head")
    engine = create_engine(URL)
    seed(engine, ROOT)
    engine.dispose()


if __name__ == "__main__":
    fresh_store()
    for logger in logging.Logger.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            logger.disabled = False
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(created).3f %(levelname)s:%(name)s:%(message)s",
    )
    app, _ = build()
    uvicorn.Server(uvicorn.Config(app, port=PORT, log_level="info")).run(
        sockets=loopback_sockets(PORT)
    )
