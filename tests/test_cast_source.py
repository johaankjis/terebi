"""JellyfinClient.get_cast_source / cast_stream_target, mocked with respx."""

from __future__ import annotations

import pytest
import respx
from cast_fixtures import BBB_ID, OTHER_ID, cast_item

from hermes_screen.jellyfin import JellyfinClient, JellyfinError

BASE = "http://jf.test:8096"
KEY = "s3cr3t-api-key-0123456789abcdef"
USER_ID = "1" * 32


@pytest.fixture
def api():
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.get(f"/Users/{USER_ID}").respond(json={"Id": USER_ID, "Name": "Ann"})
        yield router


@pytest.fixture
def jf(api):
    with JellyfinClient(BASE, KEY, USER_ID) as client:
        yield client


def test_castable_mp4_is_accepted_for_configured_user(api, jf):
    route = api.get(f"/Items/{BBB_ID}").respond(json=cast_item())
    source = jf.get_cast_source(BBB_ID)
    assert source == {
        "item_id": BBB_ID,
        "title": "BigBuckBunny_320x180",
        "type": "Movie",
        "minutes": 10,
        "duration_s": pytest.approx(596.459),
        "media_source_id": BBB_ID,
    }
    request = route.calls[0].request
    assert dict(request.url.params) == {"userId": USER_ID}
    assert 'Token="' + KEY + '"' in request.headers["Authorization"]
    assert "Path" not in str(source) and "/media" not in str(source)


def test_dashed_or_upper_id_is_the_same_exact_id(api, jf):
    api.get(f"/Items/{BBB_ID}").respond(json=cast_item())
    dashed = f"{BBB_ID[:8]}-{BBB_ID[8:12]}-{BBB_ID[12:16]}-{BBB_ID[16:20]}-{BBB_ID[20:]}"
    assert jf.get_cast_source(dashed.upper())["item_id"] == BBB_ID


@pytest.mark.parametrize(
    "bad", ["", "Big Buck Bunny", "BigBuckBunny_320x180", "../Users", f"{BBB_ID}/x", None, 5]
)
def test_titles_and_junk_are_not_resolved(api, jf, bad):
    with pytest.raises(JellyfinError) as exc:
        jf.get_cast_source(bad)  # type: ignore[arg-type]
    assert exc.value.reason == "invalid_argument"
    assert not [c for c in api.calls if "/Items" in str(c.request.url)]


def test_unknown_item_is_not_found(api, jf):
    api.get(f"/Items/{BBB_ID}").respond(404)
    with pytest.raises(JellyfinError) as exc:
        jf.get_cast_source(BBB_ID)
    assert exc.value.reason == "not_found"


def test_response_for_another_id_is_rejected(api, jf):
    api.get(f"/Items/{BBB_ID}").respond(json=cast_item(OTHER_ID))
    with pytest.raises(JellyfinError) as exc:
        jf.get_cast_source(BBB_ID)
    assert exc.value.reason == "jellyfin_bad_response"


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"Type": "Series"}, "Series"),
        ({"MediaSources": []}, "no playable file"),
        ({"source": {"Container": "mkv"}}, "container is mkv"),
        ({"source": {"Container": "mov,mp4,m4a", "Path": "/m/a.mov"}}, "not an .mp4"),
        ({"source": {"Protocol": "Http"}}, "not a local file"),
        ({"source": {"IsRemote": True}}, "remote"),
        ({"source": {"Id": "nope"}}, "no valid id"),
        (
            {"source": {"MediaStreams": [{"Type": "Video", "Codec": "hevc"}]}},
            "video codec is hevc",
        ),
        (
            {"source": {"MediaStreams": [{"Type": "Video", "Codec": "h264", "Height": 2160}]}},
            "1080p",
        ),
        (
            {
                "source": {
                    "MediaStreams": [
                        {"Type": "Video", "Codec": "h264"},
                        {"Type": "Audio", "Index": 1, "Codec": "dts"},
                    ]
                }
            },
            "audio codec is dts",
        ),
        ({"source": {"MediaStreams": []}}, "no video stream"),
    ],
)
def test_unsupported_media_is_rejected_honestly(api, jf, overrides, fragment):
    api.get(f"/Items/{BBB_ID}").respond(json=cast_item(**overrides))
    with pytest.raises(JellyfinError) as exc:
        jf.get_cast_source(BBB_ID)
    assert exc.value.reason == "unsupported_media"
    assert fragment in exc.value.hint
    assert "/m/" not in exc.value.hint and "/media" not in exc.value.hint


def test_server_labels_are_sanitized_in_hints(api, jf):
    api.get(f"/Items/{BBB_ID}").respond(
        json=cast_item(source={"Container": "<script>alert(1)</script>"})
    )
    with pytest.raises(JellyfinError) as exc:
        jf.get_cast_source(BBB_ID)
    assert "<" not in exc.value.hint and ">" not in exc.value.hint


def test_silent_video_is_accepted(api, jf):
    api.get(f"/Items/{BBB_ID}").respond(
        json=cast_item(source={"MediaStreams": [{"Type": "Video", "Codec": "H264"}]})
    )
    assert jf.get_cast_source(BBB_ID)["item_id"] == BBB_ID


def test_stream_target_is_pinned_and_key_stays_in_header(api, jf):
    api.get(f"/Items/{BBB_ID}").respond(json=cast_item())
    url, auth = jf.cast_stream_target(jf.get_cast_source(BBB_ID))
    assert url == f"{BASE}/Videos/{BBB_ID}/stream?static=true&mediaSourceId={BBB_ID}"
    assert KEY not in url and "api_key" not in url
    assert auth.startswith("MediaBrowser ") and f'Token="{KEY}"' in auth


@pytest.mark.parametrize("source", [{}, {"item_id": "../x", "media_source_id": BBB_ID}])
def test_stream_target_refuses_unvalidated_input(jf, source):
    with pytest.raises(JellyfinError):
        jf.cast_stream_target(source)
