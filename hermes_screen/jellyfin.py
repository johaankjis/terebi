"""Jellyfin API client for Hermes Screen.

Jellyfin is the source of truth for the library and watch history; the Roku is
only the output. This module is self-contained (stdlib + ``httpx``) and never
reads the environment or any credential file: the API key is injected by the
caller (through Hermes' secret scope) and is only ever sent in the
``Authorization`` header to the configured server.

Upstream references (checked 2026-11-08, see docs/RESEARCH.md):

* OpenAPI spec: https://api.jellyfin.org/openapi/jellyfin-openapi-stable.json
  (``info.version`` 12.4.0). Endpoints used: ``GET /System/Info/Public``,
  ``GET /Users``, ``GET /Users/{userId}``, ``GET /Items``, ``GET /Items/Counts``,
  ``GET /UserItems/Resume``, ``GET /Shows/NextUp``, ``GET /Sessions``.
* Server auth parsing: ``Jellyfin.Server.Implementations/Security/
  AuthorizationContext.cs`` in jellyfin/jellyfin at tag v12.4
  (83d0d0e7f76e23e2e085c8ff67d28b772d35967d): header
  ``Authorization: MediaBrowser Client=".." Token=".."``.
* The Jellyfin Roku app identifies itself as client ``Jellyfin Roku`` with a
  device name of ``"<name> (<model>)"``: ``source/api/baserequest.bs``
  ``buildAuthHeader`` in jellyfin/jellyfin-roku at
  a7b786d0595f741849aab7eb5c558f674274abc7.

The module-level docstring of each public method states what is checked at
runtime. The rule of thumb: nothing the server returns is trusted blindly, and
absence of evidence is never reported as success.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Self
from urllib.parse import quote, urlsplit

import httpx

__all__ = [
    "ROKU_CLIENT_NAME",
    "JellyfinClient",
    "JellyfinError",
]

# --- limits and constants -------------------------------------------------------

REQUEST_TIMEOUT_S = 8.0  # AGENTS.md: 8s for Jellyfin, on every request
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
PAGE_SIZE = 50  # items asked from the server per request
MAX_PAGES = 5  # per call: at most PAGE_SIZE * MAX_PAGES items are scanned
MAX_LIMIT = 25  # most items one call will ever return
DEFAULT_LIMIT = 5
MAX_GENRES = 10
MAX_QUERY_LEN = 200
MAX_SESSIONS_SCANNED = 200
TICKS_PER_SECOND = 10_000_000  # Jellyfin ticks are 100 ns
TICKS_PER_MINUTE = 60 * TICKS_PER_SECOND

ROKU_CLIENT_NAME = "Jellyfin Roku"  # Client field the official Roku app sends
DEFAULT_SESSION_MAX_AGE_S = 60.0
_CLOCK_SKEW_ALLOWANCE_S = 5.0

_CLIENT_ID = {
    "Client": "Hermes Screen",
    "Device": "Hermes Screen",
    "DeviceId": "hermes-screen",
    "Version": "0.1.0",
}

_ITEM_TYPES = ("Movie", "Series", "Season", "Episode", "Video")
_DEFAULT_FIND_TYPES = ("Movie", "Series")
_RESUME_TYPES = ("Movie", "Episode", "Video")

# Chromecast direct play (Default Media Receiver): what this version accepts unchanged.
CAST_ITEM_TYPES = ("Movie", "Episode", "Video")
CAST_CONTAINERS = frozenset({"mp4", "m4v"})
CAST_FILE_SUFFIXES = (".mp4", ".m4v")
CAST_VIDEO_CODECS = frozenset({"h264"})
CAST_AUDIO_CODECS = frozenset({"aac", "mp3"})
CAST_MAX_HEIGHT = 1080

_GUID_RE = re.compile(r"^[0-9a-f]{32}$")
_DASHED_GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_CONTROL_RE = re.compile(r"[\x00-\x20\x7f]")


# --- errors ----------------------------------------------------------------------


class JellyfinError(Exception):
    """A Jellyfin failure with a stable machine reason and a human hint.

    ``to_dict()`` gives the repo-wide error shape ``{"ok": False, "reason",
    "hint"}``. Messages never contain the API key.
    """

    def __init__(
        self,
        reason: str,
        hint: str,
        *,
        status_code: int | None = None,
    ) -> None:
        super().__init__(f"{reason}: {hint}")
        self.reason = reason
        self.hint = hint
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        return {"ok": False, "reason": self.reason, "hint": self.hint}


# --- small pure helpers ------------------------------------------------------------


def _norm_id(value: Any) -> str | None:
    """Return a Jellyfin id as 32 lowercase hex chars, or ``None`` if invalid."""
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    if _DASHED_GUID_RE.match(candidate):
        candidate = candidate.replace("-", "")
    return candidate if _GUID_RE.match(candidate) else None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _positive_ticks(value: Any) -> int | None:
    return value if _is_int(value) and value > 0 else None


def _fold(value: str) -> str:
    """Case/accent-insensitive form used for name comparison."""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.casefold().split())


def _parse_time(value: Any) -> datetime | None:
    """Parse a Jellyfin timestamp (7 fractional digits, ``Z``) to aware UTC."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _minutes(ticks: int) -> int:
    return max(1, round(ticks / TICKS_PER_MINUTE))


def _check_limit(limit: Any) -> int:
    if not _is_int(limit) or limit < 1:
        raise JellyfinError("invalid_argument", f"limit must be an integer from 1 to {MAX_LIMIT}.")
    return min(limit, MAX_LIMIT)


def _check_minutes(name: str, value: Any) -> float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
        or value > 24 * 60
    ):
        raise JellyfinError(
            "invalid_argument",
            f"{name} must be a number of minutes between 0 and 1440.",
        )
    return float(value)


def _check_item_types(
    item_types: Iterable[str] | None, default: tuple[str, ...]
) -> tuple[str, ...]:
    if item_types is None:
        return default
    if isinstance(item_types, str):
        item_types = [item_types]
    allowed = {t.lower(): t for t in _ITEM_TYPES}
    chosen: list[str] = []
    for raw in item_types:
        canonical = allowed.get(raw.lower()) if isinstance(raw, str) else None
        if canonical is None:
            raise JellyfinError(
                "invalid_argument",
                "item type must be one of: " + ", ".join(_ITEM_TYPES) + ".",
            )
        if canonical not in chosen:
            chosen.append(canonical)
    if not chosen:
        raise JellyfinError("invalid_argument", "item_types must not be empty.")
    return tuple(chosen)


def _validate_base_url(base_url: Any) -> str:
    hint = "Use the server address like http://192.168.1.10:8096 (or https://host/jellyfin)."
    if not isinstance(base_url, str) or not base_url.strip():
        raise JellyfinError("jellyfin_config", "Jellyfin URL is empty. " + hint)
    text = base_url.strip()
    if _CONTROL_RE.search(text):
        raise JellyfinError("jellyfin_config", "Jellyfin URL has bad characters. " + hint)
    try:
        parts = urlsplit(text)
        _ = parts.port  # raises ValueError for a bad port
    except ValueError:
        raise JellyfinError("jellyfin_config", "Jellyfin URL is malformed. " + hint) from None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise JellyfinError(
            "jellyfin_config",
            "Jellyfin URL must start with http:// or https://. " + hint,
        )
    if parts.username is not None or parts.password is not None:
        raise JellyfinError(
            "jellyfin_config",
            "Jellyfin URL must not contain a username or password; use the API key setting.",
        )
    if parts.query or parts.fragment:
        raise JellyfinError(
            "jellyfin_config",
            "Jellyfin URL must not contain a query or fragment. " + hint,
        )
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"


def _validate_api_key(api_key: Any) -> str:
    if not isinstance(api_key, str) or not api_key.strip():
        raise JellyfinError(
            "jellyfin_config",
            "No Jellyfin API key is set. Create one in Dashboard > API Keys.",
        )
    key = api_key.strip()
    if _CONTROL_RE.search(key) or len(key) > 512:
        raise JellyfinError(
            "jellyfin_config",
            "The Jellyfin API key looks malformed; paste it again from Dashboard > API Keys.",
        )
    return key


# --- the client ---------------------------------------------------------------------


class JellyfinClient:
    """Small synchronous Jellyfin client.

    ``user_id`` may be a user id (GUID, dashed or not) or an exact user name.
    When it is omitted the server must have exactly one enabled user, otherwise
    user resolution fails with ``jellyfin_user_ambiguous`` rather than guessing.

    The constructor does no network I/O. Use as a context manager or call
    :meth:`close`.
    """

    def __init__(self, base_url: str, api_key: str, user_id: str | None = None) -> None:
        self._base_url = _validate_base_url(base_url)
        self._api_key = _validate_api_key(api_key)
        if user_id is not None and (not isinstance(user_id, str) or not user_id.strip()):
            raise JellyfinError("jellyfin_config", "user_id must be a non-empty string or None.")
        self._user_setting = user_id.strip() if user_id is not None else None
        self._user: dict[str, str] | None = None
        self._closed = False
        self._http = httpx.Client(
            timeout=httpx.Timeout(REQUEST_TIMEOUT_S),
            follow_redirects=False,  # never forward the key to another host
        )

    def __repr__(self) -> str:
        return f"JellyfinClient(base_url={self._base_url!r}, api_key='***')"

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._http.close()

    # -- transport ---------------------------------------------------------------

    def _auth_header(self) -> str:
        fields = [f'{k}="{v}"' for k, v in _CLIENT_ID.items()]
        fields.append(f'Token="{quote(self._api_key, safe="")}"')
        return "MediaBrowser " + ", ".join(fields)

    def _get(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        authenticated: bool = True,
    ) -> tuple[Any, httpx.Headers]:
        """GET ``path`` (always a fixed, server-relative path) and parse JSON."""
        if self._closed:
            raise JellyfinError("client_closed", "The Jellyfin client was already closed.")
        headers = {"Accept": "application/json", "Cache-Control": "no-cache"}
        if authenticated:
            headers["Authorization"] = self._auth_header()
        query: dict[str, str] = {}
        for key, value in (params or {}).items():
            if value is None:
                continue
            query[key] = "true" if value is True else "false" if value is False else str(value)
        url = self._base_url + path
        try:
            with self._http.stream(
                "GET", url, params=query, headers=headers, timeout=REQUEST_TIMEOUT_S
            ) as response:
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise JellyfinError(
                            "jellyfin_bad_response",
                            "The Jellyfin server sent an unexpectedly large response.",
                        )
                status = response.status_code
                response_headers = response.headers
        except httpx.TimeoutException:
            raise JellyfinError(
                "jellyfin_unreachable",
                "Jellyfin did not answer within 8 seconds. Is the server up and the URL right?",
            ) from None
        except httpx.InvalidURL:
            raise JellyfinError("jellyfin_config", "The Jellyfin URL is not valid.") from None
        except httpx.HTTPError as exc:
            raise JellyfinError(
                "jellyfin_unreachable",
                f"Could not reach Jellyfin ({type(exc).__name__}). "
                "Check the URL, the port and that the server is running.",
            ) from None
        self._raise_for_status(status)
        try:
            return json.loads(bytes(body).decode("utf-8")), response_headers
        except ValueError:
            raise JellyfinError(
                "jellyfin_bad_response",
                "Jellyfin answered with something that is not JSON. "
                "Is the URL pointing at Jellyfin (and its base path, if any)?",
                status_code=status,
            ) from None

    @staticmethod
    def _raise_for_status(status: int) -> None:
        if 200 <= status < 300:
            return
        if status in (301, 302, 303, 307, 308):
            raise JellyfinError(
                "jellyfin_redirect",
                "Jellyfin redirected the request. Use the final URL (for example https://) "
                "in the settings.",
                status_code=status,
            )
        if status == 401:
            raise JellyfinError(
                "jellyfin_auth",
                "Jellyfin rejected the API key. Create a new one in Dashboard > API Keys.",
                status_code=status,
            )
        if status == 403:
            raise JellyfinError(
                "jellyfin_forbidden",
                "Jellyfin refused this request. Check the API key and the user's permissions.",
                status_code=status,
            )
        if status == 404:
            raise JellyfinError(
                "not_found",
                "Jellyfin has no such resource. Check the server URL (and base path).",
                status_code=status,
            )
        if status >= 500:
            raise JellyfinError(
                "jellyfin_server_error",
                f"Jellyfin had an internal error (HTTP {status}). "
                "If it just started, wait a minute and retry.",
                status_code=status,
            )
        raise JellyfinError(
            "jellyfin_bad_request",
            f"Jellyfin rejected the request (HTTP {status}).",
            status_code=status,
        )

    # -- server info and status ----------------------------------------------------

    def server_info(self) -> dict[str, Any]:
        """Public server info: ``{"name", "version", "id"}``. No API key needed."""
        data, _ = self._get("/System/Info/Public", authenticated=False)
        if not isinstance(data, dict):
            raise _bad_shape("server info")
        name, version = data.get("ServerName"), data.get("Version")
        if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
            raise _bad_shape("server info")
        server_id = data.get("Id")
        return {
            "name": name,
            "version": version,
            "id": server_id if isinstance(server_id, str) else None,
        }

    def status(self) -> dict[str, Any]:
        """Never raises for Jellyfin failures.

        Success: ``{"ok": True, "server": {"name", "version"}, "user": {"id",
        "name"}, "counts": {...}}`` (``counts`` only when the server returned
        sane numbers). Failure: ``{"ok": False, "reason", "hint"}``.
        """
        try:
            server = self.server_info()
            user = self.resolve_user()  # also proves the API key works
            result: dict[str, Any] = {
                "ok": True,
                "server": {"name": server["name"], "version": server["version"]},
                "user": dict(user),
            }
            counts = self._counts(user["id"])
            if counts:
                result["counts"] = counts
            return result
        except JellyfinError as exc:
            return exc.to_dict()

    def _counts(self, user_id: str) -> dict[str, int]:
        try:
            data, _ = self._get("/Items/Counts", {"userId": user_id})
        except JellyfinError as exc:
            if exc.reason in ("jellyfin_auth", "jellyfin_forbidden"):
                raise
            return {}  # counts are a nicety; their absence must not fail status
        if not isinstance(data, dict):
            return {}
        counts: dict[str, int] = {}
        for label, key in (
            ("movies", "MovieCount"),
            ("series", "SeriesCount"),
            ("episodes", "EpisodeCount"),
        ):
            value = data.get(key)
            if _is_int(value) and value >= 0:
                counts[label] = value
        return counts

    # -- users ------------------------------------------------------------------------

    def resolve_user(self) -> dict[str, str]:
        """Resolve (and cache) the Jellyfin user: ``{"id", "name"}``.

        Configured id: verified to exist. Configured name: exact
        (case-sensitive) match, error if zero or several match. Nothing
        configured: the single enabled user, otherwise
        ``jellyfin_user_ambiguous`` (never "the first user").
        """
        if self._user is not None:
            return dict(self._user)
        setting = self._user_setting
        wanted_id = _norm_id(setting) if setting else None
        if wanted_id:
            data, _ = self._get(f"/Users/{wanted_id}")
            user = _parse_user(data)
            if user is None or user["id"] != wanted_id:
                raise _bad_shape("user")
            self._user = user
            return dict(user)

        data, _ = self._get("/Users", {"isDisabled": False})
        if not isinstance(data, list):
            raise _bad_shape("user list")
        users = [u for u in (_parse_user(entry) for entry in data) if u is not None]
        if data and not users:
            raise _bad_shape("user list")
        if setting:
            matches = [u for u in users if u["name"] == setting]
            if not matches:
                raise JellyfinError(
                    "jellyfin_user_not_found",
                    "No enabled Jellyfin user has that name. Check the user setting.",
                )
        else:
            matches = users
            if not matches:
                raise JellyfinError(
                    "jellyfin_user_not_found",
                    "Jellyfin has no enabled users. Create one, or enable an existing one.",
                )
        if len(matches) > 1:
            raise JellyfinError(
                "jellyfin_user_ambiguous",
                "More than one Jellyfin user matches. "
                "Set the Jellyfin user (name or id) in the plugin settings.",
            )
        self._user = matches[0]
        return dict(self._user)

    # -- items ----------------------------------------------------------------------------

    def get_item(self, item_id: str) -> dict[str, Any]:
        """Look up one item by id. ``not_found`` if the id is unknown."""
        norm = _norm_id(item_id)
        if norm is None:
            raise JellyfinError("invalid_argument", "item_id must be a Jellyfin item id.")
        user = self.resolve_user()
        try:
            data, _ = self._get(f"/Items/{norm}", {"userId": user["id"]})
        except JellyfinError as exc:
            if exc.reason == "not_found":
                raise JellyfinError(
                    "not_found",
                    "Jellyfin has no item with that id. Search the library again.",
                ) from None
            raise
        item = _shape_item(data)
        if item is None or item["item_id"] != norm:
            raise _bad_shape("item")
        return item

    def get_cast_source(self, item_id: str, media_source_id: str | None = None) -> dict[str, Any]:
        """Validate one file (edition) of an item the Chromecast can play as-is.

        When ``media_source_id`` is given it must be a media source that belongs
        to exactly this item; it is used as it is (never a silent fallback to
        another edition). When it is left out and the item has several editions
        of which more than one could play directly, ``edition_ambiguous`` is
        raised instead of quietly picking one.

        The item is read as the configured user (so the user must be able to see
        it). Only a local MP4 with H.264 video (at most 1080p) and AAC/MP3 or no
        audio is accepted; anything else raises ``unsupported_media`` rather than
        pretending a transcode exists. ``duration_s`` and ``minutes`` come from
        the selected source (the source's own runtime when Jellyfin reports one,
        so offset bounds belong to that edition rather than the item's mixing
        another edition's runtime). Returns ``{"item_id", "title", "type",
        "minutes", "duration_s", "media_source_id"}``; the file path is never
        returned.
        """
        norm = _norm_id(item_id)
        if norm is None:
            raise JellyfinError("invalid_argument", "item_id must be a Jellyfin item id.")
        wanted_source = None
        if media_source_id is not None:
            wanted_source = _norm_id(media_source_id)
            if wanted_source is None:
                raise JellyfinError(
                    "invalid_argument",
                    "media_source_id must be a Jellyfin media source id (its 32 hexadecimal "
                    "characters, dashed or not).",
                )
        user = self.resolve_user()
        try:
            data, _ = self._get(f"/Items/{norm}", {"userId": user["id"]})
        except JellyfinError as exc:
            if exc.reason == "not_found":
                raise JellyfinError(
                    "not_found",
                    "Jellyfin has no item with that id for this user. Pick from the library again.",
                ) from None
            raise
        item = _shape_item(data)
        if item is None or item["item_id"] != norm:
            raise _bad_shape("item")
        if item["type"] not in CAST_ITEM_TYPES:
            raise JellyfinError(
                "unsupported_media",
                f"That item is a {_safe_label(item['type'])}, not a single video. "
                "Pick a movie, episode or video.",
            )
        sources = data.get("MediaSources")
        if not isinstance(sources, list) or not sources:
            raise JellyfinError(
                "unsupported_media", "Jellyfin lists no playable file for this item."
            )
        dicts = [s for s in sources if isinstance(s, dict)]
        if not dicts:
            raise _unsupported_media("Jellyfin lists no usable file")
        valid = [s for s in dicts if _norm_id(s.get("Id")) is not None]
        source = (
            _selected_cast_source(valid, wanted_source)
            if wanted_source is not None
            else _default_cast_source(dicts, valid)
        )
        problem = _cast_problem(source)
        if problem is not None:
            raise _unsupported_media(problem)
        ticks = _positive_ticks(source.get("RunTimeTicks"))
        if ticks is None and len(dicts) == 1:
            ticks = item["_ticks"]  # only one edition: item runtime describes that file
        return {
            "item_id": norm,
            "title": item["title"],
            "type": item["type"],
            "minutes": _minutes(ticks) if ticks else None,
            "duration_s": ticks / TICKS_PER_SECOND if ticks else None,
            "media_source_id": _norm_id(source.get("Id")),
        }

    def cast_stream_target(self, source: Mapping[str, Any]) -> tuple[str, str]:
        """The pinned static-stream URL and ``Authorization`` value for a cast source.

        ``source`` must come from :meth:`get_cast_source`. The URL is built only
        from the configured base URL and validated hex ids (no caller-supplied
        path or query); the API key stays in the returned header value and is
        never placed in the URL.
        """
        item_id = _norm_id(source.get("item_id"))
        source_id = _norm_id(source.get("media_source_id"))
        if item_id is None or source_id is None:
            raise JellyfinError("invalid_argument", "Not a validated cast source.")
        url = f"{self._base_url}/Videos/{item_id}/stream?static=true&mediaSourceId={source_id}"
        return url, self._auth_header()

    def find_items(
        self,
        query: str | None = None,
        *,
        item_types: Iterable[str] | None = None,
        genres: Iterable[str] | None = None,
        max_minutes: float | None = None,
        unwatched_only: bool = False,
        limit: int = DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        """Search the library with strict client-side re-checking.

        Every returned item satisfies *all* given constraints as verified on
        the returned data, whatever the server did with the query parameters:
        type in ``item_types`` (default Movie and Series), runtime known and
        ``<= max_minutes``, at least one of ``genres`` (case-insensitive) and,
        for ``unwatched_only``, ``UserData.Played`` explicitly false. Items
        missing the data needed to prove a constraint are excluded and counted.

        Returns ``{"items", "scanned", "truncated", "skipped_unknown_runtime",
        "skipped_malformed", "skipped_filtered"}``. ``truncated`` means the scan cap
        was hit while more results may exist.
        """
        limit = _check_limit(limit)
        types = _check_item_types(item_types, _DEFAULT_FIND_TYPES)
        max_minutes = _check_minutes("max_minutes", max_minutes)
        wanted_genres = _check_genres(genres)
        text = _check_query(query)
        user = self.resolve_user()

        params: dict[str, Any] = {
            "userId": user["id"],
            "recursive": True,
            "includeItemTypes": ",".join(types),
            "fields": "Genres",
            "enableUserData": True,
            "enableImages": False,
            "searchTerm": text,
            "genres": "|".join(wanted_genres) if wanted_genres else None,
            "isPlayed": False if unwatched_only else None,
            "sortBy": None if text else "SortName",
            "sortOrder": None if text else "Ascending",
        }

        def keep(item: dict[str, Any]) -> bool:
            if item["type"] not in types:
                return False
            if unwatched_only and item["played"] is not False:
                return False
            if wanted_genres:
                have = {_fold(g) for g in item["genres"]}
                if not have & {_fold(g) for g in wanted_genres}:
                    return False
            return True

        return self._collect("/Items", params, keep, limit, max_minutes, remaining=False)

    def get_resume_items(
        self, *, max_minutes: float | None = None, limit: int = 10
    ) -> dict[str, Any]:
        """Items the user started and has not finished, most recent first.

        Re-checked: type is Movie/Episode/Video, ``Played`` is not true and a
        positive ``PlaybackPositionTicks`` is present. ``max_minutes`` limits the
        *remaining* time (runtime minus position); items without a runtime are
        excluded when it is given. Each item has ``resume_seconds`` and
        ``remaining_minutes``.
        """
        limit = _check_limit(limit)
        max_minutes = _check_minutes("max_minutes", max_minutes)
        user = self.resolve_user()
        params = {
            "userId": user["id"],
            "includeItemTypes": ",".join(_RESUME_TYPES),
            "mediaTypes": "Video",
            "fields": "Genres",
            "enableUserData": True,
            "enableImages": False,
        }

        def keep(item: dict[str, Any]) -> bool:
            return (
                item["type"] in _RESUME_TYPES
                and item["played"] is not True
                and item["resume_seconds"] > 0
            )

        return self._collect("/UserItems/Resume", params, keep, limit, max_minutes, remaining=True)

    def get_next_up(
        self,
        series_id: str | None = None,
        *,
        max_minutes: float | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Next Up episodes. Re-checked: Episode, not already played, and, when
        ``series_id`` is given, belonging to that series."""
        limit = _check_limit(limit)
        max_minutes = _check_minutes("max_minutes", max_minutes)
        series_norm = None
        if series_id is not None:
            series_norm = _norm_id(series_id)
            if series_norm is None:
                raise JellyfinError("invalid_argument", "series_id must be a Jellyfin item id.")
        user = self.resolve_user()
        params = {
            "userId": user["id"],
            "seriesId": series_norm,
            "fields": "Genres",
            "enableUserData": True,
            "enableImages": False,
            "enableRewatching": False,
        }

        def keep(item: dict[str, Any]) -> bool:
            if item["type"] != "Episode" or item["played"] is True:
                return False
            return series_norm is None or item["series_id"] == series_norm

        return self._collect("/Shows/NextUp", params, keep, limit, max_minutes, remaining=True)

    def _collect(
        self,
        path: str,
        base_params: Mapping[str, Any],
        keep: Callable[[dict[str, Any]], bool],
        limit: int,
        max_minutes: float | None,
        *,
        remaining: bool,
    ) -> dict[str, Any]:
        """Page through ``path`` (bounded), shape + filter items, stop at ``limit``."""
        max_ticks = None if max_minutes is None else max_minutes * TICKS_PER_MINUTE
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        scanned = malformed = unknown_runtime = filtered = 0
        truncated = False
        start = 0
        for page in range(MAX_PAGES):
            params = dict(base_params)
            params.update(startIndex=start, limit=PAGE_SIZE, enableTotalRecordCount=True)
            data, _ = self._get(path, params)
            if not isinstance(data, dict) or not isinstance(data.get("Items"), list):
                raise _bad_shape("item list")
            raw_items = data["Items"]
            total = data.get("TotalRecordCount")
            new_on_page = 0
            consumed = 0
            for raw in raw_items:
                consumed += 1
                scanned += 1
                item = _shape_item(raw)
                if item is None:
                    malformed += 1
                    continue
                if item["item_id"] in seen:
                    continue  # a server ignoring startIndex must not loop us
                seen.add(item["item_id"])
                new_on_page += 1
                if not keep(item):
                    filtered += 1
                    continue
                if max_ticks is not None:
                    ticks = item["_ticks"]
                    if ticks is None:
                        unknown_runtime += 1
                        continue
                    needed = ticks - item["_position_ticks"] if remaining else ticks
                    if needed > max_ticks:
                        filtered += 1
                        continue
                out.append(item)
                if len(out) >= limit:
                    break
            if scanned and malformed == scanned and not out:
                raise _bad_shape("item list")
            start += len(raw_items)
            exhausted = (
                len(raw_items) < PAGE_SIZE
                or new_on_page == 0
                or (_is_int(total) and start >= total)
            )
            if len(out) >= limit:
                truncated = consumed < len(raw_items) or not exhausted
                break
            if exhausted:
                break
            if page == MAX_PAGES - 1:
                truncated = True  # scan cap reached while more may exist
        return {
            "items": [_public(item, remaining) for item in out],
            "scanned": scanned,
            "truncated": truncated,
            "skipped_unknown_runtime": unknown_runtime,
            "skipped_malformed": malformed,
            "skipped_filtered": filtered,
        }

    # -- playback evidence ---------------------------------------------------------------------

    def verify_playback(
        self,
        item_id: str,
        *,
        device_id: str | None = None,
        device_name: str | None = None,
        client: str | None = ROKU_CLIENT_NAME,
        max_age_seconds: float = DEFAULT_SESSION_MAX_AGE_S,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Check item identity and report play/pause evidence separately.

        Evidence is read from ``GET /Sessions``. The result is
        ``"verified": True`` only when exactly one fresh session matches the
        configured target device (``device_id`` exact, and/or ``device_name``
        exact on the full Jellyfin name or its ``"Name (Model)"`` prefix), the
        ``client`` (default the Roku app; ``None`` skips), the resolved user
        when one is configured, and that session's ``NowPlayingItem.Id`` equals
        ``item_id``. Everything else is ``verified: False`` with a ``reason``:
        ``no_session``, ``wrong_user``, ``stale_session``, ``ambiguous_session``,
        ``nothing_playing``, ``wrong_item`` or ``malformed_evidence``. A generic
        "something is playing", another device or a matching *title* never
        verifies. Jellyfin/network failures also return ``verified: False``
        (with ``ok: False``); this method does not raise them.

        ``verified`` establishes item identity only, including when paused.
        Only ``playing is True`` establishes active playback; ``None`` cannot
        establish play or pause. This is server evidence, not Roku verification.

        Freshness uses ``LastPlaybackCheckIn`` against the server clock (the
        HTTP ``Date`` header) unless ``now`` is given.
        """
        wanted = _norm_id(item_id)
        if wanted is None:
            raise JellyfinError("invalid_argument", "item_id must be a Jellyfin item id.")
        wanted_device_id = device_id.strip() if isinstance(device_id, str) else None
        wanted_name = device_name.strip() if isinstance(device_name, str) else None
        if not wanted_device_id and not wanted_name:
            raise JellyfinError(
                "invalid_argument",
                "verify_playback needs the target device_id or device_name; "
                "it never picks a device on its own.",
            )
        if (
            isinstance(max_age_seconds, bool)
            or not isinstance(max_age_seconds, (int, float))
            or not math.isfinite(max_age_seconds)
            or max_age_seconds <= 0
        ):
            raise JellyfinError("invalid_argument", "max_age_seconds must be a positive number.")

        unverified = _Unverified(wanted)
        try:
            user_id = self._configured_user_id()
            params = {"deviceId": wanted_device_id} if wanted_device_id else None
            data, headers = self._get("/Sessions", params)
        except JellyfinError as exc:
            return {
                **unverified("jellyfin_error"),
                "ok": False,
                "reason": exc.reason,
                "hint": exc.hint,
            }
        if not isinstance(data, list):
            return unverified("malformed_evidence")
        if len(data) > MAX_SESSIONS_SCANNED:
            return unverified("session_scan_limit")
        sessions = [s for s in data if isinstance(s, dict)]
        if len(sessions) != len(data):
            return unverified("malformed_evidence")

        matches = [
            s for s in sessions if _session_matches_device(s, wanted_device_id, wanted_name, client)
        ]
        if not matches:
            return unverified("no_session")
        if user_id is not None:
            matches = [s for s in matches if _norm_id(s.get("UserId")) == user_id]
            if not matches:
                return unverified("wrong_user")

        server_now = now if now is not None else _server_now(headers)
        fresh = [s for s in matches if _is_fresh(s, server_now, float(max_age_seconds))]
        if not fresh:
            return unverified("stale_session")
        if len(fresh) > 1:
            return unverified("ambiguous_session", matched_sessions=len(fresh))

        session = fresh[0]
        playing = session.get("NowPlayingItem")
        if playing is None:
            return unverified("nothing_playing", session=_session_summary(session, server_now))
        if not isinstance(playing, dict):
            return unverified("malformed_evidence")
        playing_id = _norm_id(playing.get("Id"))
        if playing_id is None:
            return unverified("malformed_evidence")
        title = playing.get("Name")
        now_playing = {
            "item_id": playing_id,
            "title": title if isinstance(title, str) else None,
        }
        summary = _session_summary(session, server_now)
        if playing_id != wanted:
            return unverified("wrong_item", now_playing=now_playing, session=summary)

        state = session.get("PlayState")
        state = state if isinstance(state, dict) else {}
        paused = state.get("IsPaused") if isinstance(state.get("IsPaused"), bool) else None
        position = state.get("PositionTicks")
        return {
            "ok": True,
            "verified": True,
            "reason": None,
            "item_id": wanted,
            "now_playing": now_playing,
            "paused": paused,
            "playing": None if paused is None else not paused,
            "position_s": position // TICKS_PER_SECOND
            if _is_int(position) and position >= 0
            else None,
            "session": summary,
            "matched_sessions": 1,
        }

    def _configured_user_id(self) -> str | None:
        """User to require on the session, only when a user is configured."""
        if self._user_setting is None:
            return None
        return self.resolve_user()["id"]


# --- module-level helpers that need no client state ----------------------------------------


def _bad_shape(what: str) -> JellyfinError:
    return JellyfinError(
        "jellyfin_bad_response",
        f"Jellyfin sent {what} in a shape this plugin does not understand. "
        "The server version may be unsupported.",
    )


def _safe_label(value: Any) -> str:
    """A short server-supplied label reduced to harmless characters."""
    text = value if isinstance(value, str) else ""
    cleaned = "".join(c for c in text[:24] if c.isalnum() or c in "._-, ")
    return cleaned or "unknown"


def _cast_problem(source: Any) -> str | None:
    """Why a raw ``MediaSourceInfo`` can't be cast directly, or ``None`` if it can."""
    if not isinstance(source, dict):
        return "Jellyfin lists no usable file"
    if _norm_id(source.get("Id")) is None:
        return "its media source has no valid id"
    protocol = source.get("Protocol")
    if protocol is not None and protocol != "File":
        return "it is not a local file"
    if source.get("IsRemote") is True:
        return "it is a remote stream"
    container = source.get("Container")
    parts = set()
    if isinstance(container, str):
        parts = {part.strip().lower() for part in container.split(",")}
    if not parts & CAST_CONTAINERS:
        return f"its container is {_safe_label(container)}, not MP4"
    path = source.get("Path")
    if isinstance(path, str) and not path.lower().endswith(CAST_FILE_SUFFIXES):
        return "its file is not an .mp4"
    streams = source.get("MediaStreams")
    streams = [s for s in streams if isinstance(s, dict)] if isinstance(streams, list) else []
    videos = [s for s in streams if s.get("Type") == "Video"]
    if not videos:
        return "Jellyfin reports no video stream"
    video = videos[0]
    codec = video.get("Codec")
    if not isinstance(codec, str) or codec.lower() not in CAST_VIDEO_CODECS:
        return f"its video codec is {_safe_label(codec)}, not H.264"
    height = video.get("Height")
    if _is_int(height) and height > CAST_MAX_HEIGHT:
        return "its video is larger than 1080p"
    audios = [s for s in streams if s.get("Type") == "Audio"]
    if audios:
        wanted = source.get("DefaultAudioStreamIndex")
        audio = next((s for s in audios if _is_int(wanted) and s.get("Index") == wanted), audios[0])
        codec = audio.get("Codec")
        if not isinstance(codec, str) or codec.lower() not in CAST_AUDIO_CODECS:
            return f"its audio codec is {_safe_label(codec)}, not AAC or MP3"
    return None


def _unsupported_media(problem: str) -> JellyfinError:
    return JellyfinError(
        "unsupported_media",
        f"This item can't play directly on the Chromecast: {problem}. Only MP4 files "
        "with H.264 video (up to 1080p) and AAC or MP3 audio are supported; "
        "transcoding is not.",
    )


def _selected_cast_source(valid: list[dict[str, Any]], wanted: str) -> dict[str, Any]:
    """The one media source of this item whose id is exactly ``wanted``.

    Never falls back to another source: zero matches and duplicate ids are
    reported honestly so the caller re-checks which edition it meant.
    """
    matches = [s for s in valid if _norm_id(s.get("Id")) == wanted]
    if not matches:
        raise JellyfinError(
            "source_not_found",
            "That item has no media source with that media_source_id; the id may belong "
            "to another item or be mistyped. Re-check the edition you want to play.",
        )
    if len(matches) > 1:
        raise JellyfinError(
            "jellyfin_bad_response",
            "Jellyfin lists more than one media source with the same id on this item, "
            "so that media source id does not name exactly one edition.",
        )
    return matches[0]


def _default_cast_source(
    dicts: list[dict[str, Any]], valid: list[dict[str, Any]]
) -> dict[str, Any]:
    """The media source to cast when the caller did not name one.

    One source (or one directly playable source among several): that one.
    Several equally playable editions: ``edition_ambiguous``, never a quiet pick.
    """
    if not valid:
        return dicts[0]  # diagnosed by _cast_problem below (first: no valid id)
    if len(valid) == 1:
        return valid[0]
    castable = [s for s in valid if _cast_problem(s) is None]
    if len(castable) == 1:
        return castable[0]  # the only edition that could work is not ambiguous
    if len(castable) > 1:
        raise JellyfinError(
            "edition_ambiguous",
            f"This item has {len(valid)} media sources (editions) and more than one could "
            "play directly. Choose an edition and pass its media_source_id.",
        )
    return valid[0]  # none playable: diagnosed by _cast_problem below


def _parse_user(entry: Any) -> dict[str, str] | None:
    if not isinstance(entry, dict):
        return None
    uid, name = _norm_id(entry.get("Id")), entry.get("Name")
    if uid is None or not isinstance(name, str) or not name:
        return None
    return {"id": uid, "name": name}


def _check_query(query: str | None) -> str | None:
    if query is None:
        return None
    if not isinstance(query, str):
        raise JellyfinError("invalid_argument", "query must be text.")
    text = " ".join(query.split())
    if len(text) > MAX_QUERY_LEN or any(ord(c) < 32 for c in text):
        raise JellyfinError("invalid_argument", "query is too long or has bad characters.")
    return text or None


def _check_genres(genres: Iterable[str] | None) -> tuple[str, ...]:
    if genres is None:
        return ()
    if isinstance(genres, str):
        genres = [genres]
    chosen: list[str] = []
    for genre in genres:
        if not isinstance(genre, str) or not genre.strip() or "|" in genre or len(genre) > 60:
            raise JellyfinError("invalid_argument", "genres must be short plain names.")
        chosen.append(genre.strip())
    if len(chosen) > MAX_GENRES:
        raise JellyfinError("invalid_argument", f"Give at most {MAX_GENRES} genres.")
    return tuple(chosen)


def _shape_item(raw: Any) -> dict[str, Any] | None:
    """Validate a raw ``BaseItemDto`` and keep only what we need.

    Returns ``None`` when the id or name is missing/invalid. Private fields
    (``_ticks``, ``_position_ticks``) are stripped by :func:`_public`.
    """
    if not isinstance(raw, dict):
        return None
    item_id, name, kind = _norm_id(raw.get("Id")), raw.get("Name"), raw.get("Type")
    if item_id is None or not isinstance(name, str) or not name or not isinstance(kind, str):
        return None
    ticks = _positive_ticks(raw.get("RunTimeTicks"))
    year = raw.get("ProductionYear")
    genres = raw.get("Genres")
    user_data = raw.get("UserData") if isinstance(raw.get("UserData"), dict) else {}
    played = user_data.get("Played")
    position = user_data.get("PlaybackPositionTicks")
    position = position if _is_int(position) and position > 0 else 0
    season, episode = raw.get("ParentIndexNumber"), raw.get("IndexNumber")
    series_name = raw.get("SeriesName")
    return {
        "item_id": item_id,
        "title": name,
        "type": kind,
        "year": year if _is_int(year) and 1800 <= year <= 2200 else None,
        "minutes": _minutes(ticks) if ticks else None,
        "genres": [g for g in genres if isinstance(g, str)][:5] if isinstance(genres, list) else [],
        "played": played if isinstance(played, bool) else None,
        "resume_seconds": position // TICKS_PER_SECOND,
        "series_id": _norm_id(raw.get("SeriesId")),
        "series_name": series_name if isinstance(series_name, str) else None,
        "season_number": season if _is_int(season) and season >= 0 else None,
        "episode_number": episode if _is_int(episode) and episode >= 0 else None,
        "_ticks": ticks,
        "_position_ticks": position,
    }


def _public(item: dict[str, Any], with_remaining: bool) -> dict[str, Any]:
    result = {k: v for k, v in item.items() if not k.startswith("_")}
    if item["type"] != "Episode":
        for key in ("series_id", "series_name", "season_number", "episode_number"):
            result.pop(key)
    if with_remaining:
        ticks = item["_ticks"]
        result["remaining_minutes"] = (
            _minutes(max(ticks - item["_position_ticks"], 1)) if ticks else None
        )
    else:
        result.pop("resume_seconds")
    return result


def _session_matches_device(
    session: Mapping[str, Any],
    device_id: str | None,
    device_name: str | None,
    client: str | None,
) -> bool:
    """All configured identity fields must match; unconfigured ones are skipped."""
    if device_id and session.get("DeviceId") != device_id:
        return False
    if client and session.get("Client") != client:
        return False
    if device_name:
        name = session.get("DeviceName")
        if not isinstance(name, str):
            return False
        wanted = _fold(device_name)
        full = _fold(name)
        # The Roku app reports "<Roku name> (<model>)"; accept the bare name too.
        bare = _fold(name.rsplit(" (", 1)[0]) if name.endswith(")") and " (" in name else full
        if wanted not in (full, bare):
            return False
    return True


def _server_now(headers: httpx.Headers) -> datetime:
    date = headers.get("date")
    if date:
        try:
            parsed = parsedate_to_datetime(date)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except (TypeError, ValueError):
            pass
    return datetime.now(UTC)


def _is_fresh(session: Mapping[str, Any], now: datetime, max_age: float) -> bool:
    if session.get("IsActive") is False:
        return False
    stamp = _parse_time(session.get("LastPlaybackCheckIn"))
    if stamp is None:
        return False
    # Jellyfin's "never" value is year 1 and so is far outside any window.
    age = now - stamp
    return timedelta(seconds=-_CLOCK_SKEW_ALLOWANCE_S) <= age <= timedelta(seconds=max_age)


def _session_summary(session: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    stamp = _parse_time(session.get("LastPlaybackCheckIn"))
    age = (now - stamp).total_seconds() if stamp else None
    return {
        "device_name": _str_or_none(session.get("DeviceName")),
        "client": _str_or_none(session.get("Client")),
        "user_name": _str_or_none(session.get("UserName")),
        "check_in_age_s": None if age is None or age > 10**9 else round(max(age, 0.0)),
    }


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


class _Unverified:
    """Builds the ``verified: False`` result for one requested item."""

    def __init__(self, item_id: str) -> None:
        self._item_id = item_id

    def __call__(self, reason: str, **extra: Any) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ok": True,
            "verified": False,
            "reason": reason,
            "item_id": self._item_id,
            "now_playing": None,
            "paused": None,
            "playing": None,
            "position_s": None,
            "session": None,
            "matched_sessions": 0,
        }
        result.update(extra)
        return result
