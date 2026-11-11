"""Launch a non-media Cast receiver; success requires its session-render acknowledgement."""

from __future__ import annotations

import ipaddress
import re
import secrets
import threading
import time
from collections import deque
from typing import Any

from .cast import APP_DEFAULT_MEDIA_RECEIVER, CAST_PORT, CastError, PyChromecastSession

NAMESPACE = "urn:x-cast:com.terebi.games"
ACK_TIMEOUT_S = 10.0
LAUNCH_TIMEOUT_S = 8.0
NAMESPACE_TIMEOUT_S = 8.0
PHASES = {"waiting_for_player", "ready", "countdown", "reveal", "score", "next_round"}
_LAUNCH_LOCK = threading.Lock()


class GameCastTransport:
    """Reuse direct-IP bounded connection and non-closing disconnect from movie control."""

    def __init__(self, host: str, app_id: str):
        from pychromecast.controllers import BaseController

        self.app_id = app_id
        self.events: deque = deque(maxlen=16)
        self.condition = threading.Condition()
        self.connection = PyChromecastSession(host, CAST_PORT)
        self.cast = self.connection._cast
        owner = self

        class Controller(BaseController):
            def __init__(self):
                # No supporting_app_id: send must never implicitly launch an app.
                super().__init__(NAMESPACE)

            def receive_message(self, _message, data):
                if isinstance(data, dict):
                    with owner.condition:
                        owner.events.append(dict(data))
                        owner.condition.notify_all()
                return True

        self.controller = Controller()
        try:
            self.cast.register_handler(self.controller)
        except Exception:
            self.connection.close()
            raise

    def launch(self):
        self.cast.start_app(self.app_id, timeout=LAUNCH_TIMEOUT_S)
        deadline = time.monotonic() + NAMESPACE_TIMEOUT_S
        while time.monotonic() < deadline:
            if self.matches_app() and NAMESPACE in self.cast.socket_client.app_namespaces:
                return
            time.sleep(0.05)
        raise CastError("receiver_unavailable", "Check the receiver URL and device registration.")

    def matches_app(self) -> bool:
        return self.connection.app_id() == self.app_id

    def send(self, message: dict):
        if not self.matches_app():
            raise CastError(
                "receiver_changed", "The Chromecast changed apps. Use the display link."
            )
        self.controller.send_message(message, no_add_request_id=True)

    def receive(self, timeout: float) -> dict | None:
        with self.condition:
            if not self.events:
                self.condition.wait(timeout=max(0, timeout))
            return self.events.popleft() if self.events else None

    def close(self):
        # Do not send CLOSE or STOP: the receiver must continue without this sender.
        self.connection.close()


def launch_game_display(
    host: str,
    app_id: str,
    session_id: str,
    display_token: str,
    *,
    transport_factory=GameCastTransport,
    clock=time.monotonic,
    ack_timeout_s: float = ACK_TIMEOUT_S,
) -> dict[str, Any]:
    """Only the viewer credential crosses Cast; never a pairing or admin capability."""
    try:
        ipaddress.ip_address(host)
        if (
            not isinstance(app_id, str)
            or not re.fullmatch(r"[A-Fa-f0-9]{8}", app_id)
            or app_id.upper() == APP_DEFAULT_MEDIA_RECEIVER
            or not all(
                isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_-]{16,128}", v)
                for v in (session_id, display_token)
            )
        ):
            raise ValueError
    except (ValueError, TypeError):
        return {
            "ok": False,
            "reason": "games_cast_config",
            "hint": "Set the Chromecast IP and Custom Receiver application ID.",
        }
    if not _LAUNCH_LOCK.acquire(timeout=1):
        return {
            "ok": False,
            "reason": "games_cast_busy",
            "hint": "Another launch is running. Use the display link or retry.",
        }
    transport = None
    try:
        challenge = secrets.token_urlsafe(24)
        transport = transport_factory(host, app_id.upper())
        transport.launch()
        transport.send(
            {
                "type": "SHOW_SESSION",
                "request_id": challenge,
                "session_id": session_id,
                "display_token": display_token,
            }
        )
        deadline = clock() + ack_timeout_s
        while clock() < deadline:
            event = transport.receive(min(0.25, max(0, deadline - clock())))
            if (
                not isinstance(event, dict)
                or event.get("request_id") != challenge
                or event.get("session_id") != session_id
            ):
                continue
            if event.get("type") == "DISPLAY_FAILED":
                return {
                    "ok": False,
                    "reason": "receiver_display_failed",
                    "hint": "Receiver session loading failed. Use the manual display link.",
                }
            if (
                event.get("type") == "DISPLAY_RENDERED"
                and event.get("phase") in PHASES
                and type(event.get("revision")) is int
                and event["revision"] >= 1
                and transport.matches_app()
            ):
                return {
                    "ok": True,
                    "evidence": "receiver_rendered_session",
                    "session_id": session_id,
                    "app_id": app_id.upper(),
                    "phase": event["phase"],
                    "revision": event["revision"],
                }
        return {
            "ok": False,
            "reason": "receiver_render_unverified",
            "hint": "No matching render acknowledgement. Use the manual display link.",
        }
    except CastError as exc:
        return exc.to_dict()
    except Exception:
        return {
            "ok": False,
            "reason": "games_cast_failed",
            "hint": "Game launch failed. Check registration or use the manual display link.",
        }
    finally:
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass
        _LAUNCH_LOCK.release()
