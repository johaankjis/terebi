"""Find timestamped scene candidates from an item's own text subtitle track.

Contract: ``docs/SCENE_CONTRACT.md``. This module never plays anything; it
returns candidates for the manager to show the user.

Jellyfin endpoints (OpenAPI 12.4.0 snapshot, sha256 02a60649..., re-fetched
2026-11-10 and byte-identical to the 2026-11-08 copy; source checked at tag
v12.4 = 83d0d0e7f76e23e2e085c8ff67d28b772d35967d):

* ``GET /Items/{itemId}?userId=..`` returns the item as that user sees it, with
  ``MediaSources[].MediaStreams[]`` (``Type == "Subtitle"``, ``Index``,
  ``Codec``, ``Language``, ``IsExternal``, ``IsForced``, ``IsTextSubtitleStream``).
* ``GET /Videos/{itemId}/{mediaSourceId}/Subtitles/{index}/Stream.{format}``
  (``SubtitleController.GetSubtitle``). The server looks the stream up in that
  exact media source by index and returns it unchanged when the format already
  matches, or converts text subtitles with its SubRip/WebVTT writers. With the
  default ``startPositionTicks=0`` cue times are not shifted
  (``SubtitleEncoder.FilterEvents``). Bitmap formats (PGS, VobSub, DVB) cannot be
  converted and are refused here before any request.

Security: the API key comes only from the constructor and is only ever sent in
the ``Authorization`` header, to URLs built from the configured base URL and
validated hex ids. Redirects are never followed. No caller-supplied URL is
fetched. Results never contain the key, URLs, file paths or exception text.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote, urlsplit

import httpx

from .jellyfin import JellyfinClient, JellyfinError
from .subtitles import (
    MAX_QUERY_CHARS,
    Cue,
    Match,
    SubtitleParseError,
    excerpt,
    find_exact,
    find_lexical,
    normalize_text,
    parse_subtitles,
    query_tokens,
    time_windows,
)

__all__ = ["LocalEmbedder", "SubtitleSceneResolver"]

REQUEST_TIMEOUT_S = 8.0
MAX_ITEM_BYTES = 4 * 1024 * 1024
MAX_SUBTITLE_BYTES = 2 * 1024 * 1024
MAX_LIMIT = 10
DEFAULT_LIMIT = 3
MAX_SOURCES = 20
MAX_TRACKS = 50
MAX_STORE_ENTRIES = 3  # tracks kept per profile store
MAX_ENTRY_CHARS = 1_000_000  # approximate stored size of one track index
MAX_EMBED_WINDOWS = 4_000
STORE_PREFIX = "scene_subtitles:v1:"
STORE_LRU_KEY = STORE_PREFIX + "lru"
TICKS_PER_SECOND = 10_000_000

_GUID_RE = re.compile(r"^[0-9a-f]{32}$")
_DASHED_GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_LANG_RE = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})?$")
_ITEM_TYPES = ("Movie", "Episode", "Video")
_BITMAP_CODECS = (
    "pgs",
    "pgssub",
    "hdmv_pgs_subtitle",
    "dvdsub",
    "dvd_subtitle",
    "vobsub",
    "dvbsub",
    "dvb_subtitle",
    "sup",
    "sub",
    "xsub",
)
_NATIVE_FORMAT = {"srt": "srt", "subrip": "srt", "webvtt": "vtt", "vtt": "vtt"}
_ACCEPTED_CONTENT_TYPES = ("text/", "application/x-subrip", "application/octet-stream")
_CLIENT_ID = {
    "Client": "Hermes Screen",
    "Device": "Hermes Screen",
    "DeviceId": "hermes-screen",
    "Version": "0.1.0",
}
# Common ISO 639-1 -> 639-2/B codes so "en" finds Jellyfin's "eng".
_LANG_ALIASES = {
    "en": "eng",
    "es": "spa",
    "fr": "fre",
    "de": "ger",
    "it": "ita",
    "pt": "por",
    "nl": "dut",
    "ja": "jpn",
    "zh": "chi",
    "ko": "kor",
    "ru": "rus",
    "sv": "swe",
    "da": "dan",
    "no": "nor",
    "fi": "fin",
    "pl": "pol",
    "tr": "tur",
    "ar": "ara",
    "he": "heb",
    "hi": "hin",
    "cs": "cze",
    "el": "gre",
    "hu": "hun",
    "ro": "rum",
    "uk": "ukr",
    "id": "ind",
    "th": "tha",
    "vi": "vie",
}
_LANG_B_T = {
    "fra": "fre",
    "deu": "ger",
    "nld": "dut",
    "zho": "chi",
    "ces": "cze",
    "ell": "gre",
    "ron": "rum",
}


@runtime_checkable
class LocalEmbedder(Protocol):
    """A local, already-approved text embedding model (optional, off by default).

    ``embed`` must run on this machine without network access or downloads. The
    resolver only uses it when no exact caption match exists and labels such
    candidates ``method: "semantic_local"`` with ``model_id``. Nothing in this
    repository ships or enables a model.
    """

    model_id: str

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class _Fail(Exception):
    def __init__(self, reason: str, hint: str, **extra: Any) -> None:
        super().__init__(reason)
        self.reason, self.hint, self.extra = reason, hint, extra

    def to_dict(self) -> dict[str, Any]:
        return {"ok": False, "reason": self.reason, "hint": self.hint, **self.extra}


def _norm_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    if _DASHED_GUID_RE.match(candidate):
        candidate = candidate.replace("-", "")
    return candidate if _GUID_RE.match(candidate) else None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _label(value: Any, limit: int = 80) -> str | None:
    """Server text reduced to printable characters and a bounded length."""
    if not isinstance(value, str):
        return None
    text = "".join(c for c in value if c.isprintable())
    text = " ".join(text.split())[:limit]
    return text or None


def _lang_key(value: Any) -> str | None:
    if not isinstance(value, str) or not _LANG_RE.match(value.strip()):
        return None
    base = value.strip().lower().split("-")[0]
    base = _LANG_ALIASES.get(base, base)
    return _LANG_B_T.get(base, base)


def _sha(*parts: Any) -> str:
    blob = json.dumps(parts, separators=(",", ":"), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _seconds(ms: int) -> float:
    return round(ms / 1000, 3)


# --- source and track description -------------------------------------------------


def _subtitle_streams(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    streams = source.get("MediaStreams")
    if not isinstance(streams, list):
        return []
    return [s for s in streams[:500] if isinstance(s, dict) and s.get("Type") == "Subtitle"]


def _track_problem(stream: Mapping[str, Any]) -> str | None:
    codec = stream.get("Codec")
    codec = codec.lower() if isinstance(codec, str) else ""
    if not _is_int(stream.get("Index")) or stream["Index"] < 0:
        return "no_index"
    if codec in _BITMAP_CODECS or any(b in codec for b in ("pgs", "dvdsub", "vobsub", "dvbsub")):
        return "bitmap"
    if stream.get("IsTextSubtitleStream") is False:
        return "bitmap"
    if not codec:
        return "unknown_codec"
    return None


def _request_format(codec: str) -> tuple[str, bool]:
    """Format to ask Jellyfin for, and whether the server converts it."""
    native = _NATIVE_FORMAT.get(codec.lower())
    return (native, False) if native else ("srt", True)


def _track_summary(stream: Mapping[str, Any]) -> dict[str, Any]:
    problem = _track_problem(stream)
    codec = stream.get("Codec") if isinstance(stream.get("Codec"), str) else None
    out: dict[str, Any] = {
        "track_index": stream.get("Index") if _is_int(stream.get("Index")) else None,
        "language": _label(stream.get("Language"), 16),
        "title": _label(stream.get("DisplayTitle") or stream.get("Title"), 60),
        "codec": _label(codec, 16),
        "external": stream.get("IsExternal") is True,
        "forced": stream.get("IsForced") is True,
        "default": stream.get("IsDefault") is True,
        "hearing_impaired": stream.get("IsHearingImpaired") is True,
        "searchable": problem is None,
    }
    if problem == "bitmap":
        out["problem"] = "image-based subtitles (would need OCR)"
    elif problem is not None:
        out["problem"] = "Jellyfin did not describe this track fully"
    elif codec is not None and _request_format(codec)[1]:
        out["converted_by_server"] = True
    return out


def _source_duration_s(source: Mapping[str, Any], item: Mapping[str, Any]) -> float | None:
    for ticks in (source.get("RunTimeTicks"), item.get("RunTimeTicks")):
        if _is_int(ticks) and ticks > 0:
            return ticks / TICKS_PER_SECOND
    return None


def _source_summary(source: Mapping[str, Any], item: Mapping[str, Any]) -> dict[str, Any]:
    duration = _source_duration_s(source, item)
    tracks = [_track_summary(s) for s in _subtitle_streams(source)[:MAX_TRACKS]]
    return {
        "media_source_id": _norm_id(source.get("Id")),
        "name": _label(source.get("Name")),
        "container": _label(source.get("Container"), 24),
        "duration_s": round(duration, 3) if duration is not None else None,
        "subtitle_tracks": tracks,
        "searchable_tracks": sum(1 for t in tracks if t["searchable"]),
    }


def _source_signature(source: Mapping[str, Any], item: Mapping[str, Any]) -> str:
    # The path is only hashed, never stored or returned.
    return _sha(
        "source",
        _norm_id(source.get("Id")),
        source.get("Path"),
        source.get("Size"),
        source.get("Container"),
        source.get("RunTimeTicks"),
        source.get("ETag"),
        item.get("Etag"),
    )


def _track_signature(stream: Mapping[str, Any]) -> str:
    return _sha(
        "track",
        *(
            stream.get(k)
            for k in (
                "Index",
                "Codec",
                "Language",
                "Title",
                "IsExternal",
                "IsForced",
                "IsDefault",
                "IsHearingImpaired",
                "Path",
                "DeliveryUrl",
            )
        ),
    )


# --- the resolver ------------------------------------------------------------------------


class SubtitleSceneResolver:
    """Search one movie edition's own text subtitles for timestamped candidates.

    ``store`` is a profile-local mutable mapping (the manager adapts
    ``ctx.state``); values written are JSON-compatible. Without one, a private
    in-memory dict is used, so nothing is persisted. The constructor does no
    I/O, starts nothing in the background and never raises for bad settings:
    those come back from each call as ``{"ok": False, "reason", "hint"}``.

    ``embedder`` is an optional :class:`LocalEmbedder`; it is ``None`` by
    default and no semantic ranking happens without it.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        user_id: str | None = None,
        store: MutableMapping[str, Any] | None = None,
        *,
        embedder: LocalEmbedder | None = None,
        min_similarity: float = 0.75,
    ) -> None:
        self.__api_key = api_key
        self._base_setting = base_url
        self._user_setting = user_id
        self._store: MutableMapping[str, Any] = store if store is not None else {}
        self._embedder = embedder
        self._min_similarity = float(min_similarity)
        self._jf: JellyfinClient | None = None
        self._http: httpx.Client | None = None
        self._base_url: str | None = None
        self._closed = False

    def __repr__(self) -> str:
        return "SubtitleSceneResolver(api_key='***')"

    def __enter__(self) -> SubtitleSceneResolver:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._closed = True
        if self._http is not None:
            self._http.close()
            self._http = None
        if self._jf is not None:
            self._jf.close()
            self._jf = None

    # -- public API ----------------------------------------------------------------------

    def editions(self, item_id: str) -> dict[str, Any]:
        """Compact media-source (edition) choices for ``item_id``.

        ``{"ok": True, "item_id", "title", "type", "sources": [...],
        "ambiguous"}``; ``ambiguous`` is true when the user must pick a source.
        Each source lists its subtitle tracks and whether they are searchable.
        """
        return self._guard(lambda: self._editions(item_id))

    def search(
        self,
        item_id: str,
        media_source_id: str | None,
        query: str,
        language: str | None = None,
        track_index: int | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        """Search the exact source's text subtitle track for ``query``.

        Returns ``{"ok": True, "candidates": [...], "no_match", "method", ...}``
        with candidates shaped as in ``docs/SCENE_CONTRACT.md``. Several
        candidates mean the user must choose; nothing is played. ``no_match``
        is explicit and comes with a hint to use a marker or timestamp.
        """
        return self._guard(
            lambda: self._search(item_id, media_source_id, query, language, track_index, limit)
        )

    # -- plumbing ------------------------------------------------------------------------

    def _guard(self, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return fn()
        except _Fail as exc:
            return exc.to_dict()
        except JellyfinError as exc:
            return exc.to_dict()
        except Exception:  # never leak exception text, URLs or keys
            return {
                "ok": False,
                "reason": "internal_error",
                "hint": "Scene search failed unexpectedly. Try again, or give a timestamp.",
            }

    def _setup(self) -> tuple[JellyfinClient, httpx.Client, str]:
        if self._closed:
            raise _Fail("client_closed", "The scene resolver was already closed.")
        if self._jf is None:
            jf = JellyfinClient(self._base_setting, self.__api_key, self._user_setting)
            parts = urlsplit(self._base_setting.strip())
            self._base_url = f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"
            self._jf = jf
        if self._http is None:
            self._http = httpx.Client(
                timeout=httpx.Timeout(REQUEST_TIMEOUT_S), follow_redirects=False
            )
        assert self._base_url is not None
        return self._jf, self._http, self._base_url

    def _auth_header(self) -> str:
        fields = [f'{k}="{v}"' for k, v in _CLIENT_ID.items()]
        fields.append(f'Token="{quote(self.__api_key.strip(), safe="")}"')
        return "MediaBrowser " + ", ".join(fields)

    def _get(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        accept: str,
        max_bytes: int,
        etag: str | None = None,
    ) -> tuple[int, bytes, httpx.Headers]:
        _, http, base = self._setup()
        headers = {"Accept": accept, "Authorization": self._auth_header()}
        if etag:
            headers["If-None-Match"] = etag
        else:
            headers["Cache-Control"] = "no-cache"
        try:
            with http.stream(
                "GET", base + path, params=params, headers=headers, timeout=REQUEST_TIMEOUT_S
            ) as response:
                status = response.status_code
                if status in (301, 302, 303, 307, 308):
                    raise _Fail(
                        "jellyfin_redirect",
                        "Jellyfin redirected the request. Use the final server URL in settings.",
                    )
                body = bytearray()
                if 200 <= status < 300:
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            raise _Fail(
                                "jellyfin_bad_response",
                                "Jellyfin sent an unexpectedly large response.",
                            )
                return status, bytes(body), response.headers
        except httpx.TimeoutException:
            raise _Fail(
                "jellyfin_unreachable", "Jellyfin did not answer within 8 seconds."
            ) from None
        except httpx.HTTPError as exc:
            raise _Fail(
                "jellyfin_unreachable",
                f"Could not reach Jellyfin ({type(exc).__name__}). Is the server running?",
            ) from None

    @staticmethod
    def _status_fail(status: int, what: str) -> _Fail:
        if status == 401:
            return _Fail("jellyfin_auth", "Jellyfin rejected the API key.")
        if status == 403:
            return _Fail("jellyfin_forbidden", "Jellyfin refused this request for the user.")
        if status == 404:
            return _Fail("not_found", f"Jellyfin has no such {what} for this user.")
        if status >= 500:
            return _Fail("jellyfin_server_error", f"Jellyfin had an error (HTTP {status}).")
        return _Fail("jellyfin_bad_request", f"Jellyfin rejected the request (HTTP {status}).")

    def _fetch_item(self, item_id: Any) -> tuple[str, str, dict[str, Any]]:
        norm = _norm_id(item_id)
        if norm is None:
            raise _Fail("invalid_argument", "item_id must be a Jellyfin item id (32 hex).")
        jf, _, _ = self._setup()
        user_id = jf.resolve_user()["id"]
        status, body, _ = self._get(
            f"/Items/{norm}",
            params={"userId": user_id},
            accept="application/json",
            max_bytes=MAX_ITEM_BYTES,
        )
        if status != 200:
            raise self._status_fail(status, "item")
        try:
            item = json.loads(body.decode("utf-8"))
        except ValueError:
            raise _Fail("jellyfin_bad_response", "Jellyfin did not answer with JSON.") from None
        if not isinstance(item, dict) or _norm_id(item.get("Id")) != norm:
            raise _Fail("jellyfin_bad_response", "Jellyfin returned a different or broken item.")
        if item.get("Type") not in _ITEM_TYPES:
            raise _Fail(
                "unsupported_media",
                "That item is not a single movie, episode or video. Pick one first.",
            )
        sources = item.get("MediaSources")
        if not isinstance(sources, list) or not sources:
            raise _Fail("no_media_source", "Jellyfin lists no file for this item.")
        if len(sources) > MAX_SOURCES or not all(
            isinstance(s, dict) and _norm_id(s.get("Id")) for s in sources
        ):
            raise _Fail("jellyfin_bad_response", "Jellyfin listed malformed media sources.")
        ids = [_norm_id(s["Id"]) for s in sources]
        if len(set(ids)) != len(ids):
            raise _Fail("jellyfin_bad_response", "Jellyfin listed duplicate media sources.")
        return norm, user_id, item

    def _editions(self, item_id: str) -> dict[str, Any]:
        norm, _, item = self._fetch_item(item_id)
        sources = [_source_summary(s, item) for s in item["MediaSources"]]
        return {
            "ok": True,
            "item_id": norm,
            "title": _label(item.get("Name"), 120),
            "type": item.get("Type"),
            "sources": sources,
            "ambiguous": len(sources) > 1,
        }

    # -- search -----------------------------------------------------------------------------

    def _search(
        self,
        item_id: Any,
        media_source_id: Any,
        query: Any,
        language: Any,
        track_index: Any,
        limit: Any,
    ) -> dict[str, Any]:
        if not _is_int(limit) or not 1 <= limit <= MAX_LIMIT:
            raise _Fail("invalid_argument", f"limit must be an integer from 1 to {MAX_LIMIT}.")
        if not isinstance(query, str) or not query.strip():
            raise _Fail("invalid_argument", "Say which line of dialogue to look for.")
        try:
            query_tokens(query)
        except ValueError:
            raise _Fail(
                "invalid_argument",
                f"The query needs real words and at most {MAX_QUERY_CHARS} characters.",
            ) from None
        wanted_lang = None
        if language is not None:
            wanted_lang = _lang_key(language)
            if wanted_lang is None:
                raise _Fail("invalid_argument", "language must be a code like eng or en.")
        if track_index is not None and (not _is_int(track_index) or track_index < 0):
            raise _Fail("invalid_argument", "track_index must be a non-negative integer.")
        wanted_source = None
        if media_source_id is not None:
            wanted_source = _norm_id(media_source_id)
            if wanted_source is None:
                raise _Fail("invalid_argument", "media_source_id must be 32 hex characters.")

        norm, user_id, item = self._fetch_item(item_id)
        source = self._pick_source(item, wanted_source)
        source_id = _norm_id(source["Id"])
        assert source_id is not None
        stream = self._pick_track(source, item, wanted_lang, track_index)
        duration = _source_duration_s(source, item)

        cues, info = self._load_track(norm, user_id, source_id, source, item, stream)
        candidates, method, total = self._rank(cues, query, duration, limit)
        out_candidates = []
        for match_cues, match in candidates:
            evidence = {
                "kind": "subtitle",
                "method": match.method,
                "track_index": stream["Index"],
                "language": info["language"],
                "track_fingerprint": info["fingerprint"],
                "cue_indices": [c.index for c in match_cues],
                "cue_start_s": _seconds(match_cues[0].start_ms),
                "cue_end_s": _seconds(max(c.end_ms for c in match_cues)),
                "excerpt": excerpt(match_cues, query),
            }
            if match.method != "exact":
                evidence["score"] = match.score
            if match.method == "semantic_local" and self._embedder is not None:
                evidence["model_id"] = _label(getattr(self._embedder, "model_id", None), 60)
            out_candidates.append(
                {
                    "item_id": norm,
                    "media_source_id": source_id,
                    "start_time_s": _seconds(match_cues[0].start_ms),
                    "evidence": evidence,
                }
            )
        result: dict[str, Any] = {
            "ok": True,
            "item_id": norm,
            "media_source_id": source_id,
            "title": _label(item.get("Name"), 120),
            "duration_s": round(duration, 3) if duration is not None else None,
            "track": {
                "track_index": stream["Index"],
                "language": info["language"],
                "codec": info["codec"],
                "converted_by_server": info["converted"],
                "cue_count": len(cues),
            },
            "index": info["index_state"],
            "method": method,
            "candidates": out_candidates,
            "total_matches": total,
            "truncated": total > len(out_candidates),
            "no_match": not out_candidates,
            "needs_choice": len(out_candidates) > 1,
        }
        if not out_candidates:
            result["hint"] = (
                "No subtitle line matches that. Try the exact words, or save a marker or "
                "give a timestamp instead."
            )
        elif method != "exact":
            result["hint"] = (
                "No exact line matched; these are approximate caption matches. "
                "Confirm with the user before playing."
            )
        elif len(out_candidates) > 1:
            result["hint"] = "That line occurs more than once. Ask which moment to play."
        return result

    def _pick_source(self, item: Mapping[str, Any], wanted: str | None) -> dict[str, Any]:
        sources = item["MediaSources"]
        choices = [_source_summary(s, item) for s in sources]
        if wanted is None:
            if len(sources) == 1:
                return sources[0]
            raise _Fail(
                "edition_ambiguous",
                "This title has several versions. Ask which one, then pass its media_source_id.",
                sources=choices,
            )
        for source in sources:
            if _norm_id(source.get("Id")) == wanted:
                return source
        raise _Fail(
            "edition_mismatch",
            "That media source does not belong to this item. Pick one of the listed versions.",
            sources=choices,
        )

    def _pick_track(
        self,
        source: Mapping[str, Any],
        item: Mapping[str, Any],
        wanted_lang: str | None,
        track_index: int | None,
    ) -> dict[str, Any]:
        streams = _subtitle_streams(source)[:MAX_TRACKS]
        tracks = [_track_summary(s) for s in streams]
        if not streams:
            raise _Fail(
                "no_subtitles",
                "This version has no subtitles to search. Save a marker or give a timestamp.",
            )
        if track_index is not None:
            chosen = [s for s in streams if s.get("Index") == track_index]
            if not chosen:
                raise _Fail(
                    "track_not_found",
                    "This version has no subtitle track with that index.",
                    tracks=tracks,
                )
        elif wanted_lang is not None:
            chosen = [s for s in streams if _lang_key(s.get("Language")) == wanted_lang]
            if not chosen:
                raise _Fail(
                    "no_subtitles_in_language",
                    "No subtitle track in that language. Pick one of the listed tracks.",
                    tracks=tracks,
                )
        else:
            chosen = streams
        usable = [s for s in chosen if _track_problem(s) is None]
        if not usable:
            if any(_track_problem(s) == "bitmap" for s in chosen):
                raise _Fail(
                    "subtitles_image_only",
                    "Those subtitles are images, which would need OCR. Save a marker or "
                    "give a timestamp instead.",
                    tracks=tracks,
                )
            raise _Fail("subtitles_unusable", "Jellyfin did not describe the track.", tracks=tracks)
        if len(usable) > 1:
            raise _Fail(
                "subtitle_track_ambiguous",
                "Several text subtitle tracks match. Pass language or track_index.",
                tracks=[
                    t
                    for t in tracks
                    if t["searchable"] and t["track_index"] in {s["Index"] for s in usable}
                ],
            )
        return usable[0]

    # -- local index -----------------------------------------------------------------------------

    def _load_track(
        self,
        item_id: str,
        user_id: str,
        source_id: str,
        source: Mapping[str, Any],
        item: Mapping[str, Any],
        stream: Mapping[str, Any],
    ) -> tuple[list[Cue], dict[str, Any]]:
        _, _, base = self._setup()
        index = stream["Index"]
        scope = _sha("scope", base, user_id, item_id, source_id, index)
        key = STORE_PREFIX + scope[:40]
        source_sig = _source_signature(source, item)
        track_sig = _track_signature(stream)
        codec = str(stream.get("Codec")).lower()
        fmt, converted = _request_format(codec)
        language = _label(stream.get("Language"), 16)

        cached = self._read_entry(key, scope)
        same_meta = (
            cached is not None
            and cached["source_sig"] == source_sig
            and cached["track_sig"] == track_sig
            and cached["format"] == fmt
        )
        etag = cached.get("etag") if same_meta and cached is not None else None
        status, body, headers = self._get(
            f"/Videos/{item_id}/{source_id}/Subtitles/{index}/Stream.{fmt}",
            accept="text/vtt, application/x-subrip, text/plain;q=0.5",
            max_bytes=MAX_SUBTITLE_BYTES,
            etag=etag,
        )
        if status == 304 and same_meta and cached is not None:
            cues = cached["cues"]
            state = "cached"
            content_sha = cached["content_sha"]
            new_etag = etag
        else:
            if status == 304:
                raise _Fail("jellyfin_bad_response", "Jellyfin answered 'not modified' oddly.")
            if status != 200:
                if status >= 500:
                    raise _Fail(
                        "subtitles_unavailable",
                        "Jellyfin could not extract that subtitle track. Try another track, "
                        "or save a marker or give a timestamp.",
                    )
                raise self._status_fail(status, "subtitle track")
            ctype = headers.get("content-type", "").split(";")[0].strip().lower()
            if ctype == "text/html" or (ctype and not ctype.startswith(_ACCEPTED_CONTENT_TYPES)):
                raise _Fail(
                    "subtitles_unusable", "Jellyfin did not return subtitle text for that track."
                )
            content_sha = hashlib.sha256(body).hexdigest()
            new_etag = _label(headers.get("etag"), 200)
            if same_meta and cached is not None and cached["content_sha"] == content_sha:
                cues = cached["cues"]
                state = "cached"
            else:
                try:
                    cues = parse_subtitles(body, fmt)
                except SubtitleParseError as exc:
                    hints = {
                        "subtitle_encoding": "The subtitle file is not UTF-8 text.",
                        "subtitle_too_large": "The subtitle track is too large to index.",
                    }
                    raise _Fail(
                        "subtitles_unusable",
                        hints.get(exc.reason, "The subtitle track could not be read reliably.")
                        + " Save a marker or give a timestamp instead.",
                    ) from None
                state = "refreshed" if cached is not None else "built"
        fingerprint = _sha(
            "fingerprint",
            base,
            user_id,
            item_id,
            source_id,
            index,
            codec,
            language,
            source_sig,
            track_sig,
            content_sha,
        )
        entry = {
            "v": 1,
            "scope": scope,
            "source_sig": source_sig,
            "track_sig": track_sig,
            "format": fmt,
            "content_sha": content_sha,
            "etag": new_etag,
            "cues": [[c.index, c.start_ms, c.end_ms, c.text] for c in cues],
        }
        stored = self._write_entry(key, entry, cues)
        return cues, {
            "fingerprint": fingerprint,
            "language": language,
            "codec": _label(codec, 16),
            "converted": converted,
            "index_state": state if stored else state + "_not_stored",
        }

    def _read_entry(self, key: str, scope: str) -> dict[str, Any] | None:
        try:
            raw = self._store.get(key)
        except Exception:
            return None
        if not isinstance(raw, dict) or raw.get("v") != 1 or raw.get("scope") != scope:
            return None
        for field in ("source_sig", "track_sig", "format", "content_sha"):
            if not isinstance(raw.get(field), str):
                return None
        rows = raw.get("cues")
        if not isinstance(rows, list) or not rows:
            return None
        cues: list[Cue] = []
        for row in rows:
            if not (
                isinstance(row, list | tuple)
                and len(row) == 4
                and all(_is_int(v) and v >= 0 for v in row[:3])
                and row[2] >= row[1]
                and isinstance(row[3], str)
            ):
                return None
            cues.append(Cue(index=row[0], start_ms=row[1], end_ms=row[2], text=row[3]))
        etag = raw.get("etag")
        return {**raw, "etag": etag if isinstance(etag, str) else None, "cues": cues}

    def _write_entry(self, key: str, entry: dict[str, Any], cues: Sequence[Cue]) -> bool:
        size = sum(len(c.text) + 32 for c in cues)
        try:
            lru = self._store.get(STORE_LRU_KEY)
            lru = [k for k in lru if isinstance(k, str)] if isinstance(lru, list) else []
            lru = [k for k in lru if k != key]
            if size > MAX_ENTRY_CHARS:
                if key in self._store:
                    del self._store[key]
                self._store[STORE_LRU_KEY] = lru
                return False
            self._store[key] = entry
            lru.append(key)
            while len(lru) > MAX_STORE_ENTRIES:
                old = lru.pop(0)
                if old.startswith(STORE_PREFIX) and old in self._store:
                    del self._store[old]
            self._store[STORE_LRU_KEY] = lru
            return True
        except Exception:
            return False

    # -- ranking ---------------------------------------------------------------------------------

    def _rank(
        self, cues: Sequence[Cue], query: str, duration_s: float | None, limit: int
    ) -> tuple[list[tuple[list[Cue], Match]], str, int]:
        order = sorted(cues, key=lambda c: (c.start_ms, c.index))
        if duration_s is not None:
            limit_ms = math.floor(duration_s * 1000)
            order = [c for c in order if c.start_ms < limit_ms]
        norms = [normalize_text(c.text) for c in order]
        matches = find_exact(order, query, norm_texts=norms)
        method = "exact"
        if not matches:
            matches = find_lexical(order, query, norm_texts=norms)
            method = "lexical" if matches else "none"
        if not matches and self._embedder is not None:
            matches = self._semantic(order, query, norms)
            method = "semantic_local" if matches else "none"
        if method == "exact":
            matches.sort(key=lambda m: m.positions[0])
        picked = [([order[p] for p in m.positions], m) for m in matches[:limit]]
        return picked, method, len(matches)

    def _semantic(self, order: Sequence[Cue], query: str, norms: Sequence[str]) -> list[Match]:
        embedder = self._embedder
        if embedder is None:
            return []
        windows = [w for w in time_windows(order, 2) if any(norms[p] for p in w)]
        if not windows or len(windows) > MAX_EMBED_WINDOWS:
            return []
        texts = [" ".join(order[p].plain for p in w) for w in windows]
        vectors = list(embedder.embed([query, *texts]))
        if len(vectors) != len(texts) + 1:
            raise _Fail("semantic_unavailable", "The local embedding model gave a bad answer.")

        def unit(vec: Sequence[float]) -> list[float] | None:
            vals = [float(v) for v in vec]
            norm = math.sqrt(sum(v * v for v in vals))
            if not norm or not all(math.isfinite(v) for v in vals):
                return None
            return [v / norm for v in vals]

        q = unit(vectors[0])
        if q is None:
            return []
        scored: list[tuple[float, tuple[int, ...]]] = []
        for window, vec in zip(windows, vectors[1:], strict=True):
            u = unit(vec)
            if u is None or len(u) != len(q):
                continue
            sim = sum(a * b for a, b in zip(q, u, strict=True))
            if sim >= self._min_similarity:
                scored.append((sim, window))
        scored.sort(key=lambda sw: (-sw[0], len(sw[1]), sw[1][0]))
        used: set[int] = set()
        out: list[Match] = []
        for sim, window in scored:
            if used.intersection(window):
                continue
            used.update(window)
            out.append(Match(positions=window, method="semantic_local", score=round(sim, 3)))
        return out
