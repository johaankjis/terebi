"""Configuration and secret access for Hermes Screen.

Settings are read through the Hermes plugin context (``ctx.get_config``).
Secrets are read ONLY through Hermes's secret scope (``agent.secret_scope.get_secret``),
never from ``.env`` files or raw ``os.environ``. A ``secret_reader`` callable may be
injected for tests.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class Config:
    """Thin accessor over a Hermes plugin context plus a secret reader."""

    def __init__(
        self,
        ctx: Any,
        secret_reader: Callable[[str], str | None] | None = None,
    ) -> None:
        self.ctx = ctx
        self._secret_reader = secret_reader if secret_reader is not None else _default_secret_reader

    # -- Jellyfin -----------------------------------------------------------
    def _clean(self, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Settings must be text.")
        value = value.strip()
        return value if value else None

    def jellyfin_url(self) -> str | None:
        return self._clean(self.ctx.get_config("jellyfin_url", default=None))

    def jellyfin_api_key(self) -> str | None:
        return self._clean(self._secret_reader("JELLYFIN_API_KEY"))

    def jellyfin_user(self) -> str | None:
        return self._clean(self.ctx.get_config("jellyfin_user", default=None))

    def is_jellyfin_configured(self) -> bool:
        return bool(self.jellyfin_url() and self.jellyfin_api_key())

    # -- Chromecast -----------------------------------------------------------
    def chromecast_host(self) -> str | None:
        return self._clean(self.ctx.get_config("chromecast_host", default=None))

    def cast_media_base_url(self) -> str | None:
        return self._clean(self.ctx.get_config("cast_media_base_url", default=None))

    def cast_relay_bind(self) -> str | None:
        return self._clean(self.ctx.get_config("cast_relay_bind", default=None))

    # -- Roku ---------------------------------------------------------------
    def roku_ip(self) -> str | None:
        return self._clean(self.ctx.get_config("roku_ip", default=None))

    def default_room(self) -> str:
        value = self._clean(self.ctx.get_config("default_room", default="living room"))
        return value if value else "living room"


def _default_secret_reader(name: str) -> str | None:
    """Production secret reader: Hermes's sanctioned secret scope."""
    from agent.secret_scope import get_secret

    return get_secret(name)
