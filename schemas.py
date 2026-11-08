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
