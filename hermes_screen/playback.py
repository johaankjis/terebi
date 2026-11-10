"""Play and pause one Jellyfin item on the configured Chromecast, with proof.

:class:`CastPlaybackManager` is created once per plugin context (Hermes profile
registration) and owns that context's relay and "what did we start" state;
there is no module-level state. Calls are serialized by a lock.

Evidence rules (docs/DECISIONS.md D-014):

* ``tv_play`` succeeds only when, after the LOAD it sent, the receiver itself
  reports the *exact* freshly minted capability URL as ``PLAYING``. A LOAD that
  was accepted, a launched app, sender-side metadata or a title never count.
* ``tv_pause`` only touches media whose receiver-reported URL is the capability
  we minted and whose media session is the one we saw playing; it then requires
  a fresh ``PAUSED`` for that same session. Anything else is left alone.
* Timeouts report what was seen (app opened, our media loading, some other
  media playing) instead of guessing.
"""

from __future__ import annotations

import ipaddress
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from .cast import (
    APP_DEFAULT_MEDIA_RECEIVER,
    CAST_PORT,
    CastConnector,
    CastError,
    CastSession,
    MediaEvent,
    connect_chromecast,
)
from .relay import MediaRelay, RelayError, parse_bind, ttl_for

__all__ = ["CastPlaybackManager", "CastSettings", "parse_cast_settings"]

PLAY_TIMEOUT_S = 25.0
PAUSE_TIMEOUT_S = 8.0
STATUS_TIMEOUT_S = 5.0
LOCK_TIMEOUT_S = 60.0
POLL_S = 1.0
_FAILED_IDLE = frozenset({"ERROR", "CANCELLED", "INTERRUPTED", "FINISHED"})


@dataclass(frozen=True)
class CastSettings:
    host: str
    port: int
    advertised_base: str
    bind: tuple[str, int]


def parse_cast_settings(
    host: str | None, advertised_base: str | None, bind: str | None
) -> CastSettings:
    """Validate the three Cast settings; raises :class:`CastError` with a hint."""
    missing = [
        name
        for name, value in (
            ("chromecast_host", host),
            ("cast_media_base_url", advertised_base),
            ("cast_relay_bind", bind),
        )
        if not value
    ]
    if missing:
        raise CastError(
            "not_configured",
            "Set " + ", ".join(missing) + " in the Hermes Screen plugin settings "
            "(Chromecast IP, the LAN URL the Chromecast uses to reach this host, and the "
            "local listen address, e.g. 0.0.0.0:8765).",
        )
    assert host and advertised_base and bind
    try:
        ipaddress.ip_address(host)
    except ValueError:
        raise CastError(
            "cast_config", "chromecast_host must be the Chromecast's IP address."
        ) from None
    try:
        bind_addr = parse_bind(bind)
    except RelayError as exc:
        raise CastError(exc.reason, exc.hint) from None
    return CastSettings(host, CAST_PORT, _parse_base(advertised_base), bind_addr)


def _parse_base(value: str) -> str:
    hint = "Set cast_media_base_url like http://192.168.1.20:8765 (no path)."
    try:
        parts = urlsplit(value.strip())
        port = parts.port
    except ValueError:
        raise CastError("cast_config", hint) from None
    if (
        parts.scheme != "http"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or parts.path not in ("", "/")
        or any(c.isspace() for c in value.strip())
    ):
        raise CastError("cast_config", hint)
    host = parts.hostname
    if ":" in host:
        host = f"[{host}]"
    return f"http://{host}" + (f":{port}" if port else "")


@dataclass
class _Owned:
    """What this context started: the exact capability URL and media session."""

    item_id: str
    title: str
    host: str
    port: int
    cap: Any
    duration_s: float | None
    session_id: int | None = None


@dataclass
class _Outcome:
    verified: bool = False
    event: MediaEvent | None = None
    failure: str | None = None
    saw_ours: bool = False
    other_media: bool = False
    last_state: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _error(reason: str, hint: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "reason": reason, "hint": hint, **extra}


class CastPlaybackManager:
    """Per-context owner of the media relay and our Cast playback state."""

    def __init__(
        self,
        *,
        connector: CastConnector | None = None,
        relay: MediaRelay | None = None,
        clock: Callable[[], float] = time.monotonic,
        play_timeout_s: float | None = None,
        pause_timeout_s: float | None = None,
        status_timeout_s: float | None = None,
        lock_timeout_s: float | None = None,
        poll_s: float | None = None,
    ) -> None:
        # None means the module default, read now (tests may shorten them).
        self._connector = connector  # None: connect_chromecast, looked up per call
        self._relay = relay if relay is not None else MediaRelay()
        self._clock = clock
        self._play_timeout = PLAY_TIMEOUT_S if play_timeout_s is None else play_timeout_s
        self._pause_timeout = PAUSE_TIMEOUT_S if pause_timeout_s is None else pause_timeout_s
        self._status_timeout = STATUS_TIMEOUT_S if status_timeout_s is None else status_timeout_s
        self._lock_timeout = LOCK_TIMEOUT_S if lock_timeout_s is None else lock_timeout_s
        self._poll = POLL_S if poll_s is None else poll_s
        self._lock = threading.Lock()
        self._owned: _Owned | None = None
        self._closed = False

    # -- public API ---------------------------------------------------------------

    def play(
        self,
        settings: CastSettings,
        source: dict[str, Any],
        upstream_url: str,
        auth_header: str,
    ) -> dict[str, Any]:
        """Cast one validated Jellyfin item and verify it is PLAYING."""
        return self._serialized(lambda: self._play(settings, source, upstream_url, auth_header))

    def pause(self) -> dict[str, Any]:
        """Pause what this context started, and verify PAUSED (idempotent)."""
        return self._serialized(self._pause)

    def release(self) -> None:
        """Revoke the media link and stop the relay now; the tools stay usable.

        Does not touch the receiver (whatever is buffered may play on briefly).
        """
        self._shutdown(disable=False)

    def close(self) -> None:
        """Like :meth:`release`, then refuse further calls. Used by ``ctx.on_unload``.

        Safe to call more than once. Bounded: waits at most 5 s for a running call,
        then revokes anyway (the relay is thread-safe).
        """
        self._shutdown(disable=True)

    def _shutdown(self, *, disable: bool) -> None:
        acquired = self._lock.acquire(timeout=5.0)
        try:
            if disable:
                self._closed = True
            self._owned = None
            self._relay.revoke()
        finally:
            if acquired:
                self._lock.release()

    # -- internals ------------------------------------------------------------------

    def _serialized(self, action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        if not self._lock.acquire(timeout=self._lock_timeout):
            return _error("busy", "Another TV command is still running. Try again in a moment.")
        try:
            if self._closed:
                return _error("not_configured", "Hermes Screen was unloaded. Reload the plugin.")
            return action()
        except CastError as exc:
            return exc.to_dict()
        except RelayError as exc:
            return _error(exc.reason, exc.hint)
        except Exception:
            return _error(
                "cast_failed", "Something went wrong talking to the Chromecast. Try again."
            )
        finally:
            self._lock.release()

    def _connect(self, host: str, port: int) -> CastSession:
        connector = self._connector or connect_chromecast
        return connector(host, port)

    def _drop(self) -> None:
        self._owned = None
        self._relay.revoke()

    def _play(
        self,
        settings: CastSettings,
        source: dict[str, Any],
        upstream_url: str,
        auth_header: str,
    ) -> dict[str, Any]:
        item_id, title = source["item_id"], source["title"]
        session = self._connect(settings.host, settings.port)
        try:
            repeat = self._repeat_play(session, settings, item_id)
            if repeat is not None:
                return repeat
            cap = self._relay.mint(
                bind=settings.bind,
                advertised_base=settings.advertised_base,
                item_id=item_id,
                upstream_url=upstream_url,
                auth_header=auth_header,
                ttl_s=ttl_for(source.get("duration_s")),
            )
            owned = _Owned(
                item_id, title, settings.host, settings.port, cap, source.get("duration_s")
            )
            self._owned = owned
            try:
                session.launch_receiver()
                mark = session.mark()
                session.load(cap.media_url, title=title, duration_s=owned.duration_s)
                outcome = self._await(session, cap.media_url, mark, "PLAYING", None)
            except BaseException:
                self._drop()
                raise
            return self._play_result(session, owned, outcome, action="started")
        finally:
            session.close()

    def _repeat_play(
        self, session: CastSession, settings: CastSettings, item_id: str
    ) -> dict[str, Any] | None:
        """Same item, same device and our capability still live: don't restart it."""
        owned, cap = self._owned, self._relay.current()
        if (
            owned is None
            or cap is None
            or cap is not owned.cap
            or owned.item_id != item_id
            or (owned.host, owned.port) != (settings.host, settings.port)
            or not cap.media_url.startswith(settings.advertised_base + "/")
            or self._relay.bound_to != settings.bind
        ):
            return None
        event = self._fresh_status(session)
        if event is None or not self._is_ours(event, owned):
            return None
        owned.session_id = event.session_id
        if event.player_state == "PLAYING":
            return self._success(owned, event, action="already_playing")
        if event.player_state == "PAUSED" and event.session_id is not None:
            mark = session.mark()
            session.play(event.session_id)
            outcome = self._await(session, cap.media_url, mark, "PLAYING", event.session_id)
            return self._play_result(session, owned, outcome, action="resumed")
        if event.player_state == "BUFFERING":
            mark = session.mark()
            outcome = self._await(session, cap.media_url, mark, "PLAYING", event.session_id)
            return self._play_result(session, owned, outcome, action="already_playing")
        return None  # IDLE/ended: load it again with a new capability

    def _play_result(
        self, session: CastSession, owned: _Owned, outcome: _Outcome, *, action: str
    ) -> dict[str, Any]:
        item = {"item_id": owned.item_id, "title": owned.title}
        if outcome.verified and outcome.event is not None:
            owned.session_id = outcome.event.session_id
            return self._success(owned, outcome.event, action=action)
        if action != "started":
            # Resume/re-check of media we already confirmed: it is still loaded, so
            # keep its link (bounded by the TTL) and report without guessing.
            return _error(
                "playback_unverified",
                "I asked the Chromecast to play but it did not confirm "
                f"(last state: {outcome.last_state or 'unknown'}). Don't assume it is playing.",
                evidence=outcome.failure or "timeout",
                item=item,
            )
        if outcome.failure is not None:
            self._drop()
            return _error(
                "playback_failed",
                "The Chromecast could not play this video "
                f"({outcome.failure}). Check that this host is reachable at "
                "cast_media_base_url from the Chromecast, then try again.",
                evidence=outcome.failure,
                item=item,
            )
        if outcome.saw_ours:
            # The receiver has our exact media but did not report PLAYING in time.
            # Keep the capability (bounded by its TTL) so it can still start.
            return _error(
                "playback_unverified",
                "The Chromecast loaded this video but did not confirm it is playing yet "
                f"(last state: {outcome.last_state or 'unknown'}). Don't assume it is "
                "playing; try tv_play again in a moment to re-check.",
                evidence="loading",
                item=item,
            )
        self._drop()
        if outcome.other_media:
            evidence = "unknown_title_playing"
            hint = (
                "Something is playing on the Chromecast, but it is not the video I sent, "
                "so playback is not confirmed."
            )
        elif session.app_id() == APP_DEFAULT_MEDIA_RECEIVER:
            evidence = "app_opened"
            hint = (
                "The Chromecast opened its media player but never reported this video. "
                "It may be unable to reach cast_media_base_url from the Chromecast."
            )
        else:
            evidence = "no_receiver_status"
            hint = "The Chromecast did not report any status for this video."
        return _error("playback_unverified", hint, evidence=evidence, item=item)

    def _success(self, owned: _Owned, event: MediaEvent, *, action: str) -> dict[str, Any]:
        cap = owned.cap
        remaining = max(cap.expires_at - self._clock(), 0.0)
        return {
            "ok": True,
            "state": "playing",
            "verified": True,
            "action": action,
            "item": {"item_id": owned.item_id, "title": owned.title},
            "position_s": _round(event.position_s),
            "duration_s": _round(event.duration_s or owned.duration_s),
            "relay_expires_in_minutes": math.ceil(remaining / 60),
            "note": (
                "The Chromecast reported this exact item playing. TV power and input "
                "were not checked. The stream link stops working after "
                "relay_expires_in_minutes."
            ),
        }

    def _pause(self) -> dict[str, Any]:
        owned, cap = self._owned, self._relay.current()
        if owned is None or cap is None or cap is not owned.cap:
            self._owned = None
            return _error(
                "nothing_playing",
                "Nothing I started is playing on the Chromecast, so there is nothing for me "
                "to pause. I only pause what tv_play started.",
            )
        session = self._connect(owned.host, owned.port)
        try:
            if session.app_id() != APP_DEFAULT_MEDIA_RECEIVER:
                return self._not_ours()
            event = self._fresh_status(session)
            if event is None:
                return _error(
                    "cast_status_unavailable",
                    "The Chromecast didn't report what it is playing, so I didn't pause it.",
                )
            if not self._is_ours(event, owned):
                return self._not_ours()
            owned.session_id = event.session_id
            if event.player_state == "PAUSED":
                return self._paused(owned, event, already=True)
            if event.player_state not in ("PLAYING", "BUFFERING") or event.session_id is None:
                return _error(
                    "playback_ended",
                    "That video is no longer playing on the Chromecast.",
                    item={"item_id": owned.item_id, "title": owned.title},
                )
            mark = session.mark()
            session.pause(event.session_id)
            outcome = self._await(session, cap.media_url, mark, "PAUSED", event.session_id)
            if outcome.verified and outcome.event is not None:
                return self._paused(owned, outcome.event, already=False)
            return _error(
                "pause_unverified",
                "I asked the Chromecast to pause but it did not confirm "
                f"(last state: {outcome.last_state or 'unknown'}). It may still be playing.",
                evidence=outcome.failure or "timeout",
                item={"item_id": owned.item_id, "title": owned.title},
            )
        finally:
            session.close()

    def _paused(self, owned: _Owned, event: MediaEvent, *, already: bool) -> dict[str, Any]:
        return {
            "ok": True,
            "state": "paused",
            "verified": True,
            "already_paused": already,
            "item": {"item_id": owned.item_id, "title": owned.title},
            "position_s": _round(event.position_s),
        }

    @staticmethod
    def _not_ours() -> dict[str, Any]:
        return _error(
            "not_our_playback",
            "The Chromecast is showing something I didn't start, so I left it alone.",
        )

    @staticmethod
    def _is_ours(event: MediaEvent, owned: _Owned) -> bool:
        if event.content_id != owned.cap.media_url:
            return False
        return owned.session_id is None or event.session_id == owned.session_id

    def _fresh_status(self, session: CastSession) -> MediaEvent | None:
        """Latest receiver media status on this call's new connection, or ``None``."""
        if session.app_id() != APP_DEFAULT_MEDIA_RECEIVER:
            return None
        seq = 0
        latest: MediaEvent | None = None
        requested_after = session.mark()
        session.request_status()
        deadline = self._clock() + self._status_timeout
        while True:
            remaining = deadline - self._clock()
            if remaining <= 0:
                return latest
            for event in session.events_after(seq, min(self._poll, remaining)):
                seq = max(seq, event.seq)
                if event.kind == "status":
                    latest = event
            if latest is not None and latest.seq > requested_after:
                return latest
            if latest is not None:
                session.request_status()
                requested_after = session.mark()

    def _await(
        self,
        session: CastSession,
        url: str,
        after_seq: int,
        want: str,
        session_id: int | None,
    ) -> _Outcome:
        """Wait for a fresh receiver status: our exact URL (and session) in ``want``."""
        outcome = _Outcome()
        timeout = self._play_timeout if want == "PLAYING" else self._pause_timeout
        deadline = self._clock() + timeout
        seq, last_poll = after_seq, self._clock()
        while True:
            remaining = deadline - self._clock()
            if remaining <= 0:
                return outcome
            events = session.events_after(seq, min(self._poll, remaining))
            for event in events:
                seq = max(seq, event.seq)
                if event.kind in ("load_failed", "command_failed"):
                    outcome.failure = event.kind
                    return outcome
                if event.kind != "status":
                    continue
                if event.content_id == url and (
                    session_id is None or event.session_id == session_id
                ):
                    if (
                        session_id is None
                        and outcome.last_state not in ("BUFFERING", "PLAYING")
                        and event.player_state == "IDLE"
                        and event.idle_reason == "INTERRUPTED"
                    ):
                        continue
                    outcome.saw_ours = True
                    outcome.last_state = event.player_state
                    if event.player_state == want:
                        outcome.verified, outcome.event = True, event
                        return outcome
                    if event.player_state == "IDLE" and event.idle_reason in _FAILED_IDLE:
                        outcome.failure = f"receiver_{event.idle_reason.lower()}"
                        return outcome
                elif event.content_id is not None and event.player_state in (
                    "PLAYING",
                    "BUFFERING",
                    "PAUSED",
                ):
                    outcome.other_media = True
                    if outcome.saw_ours:
                        outcome.failure = "replaced"
                        return outcome
            if not events and self._clock() - last_poll >= self._poll:
                session.request_status()
                last_poll = self._clock()


def _round(value: float | None) -> float | None:
    return round(value, 1) if isinstance(value, int | float) else None
