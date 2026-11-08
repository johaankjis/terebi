"""Tool handlers — thin handlers for Hermes Screen."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from hermes_screen.config import Config
from hermes_screen.errors import error_payload

# Bound during register(); overridable per call through kwargs for tests.
_CTX: Any = None
_CLIENT_FACTORY: Callable[..., Any] | None = None


def bind_context(ctx: Any) -> None:
    """Bind the Hermes plugin context for handler use."""
    global _CTX
    _CTX = ctx


def bind_client_factory(factory: Callable[..., Any] | None) -> None:
    """Override the Jellyfin client factory (used by tests)."""
    global _CLIENT_FACTORY
    _CLIENT_FACTORY = factory


def _resolve_ctx(kwargs: dict) -> Any:
    ctx = kwargs.pop("ctx", None)
    if ctx is None:
        ctx = _CTX
    return ctx


def _resolve_client_factory(kwargs: dict) -> Callable[..., Any] | None:
    factory = kwargs.pop("client_factory", None)
    if factory is None:
        factory = _CLIENT_FACTORY
    if factory is not None:
        return factory
    # Lazy import seam: the Jellyfin client is owned by a sibling worker and may
    # not be present yet. Never fabricate a client here.
    try:
        from hermes_screen import jellyfin as _jellyfin
    except Exception:  # pragma: no cover - depends on sibling module
        return None
    return getattr(_jellyfin, "JellyfinClient", None)


def library_status(args: dict, **kwargs: Any) -> str:
    """Return Jellyfin server status or a clear configuration/connection error."""
    ctx = _resolve_ctx(kwargs)
    secret_reader = kwargs.pop("secret_reader", None)
    client_factory = _resolve_client_factory(kwargs)

    if ctx is None:
        return json.dumps(
            error_payload(
                "not_configured",
                "Hermes Screen is not initialized. Reload the plugin.",
            )
        )

    config = Config(ctx, secret_reader=secret_reader)
    if not config.is_jellyfin_configured():
        return json.dumps(
            error_payload(
                "not_configured",
                "Set jellyfin_url and the JELLYFIN_API_KEY secret in the plugin "
                "settings, then retry.",
            )
        )

    if client_factory is None:
        return json.dumps(
            error_payload(
                "jellyfin_client_unavailable",
                "The Jellyfin client module is not available yet. Install the "
                "full Hermes Screen plugin.",
            )
        )

    base_url = config.jellyfin_url()
    api_key = config.jellyfin_api_key()
    user_id = config.jellyfin_user()

    try:
        with client_factory(base_url=base_url, api_key=api_key, user_id=user_id) as client:
            status = client.status()
    except Exception as exc:  # noqa: BLE001 - surface any failure as data
        return json.dumps(
            error_payload(
                "jellyfin_unreachable",
                f"Could not reach Jellyfin: {exc}",
            )
        )

    if not isinstance(status, dict):
        return json.dumps(
            error_payload(
                "jellyfin_bad_response",
                "Jellyfin returned an unexpected response.",
            )
        )

    result = dict(status)
    if result.get("ok") is False:
        reason = result.get("reason", "jellyfin_unreachable")
        hint = result.get("hint", "Check the Jellyfin URL and API key.")
        return json.dumps(
            error_payload(
                reason,
                hint,
                **{k: v for k, v in result.items() if k not in ("ok", "reason", "hint")},
            )
        )

    if "ok" not in result:
        result["ok"] = True
    return json.dumps(result)
