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
        "returned by library_pick or library_scene_find (never a title, and never a guessed or "
        "remembered id). Only MP4 files with H.264 video (up to 1080p) and "
        "AAC/MP3 audio can play; others return reason 'unsupported_media' "
        "(there is no transcoding). ok=true means the Chromecast itself reported "
        "that exact item PLAYING. If ok is false, relay 'reason', 'evidence' and "
        "'hint' honestly: for example 'app_opened' means the player opened but "
        "the video was not confirmed, so never say it is playing. Calling it "
        "again without start_time_s does not restart it (a paused item resumes). "
        "An explicit start_time_s starts or seeks the selected media_source_id, resumes "
        "playback, and verifies the measured receiver position within its stated tolerance. "
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
            "media_source_id": {
                "type": "string",
                "minLength": 32,
                "maxLength": 36,
                "description": "Exact selected edition/source from library_scene_find.",
            },
            "start_time_s": {
                "type": "number",
                "minimum": 0,
                "description": "Explicit timestamp in seconds, strictly below edition runtime.",
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


LIBRARY_SCENE_FIND = {
    "name": "library_scene_find",
    "description": (
        "Find a scene in an exact Jellyfin movie edition. Supply movie (title) OR item_id. "
        "Ambiguous movies/editions return choices: ask the user which one, never pick the first. "
        "With no selector, returns edition details and saved markers. "
        "For a scene described in the user's own words, use description to look up locally saved "
        "scene descriptions and aliases. This does not inspect subtitles or video frames. "
        "A clear saved-description match may be played immediately; for match=ambiguous or "
        "needs_choice=true, ask the user to choose, even if only one tentative candidate is shown. "
        "For match=none, say no saved scene matched and offer a timestamp; do not call playback. "
        "Use query for dialogue caption search, marker for a user-saved label, or start_time_s "
        "for an explicit timestamp the user supplied. Text search is exact or approximate lexical, "
        "not visual understanding or semantic search. Relay evidence and timestamps. If several "
        "candidates match, show them and ask the user to choose before calling tv_scene_play. "
        "For approximate matches ask for confirmation; for no caption match offer a manual "
        "timestamp or saved marker. Choices expire after 15 minutes in this conversation."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "movie": {"type": "string", "description": "Movie title as in Jellyfin."},
            "item_id": {"type": "string", "description": "Exact library item ID."},
            "media_source_id": {"type": "string", "description": "Selected edition/source ID."},
            "query": {"type": "string", "description": "Dialogue or caption text to find."},
            "description": {
                "type": "string",
                "maxLength": 200,
                "description": "What happens in a saved scene, in the user's own words.",
            },
            "marker": {"type": "string", "description": "User-saved scene marker label."},
            "start_time_s": {
                "type": "number",
                "minimum": 0,
                "description": "Explicit user-supplied timestamp in seconds.",
            },
            "language": {"type": "string", "description": "Subtitle language, such as eng."},
            "track_index": {"type": "integer", "minimum": 0},
        },
        "required": [],
    },
}

LIBRARY_SCENE_SAVE = {
    "name": "library_scene_save",
    "description": (
        "Save or update a local scene marker at a timestamp explicitly supplied by the user "
        "for one exact Jellyfin movie edition. Requires item_id, label and start_time_s. "
        "Optionally save a verified short description and paraphrase aliases for local description "
        "lookup; never invent scene times from general movie knowledge. Optional end_time_s is "
        "metadata only; playback does not stop there. Existing markers are preserved. "
        "Supply media_source_id when there are multiple versions. A saved label is user evidence, "
        "not an automatically understood visual scene. Same label+edition updates safely. "
        "Resolve the movie/edition with library_scene_find first when needed. Does not play."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "item_id": {"type": "string"},
            "media_source_id": {"type": "string"},
            "label": {"type": "string", "maxLength": 80},
            "start_time_s": {"type": "number", "minimum": 0},
            "description": {"type": "string", "maxLength": 500},
            "aliases": {
                "type": "array",
                "maxItems": 8,
                "items": {"type": "string", "maxLength": 120},
            },
            "end_time_s": {
                "type": "number",
                "minimum": 0,
                "description": "Optional end metadata, after start and within edition runtime.",
            },
        },
        "required": ["item_id", "label", "start_time_s"],
    },
}

TV_SCENE_PLAY = {
    "name": "tv_scene_play",
    "description": (
        "Play a scene candidate returned by library_scene_find in this conversation. "
        "Pass its candidate_id, never invent one. When multiple or approximate matches were "
        "offered, obtain the user's choice first. Revalidates the exact edition and subtitle "
        "evidence, then starts or seeks on the configured Chromecast. Only report success "
        "when the receiver confirms PLAYING near the requested position. tv_pause pauses it."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"candidate_id": {"type": "string"}},
        "required": ["candidate_id"],
    },
}


TV_GAME_START = {
    "name": "tv_game_start",
    "description": (
        "Start rock-paper-scissors against Hermes when the user asks to play, including "
        "'Let's play rock-paper-scissors'. Returns an expiring phone pairing link and a "
        "read-only TV display link. If tv_verified is true, the configured Custom Receiver "
        "confirmed it rendered this session; return the phone pairing link. Otherwise explain "
        "the tv.reason and offer the display link for Mac Chrome tab mirroring to Den TV. "
        "Do not claim TV readiness from app launch alone. Always keep the fallback display link. "
        "Camera permission is requested only by the phone page; images stay on-device. "
        "Hermes's move, countdown, result and score are controlled by the game service, "
        "not the language model. Repeated calls reuse this conversation's active session. "
        "If pairing_url is null, the player is already paired; reuse their player page. "
        "Only rock-paper-scissors is supported. Launch may cause HDMI-CEC power/input changes, "
        "but wake_verified and input_verified remain false until separately observed. "
        "Starting a game replaces any app currently showing on the configured Chromecast."
    ),
    "parameters": {"type": "object", "additionalProperties": False, "properties": {}},
}

TV_YOUTUBE_PLAY = {
    "name": "tv_youtube_play",
    "description": (
        "Play a user-selected YouTube video on the configured Chromecast. Accepts an HTTPS "
        "video link or exact video ID; no search API key is needed. For title requests use "
        "library_youtube_search and show titles/channels for user selection. Report playback "
        "only when verified=true with receiver_exact_video evidence. app_opened is not playing. "
        "YouTube serves the video directly; no downloads or media relay. "
        "Replaces the current TV app."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "video": {
                "type": "string",
                "description": "YouTube video link or 11-character video ID",
            }
        },
        "required": ["video"],
        "additionalProperties": False,
    },
}

TV_YOUTUBE_PAUSE = {
    "name": "tv_youtube_pause",
    "description": (
        "Pause the same YouTube video/media session verified by tv_youtube_play in this plugin "
        "context. Never pauses a Jellyfin movie or unrelated video. Success requires fresh "
        "PAUSED evidence for that video and session. Use tv_youtube_play to resume the same video."
    ),
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}

LIBRARY_YOUTUBE_SEARCH = {
    "name": "library_youtube_search",
    "description": (
        "Find up to five YouTube videos by title using the official YouTube Data API. Optional: "
        "requires YOUTUBE_API_KEY in Hermes secrets; direct-link playback needs no key. Return "
        "titles, channels and video IDs. Show plausible matches and ask which one the user means; "
        "never automatically play an ambiguous result. "
        "Then use tv_youtube_play with the chosen ID. "
        "Search does not prove a video is available on the TV."
    ),
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 200}},
        "required": ["query"],
        "additionalProperties": False,
    },
}
