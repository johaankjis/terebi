"""Small, profile-local Hermes tool handlers."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from .hermes_screen.config import Config
from .hermes_screen.errors import error_payload

_PICK_ARGUMENTS = frozenset({"max_minutes", "limit"})
_ITEM_ID_RE = re.compile(
    r"^(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$"
)
_DEFAULT_PICK_LIMIT = 3


def _error(reason: str, hint: str) -> str:
    return json.dumps(error_payload(reason, hint))


def _read_connection(
    ctx: Any, secret_reader: Callable[[str], str | None] | None
) -> tuple[str, str, str | None] | str:
    """Read settings and the secret for this call; a JSON error string on failure."""
    if ctx is None:
        return _error("not_configured", "Reload the Hermes Screen plugin.")
    try:
        config = Config(ctx, secret_reader=secret_reader)
        base_url = config.jellyfin_url()
        api_key = config.jellyfin_api_key()
        user_id = config.jellyfin_user()
    except Exception:
        return _error(
            "jellyfin_config",
            "Could not read settings. Check the plugin settings and secret scope.",
        )
    if not base_url or not api_key:
        return _error(
            "not_configured",
            "Set jellyfin_url and the JELLYFIN_API_KEY secret in plugin settings.",
        )
    return base_url, api_key, user_id


def library_status(
    args: dict,
    *,
    ctx: Any = None,
    secret_reader: Callable[[str], str | None] | None = None,
) -> str:
    """Read settings per call and return status; never expose exception text."""
    connection = _read_connection(ctx, secret_reader)
    if isinstance(connection, str):
        return connection
    base_url, api_key, user_id = connection
    try:
        from .hermes_screen.jellyfin import JellyfinClient, JellyfinError
    except Exception:
        return _error(
            "jellyfin_client_unavailable", "Reinstall Hermes Screen with its httpx dependency."
        )
    try:
        with JellyfinClient(base_url, api_key, user_id=user_id) as client:
            result = client.status()
        return json.dumps(result)
    except JellyfinError as exc:
        return json.dumps(exc.to_dict())
    except Exception:
        return _error(
            "jellyfin_unreachable",
            "Could not read Jellyfin status. Check the server and settings.",
        )


def _parse_pick_args(args: Any) -> tuple[Any, Any] | str:
    """Return ``(max_minutes, limit)`` from Hermes' arguments, or a JSON error string.

    Hermes may hand over a dict or the raw JSON text of one. Only the shape is
    checked here; the values are validated by ``pick_titles`` itself.
    """
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return _error("invalid_argument", "Arguments must be a JSON object.")
    if not isinstance(args, dict):
        return _error("invalid_argument", "Arguments must be a JSON object.")
    unknown = sorted(str(key) for key in args if key not in _PICK_ARGUMENTS)
    if unknown:
        return _error(
            "invalid_argument",
            "Unsupported argument(s): " + ", ".join(unknown)[:100] + ". "
            "Use only max_minutes and limit.",
        )
    if "max_minutes" not in args:
        return _error("invalid_argument", "max_minutes is required (minutes the viewer has).")
    limit = args.get("limit")
    return args["max_minutes"], _DEFAULT_PICK_LIMIT if limit is None else limit


def library_pick(
    args: dict,
    *,
    ctx: Any = None,
    secret_reader: Callable[[str], str | None] | None = None,
) -> str:
    """Pick up to three titles that fit in ``max_minutes``; never expose exception text."""
    parsed = _parse_pick_args(args)
    if isinstance(parsed, str):
        return parsed
    max_minutes, limit = parsed
    connection = _read_connection(ctx, secret_reader)
    if isinstance(connection, str):
        return connection
    base_url, api_key, user_id = connection
    try:
        from .hermes_screen.jellyfin import JellyfinClient, JellyfinError
        from .hermes_screen.picker import pick_titles
    except Exception:
        return _error(
            "jellyfin_client_unavailable", "Reinstall Hermes Screen with its httpx dependency."
        )
    try:
        with JellyfinClient(base_url, api_key, user_id=user_id) as client:
            result = pick_titles(client, max_minutes, limit=limit)
        return json.dumps(result)
    except JellyfinError as exc:
        return json.dumps(exc.to_dict())
    except Exception:
        return _error(
            "jellyfin_unreachable",
            "Could not pick titles from Jellyfin. Check the server and settings.",
        )


def _parse_object(args: Any) -> dict | str:
    """Hermes may hand over a dict or its JSON text; anything else is an error string."""
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except ValueError:
            return _error("invalid_argument", "Arguments must be a JSON object.")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return _error("invalid_argument", "Arguments must be a JSON object.")
    return args


def _parse_play_args(args: Any) -> str | dict:
    """Return ``{"item_id": ...}`` (format-checked, not resolved), or a JSON error string."""
    parsed = _parse_object(args)
    if isinstance(parsed, str):
        return parsed
    unknown = sorted(str(key) for key in parsed if key != "item_id")
    if unknown:
        return _error(
            "invalid_argument",
            "Unsupported argument(s): " + ", ".join(unknown)[:100] + ". Use only item_id.",
        )
    item_id = parsed.get("item_id")
    if not isinstance(item_id, str) or not _ITEM_ID_RE.match(item_id.strip()):
        return _error(
            "invalid_argument",
            "item_id must be the exact Jellyfin item id returned by library_pick, "
            "not a title. Call library_pick first.",
        )
    return {"item_id": item_id.strip()}


def _read_cast_settings(ctx: Any) -> Any:
    """Validated Cast settings, or a JSON error string."""
    try:
        from .hermes_screen.cast import CastError
        from .hermes_screen.playback import parse_cast_settings
    except Exception:
        return _error(
            "cast_unavailable", "Reinstall Hermes Screen with its Chromecast dependencies."
        )
    try:
        config = Config(ctx)
        raw = (config.chromecast_host(), config.cast_media_base_url(), config.cast_relay_bind())
    except Exception:
        return _error("cast_config", "Could not read the Chromecast settings. Check them.")
    try:
        return parse_cast_settings(*raw)
    except CastError as exc:
        return json.dumps(exc.to_dict())


def tv_play(
    args: Any,
    *,
    ctx: Any = None,
    manager: Any = None,
    secret_reader: Callable[[str], str | None] | None = None,
) -> str:
    """Validate an exact Jellyfin item, cast it, and report receiver-verified state."""
    parsed = _parse_play_args(args)
    if isinstance(parsed, str):
        return parsed
    if ctx is None or manager is None:
        return _error("not_configured", "Reload the Hermes Screen plugin.")
    settings = _read_cast_settings(ctx)
    if isinstance(settings, str):
        return settings
    connection = _read_connection(ctx, secret_reader)
    if isinstance(connection, str):
        return connection
    base_url, api_key, user_id = connection
    try:
        from .hermes_screen.jellyfin import JellyfinClient, JellyfinError
    except Exception:
        return _error(
            "jellyfin_client_unavailable", "Reinstall Hermes Screen with its httpx dependency."
        )
    try:
        with JellyfinClient(base_url, api_key, user_id=user_id) as client:
            source = client.get_cast_source(parsed["item_id"])
            upstream_url, auth_header = client.cast_stream_target(source)
    except JellyfinError as exc:
        return json.dumps(exc.to_dict())
    except Exception:
        return _error(
            "jellyfin_unreachable",
            "Could not check that item in Jellyfin. Check the server and settings.",
        )
    try:
        return json.dumps(manager.play(settings, source, upstream_url, auth_header))
    except Exception:
        return _error("cast_failed", "Something went wrong talking to the Chromecast. Try again.")


def tv_pause(args: Any, *, ctx: Any = None, manager: Any = None) -> str:
    """Pause only what this context started, and report receiver-verified state."""
    parsed = _parse_object(args)
    if isinstance(parsed, str):
        return parsed
    if parsed:
        return _error("invalid_argument", "tv_pause takes no arguments.")
    if ctx is None or manager is None:
        return _error("not_configured", "Reload the Hermes Screen plugin.")
    try:
        return json.dumps(manager.pause())
    except Exception:
        return _error("cast_failed", "Something went wrong talking to the Chromecast. Try again.")
