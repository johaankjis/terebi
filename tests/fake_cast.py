"""A scripted fake Chromecast for tests: device state survives across connections.

Behaves like the Default Media Receiver as observed on hardware (fresh status
after LOAD, BUFFERING then PLAYING, PAUSED for the same media session) and can
be told to misbehave. Nothing touches the network.
"""

from __future__ import annotations

import threading
import time
from typing import Any

BACKDROP = "E8C28D3C"
APP_DEFAULT_MEDIA_RECEIVER = "CC1AD845"


def _cast_module() -> Any:
    from hermes_screen import cast

    return cast


class FakeClock:
    def __init__(self) -> None:
        self.now = 5000.0
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            return self.now

    def advance(self, seconds: float) -> None:
        with self._lock:
            self.now += max(seconds, 0.0)


class FakeReceiver:
    def __init__(self, clock: FakeClock, cast_module: Any = None) -> None:
        # cast_module: the plugin's own hermes_screen.cast (differs under a namespaced loader)
        self.cast = cast_module if cast_module is not None else _cast_module()
        self.clock = clock
        self.app_id: str | None = BACKDROP
        self.content_id: str | None = None
        self.session_id = 0
        self.state: str | None = None
        self.idle_reason: str | None = None
        self.position = 0.0
        self.on_load = (  # play | from_zero | stall | error | load_failed | silent | other
            "play"
        )
        self.on_pause = "ok"  # ok | ignore | reject
        self.on_play = "ok"
        self.on_seek = "ok"  # ok | stall | ignore | reject | ok_noposition
        self.unreachable = False
        self.launch_fails = False
        self.commands: list[tuple[Any, ...]] = []
        self.connections = 0
        self.open_sessions: list[FakeSession] = []
        # start offset the last LOAD was told to honor (None: ordinary launch)
        self.last_load_start_time_s: float | None = None

    def connect(self, host: str, port: int) -> FakeSession:
        self.commands.append(("connect", host, port))
        if self.unreachable:
            raise self.cast.CastError("cast_unreachable", "Couldn't reach the Chromecast.")
        self.connections += 1
        session = FakeSession(self)
        self.open_sessions.append(session)
        return session

    def someone_else_casts(self, url: str = "http://other.test/movie.mp4") -> None:
        self.app_id = APP_DEFAULT_MEDIA_RECEIVER
        self.content_id = url
        self.session_id += 1
        self.state = "PLAYING"


class FakeSession:
    def __init__(self, receiver: FakeReceiver) -> None:
        self.r = receiver
        self.events: list[Any] = []
        self.closed = False
        if receiver.app_id == APP_DEFAULT_MEDIA_RECEIVER and receiver.state is not None:
            self._push()  # media channel connect triggers a status, like pychromecast

    # helpers
    def _push(self, kind: str = "status", **override: Any) -> None:
        fields: dict[str, Any] = {
            "content_id": self.r.content_id,
            "session_id": self.r.session_id or None,
            "player_state": self.r.state,
            "idle_reason": self.r.idle_reason,
            "position_s": self.r.position,
            "duration_s": 596.459,
        }
        if kind != "status":
            fields = {}
        fields.update(override)
        event = self.r.cast.MediaEvent(seq=len(self.events) + 1, kind=kind, **fields)
        self.events.append(event)

    # CastSession protocol
    def app_id(self) -> str | None:
        return self.r.app_id

    def mark(self) -> int:
        return len(self.events)

    def events_after(self, seq: int, timeout: float) -> list[Any]:
        fresh = [e for e in self.events if e.seq > seq]
        if not fresh:
            self.r.clock.advance(timeout)
            time.sleep(0.001)  # yield like a real wait when the caller uses a real clock
        return fresh

    def request_status(self) -> None:
        self.r.commands.append(("GET_STATUS",))
        if self.r.app_id == APP_DEFAULT_MEDIA_RECEIVER and self.r.on_load != "silent":
            self._push()

    def launch_receiver(self) -> None:
        self.r.commands.append(("LAUNCH",))
        if self.r.launch_fails:
            raise self.r.cast.CastError(
                "cast_launch_failed", "The Chromecast didn't open its media player."
            )
        if self.r.app_id != APP_DEFAULT_MEDIA_RECEIVER:
            self.r.app_id = APP_DEFAULT_MEDIA_RECEIVER
            self.r.content_id = None
            self.r.state = None

    def load(
        self, url: str, *, title: str, duration_s: float | None, start_time_s: float | None = None
    ) -> None:
        self.r.commands.append(("LOAD", url, title))
        self.r.last_load_start_time_s = start_time_s
        behavior = self.r.on_load
        if behavior == "reject":
            raise self.r.cast.CastError(
                "cast_command_failed", "The Chromecast didn't accept the video."
            )
        if behavior == "silent":
            return
        if behavior == "load_failed":
            self._push("load_failed")
            return
        if behavior == "other":
            self.r.content_id, self.r.state = "http://elsewhere.test/x.mp4", "PLAYING"
            self.r.session_id += 1
            self._push()
            return
        self.r.content_id = url
        self.r.session_id += 1
        start = float(start_time_s) if start_time_s is not None else 0.0
        self.r.state, self.r.idle_reason, self.r.position = "IDLE", None, start
        self._push()
        if behavior == "stall":
            return
        if behavior == "error":
            self.r.idle_reason = "ERROR"
            self._push()
            return
        if behavior == "from_zero":  # receiver ignored the sender-provided start
            self.r.state, self.r.position = "PLAYING", 0.2
            self._push()
            return
        self.r.state = "BUFFERING"
        self._push()
        self.r.state, self.r.position = "PLAYING", start + 0.2
        self._push()

    def seek(self, session_id: int, position_s: float) -> None:
        self.r.commands.append(("SEEK", session_id, position_s))
        behavior = self.r.on_seek
        if behavior == "reject":
            self._push("command_failed")
            return
        if behavior == "ignore" or session_id != self.r.session_id:
            return  # a wrong media session learns nothing, like on hardware
        if behavior == "ok_noposition":
            self.r.state = "PLAYING"
            self._push(position_s=None)
            return
        if behavior == "wrongpos":  # PLAYING acked, but the position never moves
            self.r.state = "PLAYING"
            self._push()
            return
        if behavior == "stall":
            self.r.state = "BUFFERING"  # moved but never reports PLAYING
            self.r.position = float(position_s)
            self._push()
            return
        self.r.state, self.r.position = "PLAYING", float(position_s)
        self._push()

    def pause(self, session_id: int) -> None:
        self.r.commands.append(("PAUSE", session_id))
        if self.r.on_pause == "reject":
            self._push("command_failed")
            return
        if self.r.on_pause == "ignore" or session_id != self.r.session_id:
            return
        self.r.state, self.r.position = "PAUSED", 14.462817
        self._push()

    def play(self, session_id: int) -> None:
        self.r.commands.append(("PLAY", session_id))
        if self.r.on_play == "reject":
            self._push("command_failed")
            return
        if self.r.on_play == "ok" and session_id == self.r.session_id:
            self.r.state = "PLAYING"
            self._push()

    def close(self) -> None:
        self.closed = True
