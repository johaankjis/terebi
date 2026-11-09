"""Deterministic "what should I watch" picker for Hermes Screen.

Jellyfin is the source of truth for the library and watch history; this module
keeps no history, makes no model call and does no I/O of its own. It asks an
injected :class:`~hermes_screen.jellyfin.JellyfinClient` (or anything with the
same three read methods) for candidates and ranks what comes back.

Priority (docs/ARCHITECTURE.md > Picker logic), strictly in this order:

1. ``resume``: started and unfinished items (``get_resume_items``).
2. ``next_up``: Jellyfin's Next Up episodes (``get_next_up``).
3. ``unwatched``: Movies/Videos with ``UserData.Played`` explicitly false
   (``find_items(unwatched_only=True)``).

Every pick is a concrete, playable ``Movie``/``Video``/``Episode`` that appears
once (deduplicated by item id, the highest tier wins). Series and seasons are
never returned. At most :data:`MAX_PICKS` picks come back.

Runtime rule (strict): ``max_minutes`` must be a finite number ``> 0`` and
``<= 1440``. Resume and Next Up items must fit in their *remaining* time, new
(unwatched) items in their full runtime. An item with no known runtime can
never be proven to fit and is never picked. The exact comparison is done by the
client on raw ``RunTimeTicks`` (100 ns ticks), so ``max_minutes`` is passed
through untouched: it is never converted to an int. The client's public
``minutes``/``remaining_minutes`` are *rounded* for display, so this module
never re-applies the limit to them as an exact test; it only drops a record
that is provably over the limit even allowing for that rounding.

Reasons only quote fields the client returned for that item (position,
remaining time, series/episode numbers, Jellyfin genre tags). Nothing is
inferred about taste or past viewing beyond that.

Failures are data. A Jellyfin failure never becomes an empty "nothing to
watch": see :func:`pick_titles` for the exact result shape.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from typing import Any, Protocol

from .jellyfin import JellyfinError

__all__ = ["MAX_PICKS", "PickerClient", "pick_titles"]

MAX_PICKS = 3
MAX_MINUTES_LIMIT = 24 * 60  # same ceiling the Jellyfin client enforces
_FETCH_LIMITS = {"resume": 10, "next_up": 10, "unwatched": 25}  # one client call each
_MAX_LABEL = 80
_MAX_GENRES_IN_REASON = 3

# Failures that say "the server/credentials/user are the problem", not "this
# one endpoint misbehaved". Further calls would only repeat them (and each can
# cost an 8 s timeout), so the picker stops asking.
_GLOBAL_REASONS = frozenset(
    {
        "jellyfin_unreachable",
        "jellyfin_auth",
        "jellyfin_forbidden",
        "jellyfin_config",
        "jellyfin_redirect",
        "jellyfin_user_not_found",
        "jellyfin_user_ambiguous",
        "client_closed",
    }
)

_PLAYABLE = ("Movie", "Video", "Episode")
_NEW_TYPES = ("Movie", "Video")  # Episodes of unstarted shows are not "unwatched picks"
_ALLOWED_TYPES = {"resume": _PLAYABLE, "next_up": ("Episode",), "unwatched": _NEW_TYPES}


class PickerClient(Protocol):
    """The slice of ``JellyfinClient`` the picker uses (keyword-only calls)."""

    def get_resume_items(self, *, max_minutes: float | None, limit: int) -> dict[str, Any]: ...

    def get_next_up(
        self, series_id: str | None = None, *, max_minutes: float | None, limit: int
    ) -> dict[str, Any]: ...

    def find_items(
        self,
        query: str | None = None,
        *,
        item_types: Iterable[str] | None,
        max_minutes: float | None,
        unwatched_only: bool,
        limit: int,
    ) -> dict[str, Any]: ...


# --- public API ---------------------------------------------------------------------


def pick_titles(
    client: PickerClient, max_minutes: float, *, limit: int = MAX_PICKS
) -> dict[str, Any]:
    """Pick up to ``limit`` (1 to 3) titles that fit in ``max_minutes``.

    Makes at most three bounded client calls (resume, Next Up, unwatched) and
    skips the later ones once enough picks exist. Never raises for Jellyfin
    failures or bad arguments.

    Success (``ok`` is True)::

        {"ok": True, "max_minutes": 90.0,
         "picks": [{"item_id", "title", "type", "year", "minutes",
                    "remaining_minutes"?, "source", "why",
                    "series"?, "season"?, "episode"?}, ...],
         "complete": bool,   # False if any needed source failed or was not asked
         "truncated": bool,  # True if a source hit its scan/limit cap: more may exist
         "errors": [{"source", "reason", "hint"}, ...],
         "sources": {name: {"status": "ok" | "error" | "skipped" | "not_attempted", ...}},
         "note"?: str}       # present when picks is empty or the result is partial

    ``picks`` may be empty only when no source failed. If any source failed and
    there is nothing to show, the result is ``{"ok": False, "reason", "hint",
    "errors", "sources", ...}`` carrying the first failure. A partial result
    (some picks, ``complete`` False) lists the failures in ``errors``.

    Invalid arguments give ``{"ok": False, "reason": "invalid_argument", ...}``
    without touching the client.
    """
    maximum = _check_max_minutes(max_minutes)
    if isinstance(maximum, dict):
        return maximum
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PICKS:
        return _invalid(f"limit must be an integer from 1 to {MAX_PICKS}.")

    calls: list[tuple[str, Callable[[], dict[str, Any]], Callable[[dict[str, Any]], Any]]] = [
        (
            "resume",
            lambda: client.get_resume_items(max_minutes=maximum, limit=_FETCH_LIMITS["resume"]),
            _rank_resume,
        ),
        (
            "next_up",
            lambda: client.get_next_up(max_minutes=maximum, limit=_FETCH_LIMITS["next_up"]),
            _rank_next_up,
        ),
        (
            "unwatched",
            lambda: client.find_items(
                item_types=_NEW_TYPES,
                max_minutes=maximum,
                unwatched_only=True,
                limit=_FETCH_LIMITS["unwatched"],
            ),
            _rank_unwatched,
        ),
    ]

    picks: list[dict[str, Any]] = []
    seen: set[str] = set()
    sources: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    truncated = False
    stopped = False

    for name, call, rank in calls:
        if stopped:
            sources[name] = {"status": "not_attempted", "reason": "earlier_server_error"}
            continue
        if len(picks) >= limit:
            sources[name] = {"status": "skipped", "reason": "enough_picks"}
            continue
        try:
            response = call()
        except JellyfinError as exc:
            errors.append({"source": name, "reason": exc.reason, "hint": exc.hint})
            sources[name] = {"status": "error", "reason": exc.reason, "hint": exc.hint}
            stopped = exc.reason in _GLOBAL_REASONS
            continue

        raw_items = response.get("items") if isinstance(response, dict) else None
        if not isinstance(raw_items, list):
            reason = "jellyfin_bad_response"
            hint = f"Jellyfin's {name} answer was not in the expected shape."
            errors.append({"source": name, "reason": reason, "hint": hint})
            sources[name] = {"status": "error", "reason": reason, "hint": hint}
            continue

        candidates, rejected = _candidates(name, raw_items, maximum)
        ordered = sorted(candidates, key=rank)
        duplicates = 0
        for candidate in ordered:
            if candidate["item_id"] in seen:
                duplicates += 1
                continue
            seen.add(candidate["item_id"])
            if len(picks) < limit:
                picks.append(_pick(name, candidate, maximum))
        source_truncated = response.get("truncated") is True
        truncated = truncated or source_truncated
        sources[name] = {
            "status": "ok",
            "candidates": len(candidates),
            "rejected": rejected,
            "duplicates": duplicates,
            "truncated": source_truncated,
            **{
                key: response[key]
                for key in (
                    "scanned",
                    "skipped_unknown_runtime",
                    "skipped_malformed",
                    "skipped_filtered",
                )
                if _is_int(response.get(key))
            },
        }

    complete = not errors
    if not picks and errors:
        first = errors[0]
        return {
            "ok": False,
            "reason": first["reason"],
            "hint": first["hint"],
            "errors": errors,
            "sources": sources,
            "max_minutes": maximum,
            "complete": False,
            "truncated": truncated,
        }

    result: dict[str, Any] = {
        "ok": True,
        "max_minutes": maximum,
        "picks": picks,
        "complete": complete,
        "truncated": truncated,
        "errors": errors,
        "sources": sources,
    }
    if not picks:
        result["note"] = (
            "Nothing I could check fits that time; the library scan hit its limit, "
            "so a longer time or a search may find more."
            if truncated
            else f"Nothing in Jellyfin is proven to fit in {_fmt(maximum)} minutes."
        )
    elif not complete:
        result["note"] = "Partial picks: some Jellyfin lookups failed, see errors."
    return result


# --- validation ---------------------------------------------------------------------


def _invalid(hint: str) -> dict[str, Any]:
    return {"ok": False, "reason": "invalid_argument", "hint": hint}


def _check_max_minutes(value: Any) -> float | dict[str, Any]:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
        or value > MAX_MINUTES_LIMIT
    ):
        return _invalid(
            f"max_minutes must be a number of minutes above 0 and at most {MAX_MINUTES_LIMIT}."
        )
    return float(value)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _pos_int(value: Any) -> int | None:
    return value if _is_int(value) and value > 0 else None


def _opt_int(value: Any) -> int | None:
    return value if _is_int(value) and value >= 0 else None


def _label(value: Any) -> str | None:
    """Server text made safe for a one-line reason: no control chars, bounded."""
    if not isinstance(value, str):
        return None
    text = " ".join("".join(c if c.isprintable() else " " for c in value).split())
    if not text:
        return None
    return text if len(text) <= _MAX_LABEL else text[: _MAX_LABEL - 1].rstrip() + "…"


def _surely_over(shown_minutes: int, limit: float) -> bool:
    """True only if the true duration must exceed ``limit`` whatever the rounding.

    The client shows ``max(1, round(duration))``, so the true duration is at
    least ``shown - 0.5`` (and anything above 0 when it shows 1).
    """
    lower = 0.0 if shown_minutes <= 1 else shown_minutes - 0.5
    return lower > limit


# --- candidates ---------------------------------------------------------------------


def _candidates(
    source: str, raw_items: list[Any], maximum: float
) -> tuple[list[dict[str, Any]], int]:
    """Validate client records for ``source``; return (kept, rejected count)."""
    kept: list[dict[str, Any]] = []
    rejected = 0
    for raw in raw_items:
        candidate = _validate(source, raw, maximum)
        if candidate is None:
            rejected += 1
        else:
            kept.append(candidate)
    return kept, rejected


def _validate(source: str, raw: Any, maximum: float) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    item_id, title, kind = raw.get("item_id"), _label(raw.get("title")), raw.get("type")
    if not isinstance(item_id, str) or not item_id or title is None:
        return None
    if kind not in _ALLOWED_TYPES[source]:
        return None
    played = raw.get("played")
    if source == "unwatched":
        if played is not False:  # absence of evidence is not "unwatched"
            return None
        needed = _pos_int(raw.get("minutes"))
        remaining = None
    else:
        if played is True:
            return None
        remaining = _pos_int(raw.get("remaining_minutes"))
        needed = remaining
    if needed is None or _surely_over(needed, maximum):
        return None
    position_s = _opt_int(raw.get("resume_seconds")) or 0
    if source == "resume" and position_s <= 0:
        return None
    genres = raw.get("genres")
    return {
        "item_id": item_id,
        "title": title,
        "type": kind,
        "year": raw.get("year") if _is_int(raw.get("year")) else None,
        "minutes": _pos_int(raw.get("minutes")),
        "remaining_minutes": remaining,
        "position_s": position_s,
        "genres": [g for g in map(_label, genres) if g] if isinstance(genres, list) else [],
        "series": _label(raw.get("series_name")) if kind == "Episode" else None,
        "season": _opt_int(raw.get("season_number")) if kind == "Episode" else None,
        "episode": _opt_int(raw.get("episode_number")) if kind == "Episode" else None,
    }


# --- ranking (all keys end in title and id, so ties are fully determined) ------------


def _fold(text: str) -> str:
    return " ".join(text.casefold().split())


def _rank_resume(c: dict[str, Any]) -> tuple[Any, ...]:
    # Closest to finished first, then furthest in; then title and id.
    return (c["remaining_minutes"], -c["position_s"], _fold(c["title"]), c["title"], c["item_id"])


def _rank_next_up(c: dict[str, Any]) -> tuple[Any, ...]:
    series = c["series"] or c["title"]
    season, episode = c["season"], c["episode"]
    return (
        _fold(series),
        season is None,
        season or 0,
        episode is None,
        episode or 0,
        _fold(c["title"]),
        c["item_id"],
    )


def _rank_unwatched(c: dict[str, Any]) -> tuple[Any, ...]:
    # Best use of the time window first (longest that still fits), then title and id.
    return (-c["minutes"], _fold(c["title"]), c["title"], c["item_id"])


# --- output -------------------------------------------------------------------------


def _fmt(value: float) -> str:
    return f"{value:g}"


def _name(c: dict[str, Any]) -> str:
    if c["type"] == "Episode" and c["series"]:
        code = ""
        if c["season"] is not None and c["episode"] is not None:
            code = f" S{c['season']}E{c['episode']}"
        return f"{c['series']}{code}: {c['title']}"
    return c["title"]


def _why(source: str, c: dict[str, Any], maximum: float) -> str:
    name, window = _name(c), f"{_fmt(maximum)} min"
    if source == "resume":
        started = f"{c['position_s'] // 60} min in" if c["position_s"] >= 60 else "just started"
        return (
            f"You're {started} on {name} (Jellyfin has it unfinished), "
            f"about {c['remaining_minutes']} min left, within your {window}."
        )
    if source == "next_up":
        extra = f", already {c['position_s'] // 60} min in" if c["position_s"] >= 60 else ""
        return (
            f"Jellyfin lists {name} as your next episode{extra}; "
            f"about {c['remaining_minutes']} min, within your {window}."
        )
    genres = ", ".join(c["genres"][:_MAX_GENRES_IN_REASON])
    tagged = f" It's tagged {genres}." if genres else ""
    return (
        f"Not watched yet in Jellyfin: {name}, about {c['minutes']} min, "
        f"within your {window}.{tagged}"
    )


def _pick(source: str, c: dict[str, Any], maximum: float) -> dict[str, Any]:
    pick: dict[str, Any] = {
        "item_id": c["item_id"],
        "title": c["title"],
        "type": c["type"],
        "year": c["year"],
        "minutes": c["minutes"],
        "source": source,
        "why": _why(source, c, maximum),
    }
    if c["remaining_minutes"] is not None:
        pick["remaining_minutes"] = c["remaining_minutes"]
    if c["type"] == "Episode":
        pick.update(series=c["series"], season=c["season"], episode=c["episode"])
    return pick
