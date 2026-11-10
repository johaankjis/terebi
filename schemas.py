"""Tool schemas — what the LLM reads."""

LIBRARY_STATUS = {
    "name": "library_status",
    "description": (
        "Check the connection to the configured Jellyfin server. Returns the "
        "server name, version and library item counts when everything is "
        "configured and reachable, or a clear error with a hint when "
        "configuration is missing or the server cannot be reached. Use this "
        "first to verify Jellyfin is set up before other library tools."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

LIBRARY_PICK = {
    "name": "library_pick",
    "description": (
        "Pick up to 3 things to watch from the user's own Jellyfin library that "
        "fit strictly within a time limit. Use it when the user asks what to "
        "watch, or what fits in a given number of minutes. Candidates come from "
        "Jellyfin's real watch state, in this order: unfinished items to resume, "
        "Next Up episodes, then never-watched movies/videos. Resume and Next Up "
        "items must fit in their remaining time; unwatched items in their full "
        "runtime; items with unknown runtime are never picked. Each pick has an "
        "item_id, title, type, year, minutes, a source (resume, next_up or "
        "unwatched) and a one-line 'why' grounded in Jellyfin's data: relay "
        "those reasons, do not invent others. Check 'complete', 'errors' and "
        "'note': a partial or empty result is stated honestly, never treated as "
        "'nothing to watch' when a lookup failed. This only reads the library; "
        "it does NOT start playback on the TV. If Jellyfin is not configured it "
        "returns an error with a hint."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "max_minutes": {
                "type": "number",
                "description": (
                    "Minutes the viewer has: a number above 0 and at most 1440. "
                    "Picks must fit within it (remaining time for started items)."
                ),
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 3,
                "default": 3,
                "description": "How many picks to return, 1 to 3 (default 3).",
            },
        },
        "required": ["max_minutes"],
    },
}

TV_PLAY = {
    "name": "tv_play",
    "description": (
        "Play one item from the user's Jellyfin library on the configured "
        "Chromecast and confirm it is really playing. Pass the exact item_id "
        "returned by library_pick (never a title, and never a guessed or "
        "remembered id). Only MP4 files with H.264 video (up to 1080p) and "
        "AAC/MP3 audio can play; others return reason 'unsupported_media' "
        "(there is no transcoding). ok=true means the Chromecast itself reported "
        "that exact item PLAYING. If ok is false, relay 'reason', 'evidence' and "
        "'hint' honestly: for example 'app_opened' means the player opened but "
        "the video was not confirmed, so never say it is playing. Calling it "
        "again for the same item does not restart it (a paused item resumes). "
        "It does not turn on the TV or switch inputs, and the temporary stream "
        "link expires after 'relay_expires_in_minutes'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "item_id": {
                "type": "string",
                "minLength": 32,
                "maxLength": 36,
                "description": "Exact Jellyfin item id from library_pick, e.g. 32 hex characters.",
            },
        },
        "required": ["item_id"],
    },
}

TV_PAUSE = {
    "name": "tv_pause",
    "description": (
        "Pause what tv_play started on the Chromecast and confirm it paused. It "
        "only pauses the exact stream and media session this plugin started; "
        "anything else on the Chromecast is left alone and reported as "
        "'not_our_playback'. Safe to call twice: if it is already paused it "
        "returns ok with already_paused=true. If ok is false, say it is not "
        "confirmed paused. Takes no arguments."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}
