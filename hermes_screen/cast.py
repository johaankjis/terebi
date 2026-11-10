"""Direct Google Cast control of one configured Chromecast.

The rest of the plugin talks to :class:`CastSession`, a tiny protocol that tests
replace with a fake. :func:`connect_chromecast` is the real implementation on
top of ``pychromecast`` (verified on a Chromecast Gen 2 with 14.1.1, see
docs/HARDWARE.md). Design points:

* Direct connection to the configured IP and port 8009. No mDNS/zeroconf
  discovery is used. ``CastInfo`` is built with an explicit cast type so
  pychromecast never calls ``get_cast_type`` (which has a hidden 30 s HTTP
  timeout). Connection uses one try with a bounded socket timeout.
* A fresh connection per tool call, closed afterwards. Disconnecting does not
  stop the receiver app, so playback continues. There is no background watcher.
* Only receiver-reported media statuses are evidence; everything is exposed as
  ordered :class:`MediaEvent` records so callers can require *fresh* status.
* Status requests and transport commands are only sent when the Default Media
  Receiver is the running app, so a status check never launches or disturbs
  another app.
* pychromecast debug logs include media status payloads (the capability URL);
  a filter redacts capability paths in every ``pychromecast`` logger.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from .relay import redact

__all__ = [
    "APP_DEFAULT_MEDIA_RECEIVER",
    "CastError",
    "CastSession",
    "MediaEvent",
    "connect_chromecast",
    "install_log_redaction",
]

APP_DEFAULT_MEDIA_RECEIVER = "CC1AD845"
CAST_PORT = 8009
CONNECT_TIMEOUT_S = 6.0
LAUNCH_TIMEOUT_S = 10.0
MAX_EVENTS = 256
MEDIA_NAMESPACE = "urn:x-cast:com.google.cast.media"


class CastError(Exception):
    """A Cast failure with a stable reason and a human hint (never raw errors)."""

    def __init__(self, reason: str, hint: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.hint = hint

    def to_dict(self) -> dict[str, Any]:
        return {"ok": False, "reason": self.reason, "hint": self.hint}


@dataclass(frozen=True)
class MediaEvent:
    """One receiver report. ``kind`` is ``status``, ``load_failed`` or ``command_failed``."""

    seq: int
    kind: str
    content_id: str | None = None
    session_id: int | None = None
    player_state: str | None = None
    idle_reason: str | None = None
    position_s: float | None = None
    duration_s: float | None = None


class CastSession(Protocol):
    """One open connection to the Chromecast for the duration of a tool call."""

    def app_id(self) -> str | None: ...

    def mark(self) -> int:
        """Sequence number of the latest event; later events are fresh."""
        ...

    def events_after(self, seq: int, timeout: float) -> list[MediaEvent]:
        """Events newer than ``seq``, waiting up to ``timeout`` for at least one."""
        ...

    def request_status(self) -> None:
        """Ask for a media status, only if the Default Media Receiver is running."""
        ...

    def launch_receiver(self) -> None: ...

    def load(
        self,
        url: str,
        *,
        title: str,
        duration_s: float | None,
        start_time_s: float | None = None,
    ) -> None: ...

    def seek(self, session_id: int, position_s: float) -> None:
        """Move this media session to ``position_s`` seconds and start playing there."""
        ...

    def pause(self, session_id: int) -> None: ...

    def play(self, session_id: int) -> None: ...

    def close(self) -> None: ...


CastConnector = Callable[[str, int], CastSession]


# --- log redaction -------------------------------------------------------------------------


class _RedactCapabilities(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        cleaned = redact(message)
        if cleaned != message:
            record.msg, record.args = cleaned, None
        if record.exc_info:
            text = logging.Formatter().formatException(record.exc_info)
            record.exc_text = redact(text)
        return True


_REDACT_FILTER = _RedactCapabilities()
# pychromecast creates some loggers lazily (socket client, controllers), so the
# known names are created up front; later getLogger() calls return these objects.
_PYCHROMECAST_LOGGERS = (
    "pychromecast",
    "pychromecast.socket_client",
    "pychromecast.controllers",
    "pychromecast.controllers.media",
    "pychromecast.controllers.receiver",
    "pychromecast.controllers.heartbeat",
    "pychromecast.dial",
    "pychromecast.discovery",
    "pychromecast.response_handler",
    "pychromecast.quick_play",
)


def install_log_redaction() -> None:
    """Attach the capability-redacting filter to every ``pychromecast`` logger (idempotent)."""
    names = set(_PYCHROMECAST_LOGGERS) | {
        name for name in list(logging.root.manager.loggerDict) if name.startswith("pychromecast.")
    }
    for name in names:
        logger = logging.getLogger(name)
        if _REDACT_FILTER not in logger.filters:
            logger.addFilter(_REDACT_FILTER)


# --- pychromecast implementation -------------------------------------------------------------


class _Recorder:
    """Thread-safe ordered record of receiver reports (called from the socket thread)."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._events: deque[MediaEvent] = deque(maxlen=MAX_EVENTS)
        self._seq = 0

    def _add(self, **fields: Any) -> None:
        with self._cond:
            self._seq += 1
            self._events.append(MediaEvent(seq=self._seq, **fields))
            self._cond.notify_all()

    def mark(self) -> int:
        with self._cond:
            return self._seq

    def events_after(self, seq: int, timeout: float) -> list[MediaEvent]:
        with self._cond:
            self._cond.wait_for(lambda: self._seq > seq, timeout=max(timeout, 0.0))
            return [event for event in self._events if event.seq > seq]

    # pychromecast MediaStatusListener interface
    def new_media_status(self, status: Any) -> None:
        session_id = getattr(status, "media_session_id", None)
        position = getattr(status, "current_time", None)
        duration = getattr(status, "duration", None)
        content_id = getattr(status, "content_id", None)
        state = getattr(status, "player_state", None)
        idle = getattr(status, "idle_reason", None)
        self._add(
            kind="status",
            content_id=content_id if isinstance(content_id, str) else None,
            session_id=session_id if isinstance(session_id, int) else None,
            player_state=state if isinstance(state, str) else None,
            idle_reason=idle if isinstance(idle, str) else None,
            position_s=float(position) if isinstance(position, int | float) else None,
            duration_s=float(duration) if isinstance(duration, int | float) else None,
        )

    def load_media_failed(self, queue_item_id: int, error_code: int) -> None:
        self._add(kind="load_failed")

    def command_result(self, success: bool, response: Any) -> None:
        if not success:
            self._add(kind="command_failed")


class PyChromecastSession:
    """A :class:`CastSession` backed by ``pychromecast`` (one connection)."""

    def __init__(self, host: str, port: int, *, connect_timeout: float = CONNECT_TIMEOUT_S):
        try:
            import pychromecast
            from pychromecast.const import CAST_TYPE_CHROMECAST
            from pychromecast.models import CastInfo, HostServiceInfo
        except Exception:
            raise CastError(
                "cast_unavailable",
                "Chromecast support is not installed. Reinstall Hermes Screen with its "
                "pychromecast dependency.",
            ) from None
        install_log_redaction()
        self._recorder = _Recorder()
        self._cast: Any = None
        info = CastInfo(
            {HostServiceInfo(host, port)},
            uuid.UUID(int=0),
            "Chromecast",
            None,
            host,
            port,
            CAST_TYPE_CHROMECAST,  # explicit: never call get_cast_type (30 s default)
            "Google Inc.",
        )
        try:
            self._cast = pychromecast.Chromecast(
                info, tries=1, timeout=connect_timeout, retry_wait=0.5
            )
            self._cast.media_controller.register_status_listener(self._recorder)
            self._cast.wait(timeout=connect_timeout)
        except Exception:
            self.close()
            raise CastError(
                "cast_unreachable",
                "Couldn't reach the Chromecast. Is it powered, on the same network, and is "
                "chromecast_host its current IP?",
            ) from None

    def app_id(self) -> str | None:
        try:
            value = self._cast.app_id
        except Exception:
            return None
        return value if isinstance(value, str) else None

    def mark(self) -> int:
        return self._recorder.mark()

    def events_after(self, seq: int, timeout: float) -> list[MediaEvent]:
        return self._recorder.events_after(seq, timeout)

    def _media_ready(self) -> bool:
        try:
            namespaces = self._cast.socket_client.app_namespaces
        except Exception:
            return False
        return self.app_id() == APP_DEFAULT_MEDIA_RECEIVER and MEDIA_NAMESPACE in namespaces

    def request_status(self) -> None:
        if not self._media_ready():
            return  # never let a status request launch or touch another app
        try:
            self._cast.media_controller.update_status()
        except Exception:
            pass

    def launch_receiver(self) -> None:
        if self.app_id() == APP_DEFAULT_MEDIA_RECEIVER:
            return
        try:
            self._cast.start_app(APP_DEFAULT_MEDIA_RECEIVER, timeout=LAUNCH_TIMEOUT_S)
        except Exception:
            raise CastError(
                "cast_launch_failed",
                "The Chromecast didn't open its media player. Try again in a moment.",
            ) from None

    def load(
        self,
        url: str,
        *,
        title: str,
        duration_s: float | None,
        start_time_s: float | None = None,
    ) -> None:
        if self.app_id() != APP_DEFAULT_MEDIA_RECEIVER:
            raise CastError(
                "cast_launch_failed",
                "The Chromecast media player is not open, so nothing was sent.",
            )
        media_info: dict[str, Any] = {}
        if duration_s:
            media_info["duration"] = duration_s
        try:
            # ``current_time`` is only sent when an explicit start exists so the
            # ordinary launch carries no new keyword (verified 14.1.1 API:
            # play_media(..., current_time=None) puts "currentTime" in the LOAD).
            if start_time_s is None:
                self._cast.media_controller.play_media(
                    url,
                    "video/mp4",
                    title=title,
                    stream_type="BUFFERED",
                    media_info=media_info or None,
                    callback_function=self._recorder.command_result,
                )
            else:
                self._cast.media_controller.play_media(
                    url,
                    "video/mp4",
                    title=title,
                    stream_type="BUFFERED",
                    media_info=media_info or None,
                    current_time=start_time_s,
                    callback_function=self._recorder.command_result,
                )
        except Exception:
            raise CastError(
                "cast_command_failed", "The Chromecast didn't accept the video. Try again."
            ) from None

    def _command(self, kind: str, session_id: int) -> None:
        if not self._media_ready():
            raise CastError(
                "not_our_playback",
                "The Chromecast is not showing our player any more, so nothing was sent.",
            )
        try:
            self._cast.media_controller.send_message(
                {"type": kind, "mediaSessionId": session_id},
                inc_session_id=True,
                callback_function=self._recorder.command_result,
            )
        except Exception:
            raise CastError(
                "cast_command_failed", "The Chromecast didn't accept the command. Try again."
            ) from None

    def pause(self, session_id: int) -> None:
        self._command("PAUSE", session_id)

    def play(self, session_id: int) -> None:
        self._command("PLAY", session_id)

    def seek(self, session_id: int, position_s: float) -> None:
        """Documented Cast SEEK (developers.google.com/cast/docs/reference/messages):
        the receiver jumps to ``position_s`` seconds and plays from there
        (``resumeState`` PLAYBACK_START also resumes a paused session)."""
        if not self._media_ready():
            raise CastError(
                "not_our_playback",
                "The Chromecast is not showing our player any more, so nothing was sent.",
            )
        try:
            self._cast.media_controller.send_message(
                {
                    "type": "SEEK",
                    "mediaSessionId": session_id,
                    "currentTime": position_s,
                    "resumeState": "PLAYBACK_START",
                },
                inc_session_id=True,
                callback_function=self._recorder.command_result,
            )
        except Exception:
            raise CastError(
                "cast_command_failed", "The Chromecast didn't accept the command. Try again."
            ) from None

    def close(self) -> None:
        cast, self._cast = self._cast, None
        if cast is None:
            return
        try:
            # Drop virtual-channel bookkeeping before disconnect so pychromecast
            # closes our TCP socket without sending a Cast CLOSE message to the
            # Default Media Receiver's transport_id (which terminates CC1AD845 on
            # Chromecast Gen 2 when the last sender disconnects).
            open_channels = getattr(getattr(cast, "socket_client", None), "_open_channels", None)
            if hasattr(open_channels, "clear"):
                open_channels.clear()
            cast.disconnect(timeout=2.0)
        except Exception:
            pass


def connect_chromecast(host: str, port: int = CAST_PORT) -> CastSession:
    """Open a bounded direct connection to the Chromecast at ``host:port``."""
    return PyChromecastSession(host, port)
