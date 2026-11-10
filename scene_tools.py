"""Hermes scene selection and edition-scoped manual markers.

Subtitle indexes and markers use profile-owned state. Pending choices are bounded,
expire, and are scoped to trusted conversation context, never a model argument.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import secrets
import threading
import time
from collections.abc import MutableMapping
from typing import Any

from . import tools
from .hermes_screen.scene_search import SubtitleSceneResolver

CHOICE_TTL_S = 900
MAX_CHOICES = 64
MAX_MARKERS = 100


def _error(reason: str, hint: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "reason": reason, "hint": hint, **extra}


def _args(args: Any, allowed: set[str]) -> dict:
    if isinstance(args, str):
        args = json.loads(args)
    if not isinstance(args, dict) or set(args) - allowed:
        raise ValueError("arguments")
    return args


def _id(value: Any) -> str:
    if not isinstance(value, str) or not tools._ITEM_ID_RE.fullmatch(value.strip()):
        raise ValueError("id")
    return value.strip().replace("-", "").lower()


def _text(value: Any, limit: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("text")
    return value.strip()


def _offset(value: Any, duration: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("offset")
    try:
        valid = math.isfinite(value) and 0 <= value < duration
    except (TypeError, OverflowError):
        valid = False
    if not valid:
        raise ValueError("offset")
    return float(value)


class _StateMap(MutableMapping):
    """Adapt Hermes PluginState.get/set without relying on a private file path."""

    def __init__(self, state: Any, key: str) -> None:
        self.state, self.key = state, key

    def _read(self) -> dict:
        value = self.state.get(self.key, {})
        if not isinstance(value, dict):
            raise ValueError("state")
        return copy.deepcopy(value)

    def __getitem__(self, key: str) -> Any:
        return self._read()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        data = self._read()
        data[key] = value
        self.state.set(self.key, data)

    def __delitem__(self, key: str) -> None:
        data = self._read()
        del data[key]
        self.state.set(self.key, data)

    def __iter__(self):
        return iter(self._read())

    def __len__(self) -> int:
        return len(self._read())


class SceneTools:
    """One profile registration's scene tools and ephemeral conversation choices."""

    def __init__(self, ctx: Any, manager: Any, *, clock=time.monotonic) -> None:
        self.ctx, self.manager, self.clock = ctx, manager, clock
        self.lock = threading.RLock()
        self.pending: dict[str, dict] = {}
        state = getattr(ctx, "state", None)
        self.state = state if callable(getattr(state, "set", None)) else None
        self.cache = _StateMap(self.state, "scene_cache_v1") if self.state else {}

    def call(self, method: str, args: Any, conversation_id: Any = None) -> str:
        with self.lock:
            try:
                connection = tools._read_connection(self.ctx, None)
                if isinstance(connection, str):
                    return connection
                scope = hashlib.sha256(json.dumps(connection[::2]).encode()).hexdigest()
                who = conversation_id if isinstance(conversation_id, str) else "local"
                result = getattr(self, "_" + method)(args, connection, scope, who)
            except (ValueError, TypeError, OverflowError):
                result = _error(
                    "invalid_argument", "Check the tool arguments and timestamp bounds."
                )
            except Exception:
                result = _error("scene_failed", "Scene lookup failed. Check settings and retry.")
            return json.dumps(result)

    def _resolver(self, connection: tuple) -> SubtitleSceneResolver:
        return SubtitleSceneResolver(*connection, store=self.cache)

    def _movie(self, args: dict, connection: tuple) -> tuple[str | None, dict | None]:
        if "item_id" in args:
            if "movie" in args:
                raise ValueError("movie and item")
            return _id(args["item_id"]), None
        movie = _text(args.get("movie"))
        from .hermes_screen.jellyfin import JellyfinClient, JellyfinError

        try:
            with JellyfinClient(*connection) as client:
                found = client.find_items(movie, item_types=("Movie", "Video"), limit=10)
        except JellyfinError as exc:
            return None, exc.to_dict()
        items = found["items"]
        if len(items) != 1 or found["truncated"]:
            return None, _error(
                "movie_ambiguous" if items else "not_found",
                "Ask which movie or edition, then use its item_id."
                if items
                else "No movie matched. Try its title as shown in Jellyfin.",
                movies=items,
                truncated=found["truncated"],
            )
        return items[0]["item_id"], None

    @staticmethod
    def _edition(resolver: SubtitleSceneResolver, item_id: str, source: Any) -> tuple:
        editions = resolver.editions(item_id)
        if not editions["ok"]:
            return None, editions
        sources = editions["sources"]
        if source is None:
            if len(sources) != 1:
                return None, _error(
                    "edition_ambiguous",
                    "Ask which version to use.",
                    item_id=item_id,
                    sources=sources,
                )
            return sources[0], None
        wanted = _id(source)
        for edition in sources:
            if edition["media_source_id"] == wanted:
                return edition, None
        return None, _error(
            "edition_mismatch",
            "Choose a source belonging to this movie.",
            item_id=item_id,
            sources=sources,
        )

    def _markers(self, scope: str) -> list:
        if self.state is None:
            return []
        value = self.state.get("scene_markers_v1:" + scope, [])
        if not isinstance(value, list) or len(value) > MAX_MARKERS:
            raise ValueError("markers")
        return copy.deepcopy(value)

    def _offer(self, candidates: list, scope: str, who: str, lookup: dict | None = None) -> list:
        now = self.clock()
        self.pending = {k: v for k, v in self.pending.items() if v["expires"] > now}
        result = []
        for candidate in candidates:
            while len(self.pending) >= MAX_CHOICES:
                del self.pending[next(iter(self.pending))]
            choice_id = secrets.token_urlsafe(18)
            self.pending[choice_id] = dict(
                candidate=copy.deepcopy(candidate),
                scope=scope,
                who=who,
                expires=now + CHOICE_TTL_S,
                lookup=lookup,
            )
            result.append(
                {
                    **candidate,
                    "candidate_id": choice_id,
                    "timestamp": _timestamp(candidate["start_time_s"]),
                }
            )
        return result

    def _find(self, args: Any, connection: tuple, scope: str, who: str) -> dict:
        args = _args(
            args,
            {
                "movie",
                "item_id",
                "media_source_id",
                "query",
                "marker",
                "start_time_s",
                "language",
                "track_index",
            },
        )
        if "movie" not in args and "item_id" not in args:
            return _error(
                "movie_required", "Which movie should I search? Supply its title or item_id."
            )
        item_id, error = self._movie(args, connection)
        if error:
            return error
        selectors = [key for key in ("query", "marker", "start_time_s") if key in args]
        if len(selectors) > 1:
            raise ValueError("selector")
        with self._resolver(connection) as resolver:
            edition, error = self._edition(resolver, item_id, args.get("media_source_id"))
            if error:
                return error
            source_id = edition["media_source_id"]
            if not selectors:
                return {
                    "ok": True,
                    "item_id": item_id,
                    "edition": edition,
                    "markers": [
                        m
                        for m in self._markers(scope)
                        if m["item_id"] == item_id and m["media_source_id"] == source_id
                    ],
                    "hint": "Give dialogue, a saved marker label, or start_time_s.",
                }
            selector = selectors[0]
            lookup = None
            if selector == "query":
                query = _text(args["query"])
                result = resolver.search(
                    item_id, source_id, query, args.get("language"), args.get("track_index")
                )
                if not result["ok"]:
                    return result
                lookup = {
                    "query": query,
                    "language": args.get("language"),
                    "track_index": result["track"]["track_index"],
                }
                candidates = result["candidates"]
            elif selector == "marker":
                label = _text(args["marker"], 80).casefold()
                candidates = [
                    m
                    for m in self._markers(scope)
                    if m["item_id"] == item_id
                    and m["media_source_id"] == source_id
                    and m["evidence"]["label"].casefold() == label
                ]
                if any(
                    m["evidence"].get("source_fingerprint") != edition["fingerprint"]
                    for m in candidates
                ):
                    return _error(
                        "marker_stale",
                        "The edition changed. Confirm its timestamp and save the marker again.",
                    )
                result = {"ok": True, "method": "user_supplied", "no_match": not candidates}
            else:
                seconds = _offset(args["start_time_s"], edition["duration_s"])
                candidates = [
                    {
                        "item_id": item_id,
                        "media_source_id": source_id,
                        "start_time_s": seconds,
                        "evidence": {
                            "kind": "timestamp",
                            "method": "user_supplied",
                            "source_fingerprint": edition["fingerprint"],
                        },
                    }
                ]
                result = {"ok": True, "method": "user_supplied", "no_match": False}
            result["candidates"] = self._offer(candidates, scope, who, lookup)
            result["needs_choice"] = len(candidates) > 1
            result["choice_expires_in_s"] = CHOICE_TTL_S
            if not candidates:
                result["hint"] = (
                    "No scene matched. Give exact dialogue, save a marker, or supply a timestamp."
                )
            return result

    def _save(self, args: Any, connection: tuple, scope: str, who: str) -> dict:
        args = _args(args, {"item_id", "media_source_id", "label", "start_time_s"})
        item_id, label = _id(args.get("item_id")), _text(args.get("label"), 80)
        if self.state is None:
            return _error(
                "state_unavailable", "Local plugin state is unavailable; marker was not saved."
            )
        with self._resolver(connection) as resolver:
            edition, error = self._edition(resolver, item_id, args.get("media_source_id"))
            if error:
                return error
        seconds = _offset(args.get("start_time_s"), edition["duration_s"])
        source_id = edition["media_source_id"]
        markers = self._markers(scope)
        matches = [
            m
            for m in markers
            if m["item_id"] == item_id
            and m["media_source_id"] == source_id
            and m["evidence"]["label"].casefold() == label.casefold()
        ]
        marker = {
            "item_id": item_id,
            "media_source_id": source_id,
            "start_time_s": seconds,
            "evidence": {
                "kind": "marker",
                "method": "user_supplied",
                "source_fingerprint": edition["fingerprint"],
                "marker_id": matches[0]["evidence"]["marker_id"]
                if matches
                else secrets.token_hex(12),
                "label": label,
            },
        }
        markers = [m for m in markers if m not in matches]
        if len(markers) >= MAX_MARKERS:
            return _error(
                "marker_limit", "This profile already has 100 markers. Reuse an existing label."
            )
        self.state.set("scene_markers_v1:" + scope, [*markers, marker])
        return {"ok": True, "saved": marker}

    def _play(self, args: Any, connection: tuple, scope: str, who: str) -> dict:
        args = _args(args, {"candidate_id"})
        choice_id = _text(args.get("candidate_id"), 80)
        choice = self.pending.get(choice_id)
        if not choice or choice["scope"] != scope or choice["who"] != who:
            return _error("scene_choice_missing", "Find the scene again in this conversation.")
        if choice["expires"] <= self.clock():
            self.pending.pop(choice_id, None)
            return _error("scene_choice_expired", "Find the scene again; its choice expired.")
        candidate = choice["candidate"]
        with self._resolver(connection) as resolver:
            edition, error = self._edition(
                resolver, candidate["item_id"], candidate["media_source_id"]
            )
            if error:
                return error
            _offset(candidate["start_time_s"], edition["duration_s"])
            expected = candidate["evidence"].get("source_fingerprint")
            if expected is not None and expected != edition["fingerprint"]:
                return _error(
                    "scene_changed", "The edition changed. Find and choose the scene again."
                )
            if choice["lookup"]:
                lookup = choice["lookup"]
                fresh = resolver.search(
                    candidate["item_id"],
                    candidate["media_source_id"],
                    lookup["query"],
                    lookup["language"],
                    lookup["track_index"],
                    limit=10,
                )
                if not fresh["ok"]:
                    return fresh
                if candidate not in fresh["candidates"]:
                    return _error(
                        "scene_changed",
                        "The subtitle match changed. Find and choose the scene again.",
                    )
        played = json.loads(
            tools.tv_play(
                {k: candidate[k] for k in ("item_id", "media_source_id", "start_time_s")},
                ctx=self.ctx,
                manager=self.manager,
            )
        )
        if played.get("ok"):
            played["scene_evidence"] = candidate["evidence"]
        return played


def _timestamp(seconds: float) -> str:
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"
