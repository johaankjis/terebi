"""Hermes entry into the separately hosted Terebi Games service."""

from __future__ import annotations

import hashlib
import json
from urllib.parse import urlsplit

import httpx

from .hermes_screen.config import _default_secret_reader


def _error(reason: str, hint: str) -> str:
    return json.dumps({"ok": False, "reason": reason, "hint": hint})


def start_rps(args, *, ctx, identity=None, secret_reader=None) -> str:
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
                "display_path": "manual_chrome_mirroring",
                "tv_verified": False,
                "instructions": (
                    "Open the pairing link in Safari on your phone; camera frames stay on-device. "
                    "Open the display link in Mac Chrome, cast that tab to Den TV, then press "
                    "Fullscreen. Start and advance rounds on the phone. "
                    "If already paired, reuse the open player page."
                ),
            }
        )
    except Exception:
        return _error(
            "games_unavailable",
            "Could not start the game. Check its service URL and secret settings.",
        )
