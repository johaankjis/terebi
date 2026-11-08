"""Small, profile-local Hermes tool handlers."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .hermes_screen.config import Config
from .hermes_screen.errors import error_payload


def library_status(
    args: dict,
    *,
    ctx: Any = None,
    secret_reader: Callable[[str], str | None] | None = None,
) -> str:
    """Read settings per call and return status; never expose exception text."""
    if ctx is None:
        return json.dumps(error_payload("not_configured", "Reload the Hermes Screen plugin."))
    try:
        config = Config(ctx, secret_reader=secret_reader)
        base_url = config.jellyfin_url()
        api_key = config.jellyfin_api_key()
        user_id = config.jellyfin_user()
    except Exception:
        return json.dumps(
            error_payload(
                "jellyfin_config",
                "Could not read settings. Check the plugin settings and secret scope.",
            )
        )
    if not base_url or not api_key:
        return json.dumps(
            error_payload(
                "not_configured",
                "Set jellyfin_url and the JELLYFIN_API_KEY secret in plugin settings.",
            )
        )
    try:
        from .hermes_screen.jellyfin import JellyfinClient, JellyfinError
    except Exception:
        return json.dumps(
            error_payload(
                "jellyfin_client_unavailable", "Reinstall Hermes Screen with its httpx dependency."
            )
        )
    try:
        with JellyfinClient(base_url, api_key, user_id=user_id) as client:
            result = client.status()
        return json.dumps(result)
    except JellyfinError as exc:
        return json.dumps(exc.to_dict())
    except Exception:
        return json.dumps(
            error_payload(
                "jellyfin_unreachable",
                "Could not read Jellyfin status. Check the server and settings.",
            )
        )
