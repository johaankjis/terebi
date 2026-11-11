"""Direct YouTube Cast control with exact-video receiver evidence; optional official search."""

from __future__ import annotations

import ipaddress
import math
import re
import threading
import time
from collections import deque
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from .cast import CastError, PyChromecastSession

APP_YOUTUBE = "233637DE"
MEDIA_NAMESPACE = "urn:x-cast:com.google.cast.media"
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
VERIFY_TIMEOUT_S = 25.0


def error(reason: str, hint: str, **data: Any) -> dict:
    return {"ok": False, "reason": reason, "hint": hint, **data}


def video_id(value: Any) -> str:
    """Accept an ID or a supported HTTPS video link; never fetch user URLs."""
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError
    value = value.strip()
    if VIDEO_ID.fullmatch(value):
        return value
    link = urlsplit(value)
    if link.scheme != "https" or link.username or link.password or link.port or link.fragment:
        raise ValueError
    params = parse_qs(link.query, keep_blank_values=True)
    if any(k in params for k in ("t", "start", "time_continue")):
        raise ValueError  # Timestamp links are outside this slice; do not silently ignore offsets.
    if link.hostname == "youtu.be":
        candidate = link.path.removeprefix("/")
    elif link.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if link.path == "/watch" and len(params.get("v", [])) == 1:
            candidate = params["v"][0]
        elif re.fullmatch(r"/(shorts|embed|live)/[A-Za-z0-9_-]{11}", link.path):
            candidate = link.path.rsplit("/", 1)[1]
        else:
            raise ValueError
    else:
        raise ValueError
    if not VIDEO_ID.fullmatch(candidate):
        raise ValueError
    return candidate


class YouTubeTransport:
    """Use installed PyChromecast controller; YouTube serves media, never a relay."""

    def __init__(self, host: str) -> None:
        self.connection = PyChromecastSession(host, 8009)
        self.cast = self.connection._cast
        self.condition = threading.Condition()
        self.seq = 0
        self.events: deque = deque(maxlen=128)
        owner = self

        class Listener:
            def new_media_status(self, status):
                with owner.condition:
                    owner.seq += 1
                    owner.events.append(
                        {
                            "seq": owner.seq,
                            "app_id": owner.connection.app_id(),
                            "video_id": status.content_id,
                            "state": status.player_state,
                            "idle_reason": status.idle_reason,
                            "session_id": status.media_session_id,
                            "position_s": status.current_time,
                            "title": status.title,
                        }
                    )
                    owner.condition.notify_all()

        self.cast.media_controller.register_status_listener(Listener())

    def app_id(self) -> str | None:
        return self.connection.app_id()

    def snapshot(self) -> dict | None:
        with self.condition:
            return dict(self.events[-1]) if self.events else None

    def mark(self) -> int:
        with self.condition:
            return self.seq

    def events_after(self, mark: int, timeout: float) -> list[dict]:
        with self.condition:
            if self.seq <= mark:
                self.condition.wait(timeout)
            return [dict(e) for e in self.events if e["seq"] > mark]

    def request_status(self) -> None:
        if (
            self.app_id() == APP_YOUTUBE
            and MEDIA_NAMESPACE in self.cast.socket_client.app_namespaces
        ):
            self.cast.media_controller.update_status()

    def load(self, requested: str) -> None:
        from pychromecast.controllers.youtube import TimeoutYouTubeSession, YouTubeController

        class BoundedSession(TimeoutYouTubeSession):
            # The upstream session can recursively rebind after HTTP 400/404. Bound
            # total requests as well as each request's existing socket timeout.
            def __init__(self, screen_id):
                super().__init__(screen_id, timeout=5)
                self.budget = 6

            def _do_post(self, *args, **kwargs):
                self.budget -= 1
                if self.budget < 0:
                    raise TimeoutError
                return super()._do_post(*args, **kwargs)

        class Controller(YouTubeController):
            def start_session_if_none(self):
                if not (self._screen_id and self._session):
                    self.update_screen_id()
                    if not self._screen_id:
                        raise TimeoutError
                    self._session = BoundedSession(self._screen_id)

        controller = Controller(timeout=5)
        self.cast.register_handler(controller)
        controller.play_video(requested)

    def _command(self, kind: str, session_id: int) -> None:
        if (
            self.app_id() != APP_YOUTUBE
            or MEDIA_NAMESPACE not in self.cast.socket_client.app_namespaces
        ):
            raise CastError("not_our_playback", "The TV changed apps; nothing was controlled.")
        self.cast.media_controller.send_message({"type": kind, "mediaSessionId": session_id})

    def pause(self, session_id: int) -> None:
        self._command("PAUSE", session_id)

    def resume(self, session_id: int) -> None:
        self._command("PLAY", session_id)

    def close(self) -> None:
        self.connection.close()  # Preserve the receiver; no CLOSE/STOP.


class YouTubePlayback:
    """Context-local ownership for safe pause; a launch response never means playing."""

    def __init__(self, transport_factory=YouTubeTransport, clock=time.monotonic) -> None:
        self.factory = transport_factory
        self.clock = clock
        self.lock = threading.Lock()
        self.owned: tuple | None = None
        self.owned_host: str | None = None

    def _verify(self, transport, mark, requested, state, session_id=None):
        deadline = self.clock() + VERIFY_TIMEOUT_S
        last = None
        while self.clock() < deadline:
            for event in transport.events_after(mark, min(0.25, deadline - self.clock())):
                mark = max(mark, event["seq"])
                last = event
                if (
                    event.get("app_id") == APP_YOUTUBE
                    and event.get("video_id") == requested
                    and event.get("state") == "IDLE"
                    and event.get("idle_reason") == "ERROR"
                ):
                    return error(
                        "youtube_video_unavailable",
                        "The receiver reported an error for this video. Check the TV for "
                        "availability, sign-in, age or region restrictions.",
                        verified=False,
                        video_id=requested,
                        outcome="app_opened",
                    )
                if (
                    event.get("app_id") == APP_YOUTUBE
                    and transport.app_id() == APP_YOUTUBE
                    and event.get("video_id") == requested
                    and event.get("state") == state
                    and type(event.get("session_id")) is int
                    and (session_id is None or event["session_id"] == session_id)
                ):
                    self.owned = (requested, event["session_id"])
                    position = event.get("position_s")
                    return {
                        "ok": True,
                        "verified": True,
                        "evidence": "receiver_exact_video",
                        "video_id": requested,
                        "state": state,
                        "media_session_id": event["session_id"],
                        "position_s": position
                        if isinstance(position, (int, float)) and math.isfinite(position)
                        else None,
                        "title": str(event.get("title") or "")[:200],
                    }
            if transport.app_id() != APP_YOUTUBE:
                break
        return error(
            "youtube_playback_unverified",
            "YouTube did not confirm the requested video/state. Check the TV for ads, "
            "sign-in, age/region restrictions, or an unavailable/private video.",
            verified=False,
            video_id=requested,
            outcome="app_opened" if transport.app_id() == APP_YOUTUBE else "failure",
            reported_state=last.get("state") if last else None,
        )

    def call(self, host: str, requested: str | None = None, *, pause: bool = False) -> dict:
        try:
            ipaddress.ip_address(host)
        except (ValueError, TypeError):
            return error("not_configured", "Set chromecast_host to the Chromecast's LAN IP.")
        if not self.lock.acquire(timeout=1):
            return error("youtube_busy", "Another YouTube action is running. Retry shortly.")
        transport = None
        try:
            transport = self.factory(host)
            transport.request_status()
            mark = transport.mark()
            # Obtain a fresh snapshot before deciding whether another app/video is ours.
            transport.events_after(mark, 0.5)
            current = transport.snapshot()
            if pause:
                if (
                    not self.owned
                    or self.owned_host != host
                    or not current
                    or transport.app_id() != APP_YOUTUBE
                    or (current.get("video_id"), current.get("session_id")) != self.owned
                ):
                    return error(
                        "not_our_playback", "Only pause YouTube started by this plugin context."
                    )
                requested, sid = self.owned
                mark = transport.mark()
                if current.get("state") == "PAUSED":
                    transport.request_status()
                else:
                    transport.pause(sid)
                return self._verify(transport, mark, requested, "PAUSED", sid)
            mark = transport.mark()
            if (
                current
                and transport.app_id() == APP_YOUTUBE
                and current.get("video_id") == requested
                and current.get("state") in {"PLAYING", "PAUSED"}
            ):
                if current["state"] == "PAUSED":
                    transport.resume(current["session_id"])
                else:
                    transport.request_status()
            else:
                self.owned = None
                transport.load(requested)
                transport.request_status()
            result = self._verify(transport, mark, requested, "PLAYING")
            if result["ok"]:
                self.owned_host = host
            return result
        except CastError as exc:
            return exc.to_dict()
        except Exception:
            return error(
                "youtube_control_failed",
                "YouTube control failed. Check the TV and retry; video playback is unverified.",
                verified=False,
                outcome="app_opened"
                if transport and transport.app_id() == APP_YOUTUBE
                else "failure",
            )
        finally:
            if transport:
                try:
                    transport.close()
                except Exception:
                    pass
            self.lock.release()


def search(query: Any, key: str | None, *, client_factory=httpx.Client) -> dict:
    """Search only the official Data API; never scrape YouTube pages."""
    if not isinstance(query, str) or not query.strip() or len(query) > 200:
        return error("invalid_argument", "Use a title query of 1–200 characters.")
    if not key:
        return error(
            "youtube_search_not_configured",
            "Add YOUTUBE_API_KEY in Hermes secrets for title search. Direct links need no key.",
        )
    try:
        with client_factory(timeout=httpx.Timeout(8), follow_redirects=False) as client:
            response = client.get(
                "https://www.googleapis.com/youtube/v3/search",
                headers={"X-Goog-Api-Key": key},
                params={
                    "part": "snippet",
                    "type": "video",
                    "q": query.strip(),
                    "maxResults": 5,
                    "safeSearch": "moderate",
                },
            )
        if response.status_code in {401, 403, 429}:
            return error(
                "youtube_search_access",
                "Check the API key, enabled YouTube Data API v3, "
                "key restrictions and quota. Direct links still work.",
            )
        if response.status_code != 200 or len(response.content) > 128000:
            return error(
                "youtube_search_unavailable", "YouTube search failed. Retry or use a direct link."
            )
        data = response.json()
        if not isinstance(data.get("items"), list):
            raise ValueError
        picks = []
        import html

        for item in data["items"][:5]:
            vid = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            if not isinstance(vid, str) or not VIDEO_ID.fullmatch(vid):
                continue
            if not all(isinstance(snippet.get(k), str) for k in ("title", "channelTitle")):
                continue
            picks.append(
                {
                    "choice": len(picks) + 1,
                    "video_id": vid,
                    "title": html.unescape(snippet["title"])[:200],
                    "channel": html.unescape(snippet["channelTitle"])[:120],
                }
            )
        return {
            "ok": True,
            "candidates": picks,
            "needs_choice": len(picks) > 1,
            "hint": "Show titles and channels; ask the user to choose before playback. "
            "Availability on the TV is confirmed only during playback.",
        }
    except Exception:
        return error(
            "youtube_search_unavailable", "YouTube search failed. Retry or use a direct link."
        )
