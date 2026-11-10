"""Shared fake Jellyfin payloads for the Chromecast tests (no network, no hardware)."""

from __future__ import annotations

from typing import Any

BBB_ID = "e5d6c471a8a4ea26e00a3694f91bf8d1"  # test fixture only, mirrors the demo item shape
SOURCE_ID = BBB_ID
OTHER_ID = "c" * 32
RUNTIME_TICKS = 5_964_590_000  # 596.459 s


def cast_item(item_id: str = BBB_ID, **overrides: Any) -> dict[str, Any]:
    """A raw Jellyfin ``BaseItemDto`` for a directly castable MP4."""
    source: dict[str, Any] = {
        "Id": item_id,
        "Protocol": "File",
        "IsRemote": False,
        "Container": "mov,mp4,m4a,3gp,3g2,mj2",
        "Path": "/media/movies/BigBuckBunny_320x180.mp4",
        "Size": 64_657_027,
        "DefaultAudioStreamIndex": 1,
        "MediaStreams": [
            {"Type": "Video", "Index": 0, "Codec": "h264", "Height": 180, "Width": 320},
            {"Type": "Audio", "Index": 1, "Codec": "aac"},
        ],
    }
    source.update(overrides.pop("source", {}))
    data: dict[str, Any] = {
        "Id": item_id,
        "Name": "BigBuckBunny_320x180",
        "Type": "Movie",
        "ProductionYear": 2008,
        "RunTimeTicks": RUNTIME_TICKS,
        "UserData": {"Played": False, "PlaybackPositionTicks": 0},
        "MediaSources": [source],
    }
    data.update(overrides)
    return data
