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
