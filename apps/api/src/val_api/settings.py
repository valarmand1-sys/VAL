"""Service configuration — WP-0.10.

Read from the environment, never from a literal. The database URL names the
authoritative store; provider keys are read by `val_gateway.startup`, not
here, so this module cannot become a second place credentials live.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """What the service needs to run, and nothing it does not."""

    model_config = SettingsConfigDict(env_prefix="VAL_")

    #: The authoritative store. `VAL_DATABASE_URL`.
    database_url: str
    #: Where the service listens. Loopback only: the desktop shell is on the
    #: same machine, and Layer 0 exposes nothing beyond it.
    host: str = "127.0.0.1"
    port: int = 8756
