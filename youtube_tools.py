"""Thin YouTube handlers using Hermes configuration and secret scope."""

import json
import logging
from typing import Any

from .hermes_screen.config import _default_secret_reader
from .hermes_screen.youtube import error, search, video_id


def call(method: str, args: Any, *, ctx: Any, manager: Any, secret_reader=None) -> str:
    if not isinstance(args, dict):
        return json.dumps(error("invalid_argument", "Use the tool's named arguments."))
    if method == "search":
        if set(args) != {"query"}:
            return json.dumps(error("invalid_argument", "Provide only query for title search."))
        try:
            key = (secret_reader or _default_secret_reader)("YOUTUBE_API_KEY")
            return json.dumps(search(args["query"], key))
        except Exception:
            return json.dumps(error("youtube_search_unavailable", "Check Hermes secret settings."))
    if method == "play":
        try:
            if set(args) != {"video"}:
                raise ValueError
            requested = video_id(args["video"])
        except (ValueError, TypeError):
            return json.dumps(
                error(
                    "invalid_argument",
                    "Provide an 11-character YouTube video ID "
                    "or an HTTPS watch, youtu.be, shorts, embed or live link. "
                    "Playlists and timestamp offsets are not supported.",
                )
            )
    elif method == "pause" and not args:
        requested = None
    else:
        return json.dumps(error("invalid_argument", "Pause takes no arguments."))
    try:
        result = manager.call(
            ctx.get_config("chromecast_host", ""), requested, pause=method == "pause"
        )
        logging.getLogger(__name__).info(
            "youtube_tool method=%s ok=%s verified=%s "
            "video_id=%s state=%s media_session_id=%s reason=%s",
            method,
            result.get("ok"),
            result.get("verified"),
            result.get("video_id"),
            result.get("state"),
            result.get("media_session_id"),
            result.get("reason"),
        )
        return json.dumps(result)
    except Exception:
        return json.dumps(error("youtube_control_failed", "YouTube playback is unverified; retry."))
