"""Hermes entry into the separately hosted Terebi Games service."""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from .hermes_screen.config import _default_secret_reader
from .hermes_screen.game_cast import launch_game_display, stop_game_display


def _error(reason: str, hint: str) -> str:
    return json.dumps({"ok": False, "reason": reason, "hint": hint})


def _start_rps(args, *, ctx, identity=None, secret_reader=None, cast_launcher=None) -> str:
    try:
        if isinstance(args, str):
            args = json.loads(args)
        if not isinstance(args, dict) or args:
            return _error("invalid_argument", "Rock-paper-scissors takes no arguments.")
        if not isinstance(identity, str) or not identity or len(identity) > 512:
            return _error("game_context_missing", "Start the game inside a Hermes conversation.")
        url = ctx.get_config("games_service_url", "")
        if not isinstance(url, str) or not url:
            return _error("not_configured", "Configure games_service_url and TEREBI_GAMES_API_KEY.")
        parts = urlsplit(url)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.netloc
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or parts.path not in {"", "/"}
        ):
            return _error(
                "games_config", "Use the game service origin without credentials or a path."
            )
        key = (secret_reader or _default_secret_reader)("TEREBI_GAMES_API_KEY")
        if not isinstance(key, str) or not key:
            return _error("not_configured", "Set the TEREBI_GAMES_API_KEY secret in Hermes.")
        request_key = hashlib.sha256((url.rstrip("/") + "|" + identity).encode()).hexdigest()
        with httpx.Client(
            timeout=httpx.Timeout(8, connect=3), follow_redirects=False, trust_env=False
        ) as client:
            response = client.post(
                url.rstrip("/") + "/v1/sessions",
                headers={"Authorization": f"Bearer {key}"},
                json={"request_key": request_key},
            )
        if response.status_code == 401:
            return _error("games_auth", "Check the game service key in Hermes's secret settings.")
        if response.status_code != 200 or len(response.content) > 65536:
            return _error(
                "games_unavailable", "Check the game service and its HTTPS origin, then retry."
            )
        data = response.json()
        if not data.get("ok") or not isinstance(data.get("state"), dict):
            raise ValueError("response")
        for field in ("pairing_url", "display_url"):
            value = data.get(field)
            if value is None and field == "pairing_url":
                continue
            link = urlsplit(value)
            if link.scheme != "https" and not (
                link.scheme == "http" and link.hostname in {"localhost", "127.0.0.1"}
            ):
                raise ValueError("insecure_camera")
            if not link.netloc or link.username or link.password:
                raise ValueError("link")
        display = urlsplit(data["display_url"])
        credentials = parse_qs(display.fragment)
        if (
            display.path != "/display/"
            or display.query
            or set(credentials) != {"session", "token"}
            or any(len(v) != 1 for v in credentials.values())
            or credentials["session"][0] != data["session_id"]
        ):
            raise ValueError("display_capability")
        app_id = ctx.get_config("games_receiver_app_id", "")
        host = ctx.get_config("chromecast_host", "")
        _remember(
            ctx,
            request_key,
            {
                "session_id": data["session_id"],
                "display_token": credentials["token"][0],
                "service_url": url.rstrip("/"),
                "host": host,
                "app_id": app_id,
                "ended": False,
                "tv_done": False,
            },
        )
        tv = {
            "ok": False,
            "reason": "games_receiver_not_configured",
            "hint": "Set a Custom Receiver app ID and Chromecast IP, or mirror manually.",
        }
        if app_id and host:
            try:
                tv = (cast_launcher or launch_game_display)(
                    host, app_id, data["session_id"], credentials["token"][0]
                )
            except Exception:
                tv = {
                    "ok": False,
                    "reason": "games_cast_failed",
                    "hint": "Use the manual display link.",
                }
        if not isinstance(tv, dict):
            tv = {
                "ok": False,
                "reason": "games_cast_failed",
                "hint": "Use the manual display link.",
            }
        verified = (
            tv.get("ok") is True
            and tv.get("evidence") == "receiver_rendered_session"
            and tv.get("session_id") == data["session_id"]
        )
        if tv.get("ok") and not verified:
            tv = {
                "ok": False,
                "reason": "receiver_render_unverified",
                "hint": "Use the manual display link.",
            }
        instructions = (
            "The receiver confirmed it rendered this game session. Open the pairing link in Safari "
            "on your phone, then use the phone camera page to play. Camera frames stay on-device. "
            "TV power and HDMI input are not verified."
            if verified
            else "Open the pairing link in Safari on your phone; camera frames stay on-device. "
            "Automatic TV launch was not verified. Open the display link in Mac Chrome, cast that "
            "tab to Den TV, then press Fullscreen. Start and advance rounds on the phone."
        )
        return json.dumps(
            {
                "ok": True,
                "game": "rock_paper_scissors",
                "session_id": data["session_id"],
                "pairing_url": data["pairing_url"],
                "pairing_expires_at_ms": data["pairing_expires_at_ms"],
                "display_url": data["display_url"],
                "expires_at_ms": data["state"]["expires_at_ms"],
                "phase": data["state"]["phase"],
                "display_path": "custom_cast_receiver" if verified else "manual_chrome_mirroring",
                "tv_verified": verified,
                "tv": tv,
                "wake_verified": False,
                "input_verified": False,
                "instructions": instructions + " If already paired, reuse the open player page.",
            }
        )
    except Exception:
        return _error(
            "games_unavailable",
            "Could not start the game. Check its service URL and secret settings.",
        )


_GAME_LOCK = threading.Lock()
_STATE_KEY = "games.active.v1"


def _records(ctx: Any) -> dict:
    state = getattr(ctx, "state", None)
    if state is not None:
        data = state.get(_STATE_KEY, {})
        return dict(data) if isinstance(data, dict) else {}
    return dict(getattr(ctx, "_screen_games", {}))


def _remember(ctx: Any, caller: str, record: dict) -> None:
    records = _records(ctx)
    records[caller] = dict(record)
    while len(records) > 64:
        del records[next(iter(records))]
    state = getattr(ctx, "state", None)
    if state is None:
        ctx._screen_games = records
    elif callable(getattr(state, "set", None)):
        state.set(_STATE_KEY, records)
    else:
        state[_STATE_KEY] = records


def start_rps(args, *, ctx, identity=None, secret_reader=None, cast_launcher=None) -> str:
    """Serialize game start/stop; ownership is stored before the hardware handoff."""
    if not _GAME_LOCK.acquire(timeout=1):
        return _error("games_busy", "Another game action is running; retry shortly.")
    try:
        return _start_rps(
            args,
            ctx=ctx,
            identity=identity,
            secret_reader=secret_reader,
            cast_launcher=cast_launcher,
        )
    finally:
        _GAME_LOCK.release()


def stop_rps(
    args: Any,
    *,
    ctx: Any,
    identity: str | None = None,
    secret_reader: Any = None,
    cast_stopper: Any = None,
) -> str:
    """End only this host conversation's recorded session; no arbitrary device STOP."""
    if not _GAME_LOCK.acquire(timeout=1):
        return _error("games_busy", "Another game action is running; retry shortly.")
    game_ended = False
    try:
        if isinstance(args, str):
            args = json.loads(args)
        if not isinstance(args, dict) or args:
            return _error("invalid_argument", "Stopping the game takes no arguments.")
        if not isinstance(identity, str) or not identity or len(identity) > 512:
            return _error("game_context_missing", "Stop the game inside its Hermes conversation.")
        url = ctx.get_config("games_service_url", "")
        if not isinstance(url, str) or not url:
            return _error("not_configured", "Configure games_service_url first.")
        caller = hashlib.sha256((url.rstrip("/") + "|" + identity).encode()).hexdigest()
        record = _records(ctx).get(caller)
        if not record:
            return json.dumps(
                {
                    "ok": True,
                    "game_ended": False,
                    "outcome": "no_active_game",
                    "hint": "No game is recorded in this conversation. TV left alone.",
                }
            )
        if record.get("ended") and record.get("tv_done"):
            return json.dumps(
                {
                    "ok": True,
                    "game_ended": True,
                    "already_ended": True,
                    "session_id": record["session_id"],
                    "tv_verified": False,
                    "tv": {"reason": "not_touched"},
                    "hint": "This game already ended. Current TV playback was left alone.",
                }
            )
        key = (secret_reader or _default_secret_reader)("TEREBI_GAMES_API_KEY")
        if not isinstance(key, str) or not key:
            return _error("not_configured", "Set the TEREBI_GAMES_API_KEY secret in Hermes.")
        # The SID captured here pins the operation even if another client starts a newer game.
        sid = record["session_id"]
        with httpx.Client(
            timeout=httpx.Timeout(8, connect=3), follow_redirects=False, trust_env=False
        ) as client:
            response = client.post(
                record["service_url"] + "/v1/sessions/" + sid + "/end",
                headers={"Authorization": f"Bearer {key}"},
                json={"request_key": caller},
            )
        if response.status_code == 401:
            return _error("games_auth", "Check the game service key in Hermes settings.")
        if response.status_code != 200 or len(response.content) > 65536:
            return _error(
                "games_end_unverified", "The service did not confirm the game ended. Retry."
            )
        data = response.json()
        if (
            data.get("ok") is not True
            or data.get("ended") is not True
            or data.get("session_id") != sid
        ):
            raise ValueError("end response")
        game_ended = True
        record["ended"] = True
        _remember(ctx, caller, record)
        if record.get("host") and record.get("app_id"):
            try:
                tv = (cast_stopper or stop_game_display)(
                    record["host"], record["app_id"], sid, record["display_token"]
                )
            except Exception:
                tv = {"ok": False, "reason": "receiver_close_unverified"}
        else:
            tv = {"ok": True, "reason": "manual_display_ended", "closed": False}
        verified = (
            tv.get("ok") is True
            and tv.get("closed") is True
            and tv.get("evidence") == "receiver_backdrop"
            and tv.get("session_id") == sid
        )
        untouched = tv.get("ok") is True and tv.get("reason") in {
            "other_playback_untouched",
            "newer_game_untouched",
            "manual_display_ended",
        }
        record["tv_done"] = verified or untouched
        _remember(ctx, caller, record)
        result = {
            "ok": verified or untouched,
            "game_ended": True,
            "session_id": sid,
            "already_ended": bool(data.get("already_ended")),
            "tv_verified": verified,
            "tv": tv,
        }
        if not result["ok"]:
            result.update(
                reason="game_ended_tv_unverified",
                hint="Your game ended and its links are revoked, but receiver closure "
                "is unverified. Check the TV; retry safely.",
            )
        else:
            result["hint"] = (
                "Game ended; Chromecast reports its artwork/home receiver."
                if verified
                else "Game ended. Other TV playback was left alone."
            )
        return json.dumps(result)
    except Exception:
        return json.dumps(
            {
                "ok": False,
                "reason": "game_ended_tv_unverified" if game_ended else "games_end_unverified",
                "game_ended": game_ended,
                "hint": "Game ended; TV closure is unverified."
                if game_ended
                else "Could not confirm the game ended. Check service settings and retry.",
            }
        )
    finally:
        _GAME_LOCK.release()
