"""SubtitleSceneResolver against a mocked Jellyfin (respx); no network, no hardware."""

from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from hermes_screen import scene_search
from hermes_screen.scene_search import STORE_LRU_KEY, STORE_PREFIX, SubtitleSceneResolver

FIXTURES = Path(__file__).parent / "fixtures" / "scenes"
BASE = "http://jellyfin.test:8096"
KEY = "sekret-api-key-0123456789"
USER = "682764864adc45bbb6b981837f790812"
USER2 = "11111111111111111111111111111111"
ITEM = "e5d6c471a8a4ea26e00a3694f91bf8d1"
SRC = ITEM
SRC2 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SECRET_PATH = "/media/movies/Lighthouse (2026)/Lighthouse.mp4"

CONTRACT_KEYS = {"item_id", "media_source_id", "start_time_s", "evidence"}
EVIDENCE_KEYS = {
    "kind",
    "method",
    "track_index",
    "language",
    "track_fingerprint",
    "cue_indices",
    "cue_start_s",
    "cue_end_s",
    "excerpt",
}


def srt() -> bytes:
    return (FIXTURES / "lighthouse.en.srt").read_bytes()


def vtt() -> bytes:
    return (FIXTURES / "lighthouse.en.vtt").read_bytes()


def sub_stream(index: int, codec: str = "subrip", language: str | None = "eng", **kw: Any):
    stream = {
        "Type": "Subtitle",
        "Index": index,
        "Codec": codec,
        "Language": language,
        "DisplayTitle": f"{language or 'Unknown'} - {codec.upper()}",
        "IsExternal": False,
        "IsForced": False,
        "IsDefault": False,
        "IsTextSubtitleStream": codec not in ("PGSSUB", "pgssub", "dvdsub"),
        "Path": SECRET_PATH + f".{index}.srt",
    }
    stream.update(kw)
    return stream


def source(source_id: str = SRC, streams: list[dict[str, Any]] | None = None, **kw: Any):
    raw = {
        "Id": source_id,
        "Name": "Lighthouse 1080p",
        "Path": SECRET_PATH,
        "Protocol": "File",
        "Container": "mp4",
        "Size": 123456,
        "RunTimeTicks": 2 * 3600 * 10_000_000,
        "ETag": "src-etag-1",
        "MediaStreams": [
            {"Type": "Video", "Index": 0, "Codec": "h264"},
            {"Type": "Audio", "Index": 1, "Codec": "aac", "Language": "eng"},
            *(streams if streams is not None else [sub_stream(2)]),
        ],
    }
    raw.update(kw)
    return raw


def item(sources: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
    raw = {
        "Id": ITEM,
        "Name": "Lighthouse",
        "Type": "Movie",
        "Etag": "item-etag-1",
        "RunTimeTicks": 2 * 3600 * 10_000_000,
        "MediaSources": sources if sources is not None else [source()],
    }
    raw.update(kw)
    return raw


def sub_url(src: str = SRC, index: int = 2, fmt: str = "srt", item_id: str = ITEM) -> str:
    return f"{BASE}/Videos/{item_id}/{src}/Subtitles/{index}/Stream.{fmt}"


class Server:
    """Holds the mocked Jellyfin state so tests can change it between calls."""

    def __init__(self, mock: respx.MockRouter) -> None:
        self.mock = mock
        self.item = item()
        self.users = {USER: "homelab", USER2: "guest"}
        mock.get(url__regex=rf"^{re.escape(BASE)}/Users/(?P<uid>[0-9a-f]{{32}})$").mock(
            side_effect=self._user
        )
        self.item_route = mock.get(url__regex=rf"^{re.escape(BASE)}/Items/{ITEM}(\?.*)?$").mock(
            side_effect=self._item
        )

    def _user(self, request: httpx.Request, uid: str) -> httpx.Response:
        if uid not in self.users:
            return httpx.Response(404)
        return httpx.Response(200, json={"Id": uid, "Name": self.users[uid]})

    def _item(self, request: httpx.Request) -> httpx.Response:
        if request.url.params.get("userId") not in self.users:
            return httpx.Response(400)
        return httpx.Response(200, json=self.item)

    def subtitle(
        self,
        body: bytes = b"",
        *,
        src: str = SRC,
        index: int = 2,
        fmt: str = "srt",
        ctype: str = "application/x-subrip",
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> respx.Route:
        return self.mock.get(sub_url(src, index, fmt)).mock(
            return_value=httpx.Response(
                status, content=body, headers={"content-type": ctype, **(headers or {})}
            )
        )


@pytest.fixture
def server():
    with respx.mock(assert_all_called=False) as mock:
        yield Server(mock)


def resolver(store: dict[str, Any] | None = None, user: str = USER, **kw: Any):
    return SubtitleSceneResolver(BASE, KEY, user, store, **kw)


def assert_no_leaks(result: Any) -> None:
    text = json.dumps(result)
    for secret in (KEY, BASE, "jellyfin.test", SECRET_PATH, "/media/", "Traceback"):
        assert secret not in text


def assert_contract(candidate: dict[str, Any]) -> None:
    assert set(candidate) == CONTRACT_KEYS
    ev = candidate["evidence"]
    assert EVIDENCE_KEYS <= set(ev) <= EVIDENCE_KEYS | {"score", "model_id"}
    assert re.fullmatch(r"[0-9a-f]{32}", candidate["item_id"])
    assert re.fullmatch(r"[0-9a-f]{32}", candidate["media_source_id"])
    for key in ("start_time_s",):
        value = candidate[key]
        assert isinstance(value, float) and math.isfinite(value) and value >= 0
    assert ev["kind"] == "subtitle"
    assert re.fullmatch(r"[0-9a-f]{64}", ev["track_fingerprint"])
    assert ev["cue_start_s"] == candidate["start_time_s"]
    assert ev["cue_end_s"] >= ev["cue_start_s"]
    assert all(isinstance(i, int) for i in ev["cue_indices"])
    assert len(ev["excerpt"]) <= 220


# --- construction ------------------------------------------------------------------------


def test_constructor_does_no_io_and_hides_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with respx.mock(assert_all_called=False) as mock:
        r = SubtitleSceneResolver(BASE, KEY)
        assert not mock.calls
    assert KEY not in repr(r)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "base, key",
    [("ftp://x", KEY), ("", KEY), (BASE, ""), ("http://user:pw@h", KEY), (BASE + "?a=1", KEY)],
)
def test_bad_settings_are_errors_not_exceptions(base: str, key: str) -> None:
    with respx.mock(assert_all_called=False) as mock:
        out = SubtitleSceneResolver(base, key).search(ITEM, SRC, "keep the lamp burning")
        assert not mock.calls
    assert out["ok"] is False and out["reason"] == "jellyfin_config"
    assert_no_leaks(out)


# --- editions --------------------------------------------------------------------------------


def test_editions_are_compact_and_flag_bitmap_tracks(server: Server) -> None:
    server.item = item(
        [
            source(SRC, [sub_stream(2), sub_stream(3, "PGSSUB", "eng")]),
            source(SRC2, [], Name="Lighthouse Director's Cut", RunTimeTicks=3 * 3600 * 10**7),
        ]
    )
    out = resolver().editions(ITEM)
    assert out["ok"] is True and out["ambiguous"] is True
    assert out["title"] == "Lighthouse"
    first, second = out["sources"]
    assert first["media_source_id"] == SRC and first["searchable_tracks"] == 1
    assert [t["searchable"] for t in first["subtitle_tracks"]] == [True, False]
    assert "OCR" in first["subtitle_tracks"][1]["problem"]
    assert second["name"] == "Lighthouse Director's Cut" and second["duration_s"] == 10800.0
    assert second["subtitle_tracks"] == []
    assert_no_leaks(out)


def test_editions_rejects_non_video_and_bad_ids(server: Server) -> None:
    server.item = item(Type="Series")
    assert resolver().editions(ITEM)["reason"] == "unsupported_media"
    assert resolver().editions("../../etc")["reason"] == "invalid_argument"


# --- dialogue search (required fixture test) -------------------------------------------------


def test_dialogue_query_srt_returns_contract_candidate(server: Server) -> None:
    route = server.subtitle(srt())
    out = resolver().search(ITEM, SRC, "It's only the wind")
    assert out["ok"] is True and out["no_match"] is False and out["method"] == "exact"
    assert out["needs_choice"] is False
    (cand,) = out["candidates"]
    assert_contract(cand)
    assert cand["item_id"] == ITEM and cand["media_source_id"] == SRC
    assert cand["start_time_s"] == 63.1
    ev = cand["evidence"]
    assert ev["method"] == "exact" and ev["track_index"] == 2 and ev["language"] == "eng"
    assert ev["cue_indices"] == [3] and ev["cue_end_s"] == 65.6
    assert ev["excerpt"] == "It's only the wind."
    # auth went only in the header, to the configured server
    request = route.calls.last.request
    assert request.headers["authorization"].startswith("MediaBrowser ")
    assert KEY in request.headers["authorization"]
    assert KEY not in str(request.url)
    assert request.url.host == "jellyfin.test"
    assert_no_leaks(out)


def test_dialogue_query_webvtt_track(server: Server) -> None:
    server.item = item([source(streams=[sub_stream(4, "webvtt", "eng", IsExternal=True)])])
    server.subtitle(vtt(), index=4, fmt="vtt", ctype="text/vtt; charset=utf-8")
    out = resolver().search(ITEM, SRC, "in the blue tin by the old stove")
    (cand,) = out["candidates"]
    assert_contract(cand)
    assert cand["start_time_s"] == 66.0
    assert cand["evidence"]["cue_indices"] == [4, 5]  # neighbors, original times
    assert cand["evidence"]["cue_end_s"] == 70.0
    assert out["track"]["converted_by_server"] is False


def test_time_precision_is_milliseconds(server: Server) -> None:
    server.subtitle(srt())
    out = resolver().search(ITEM, SRC, "keep the lamp burning", limit=3)
    starts = [c["start_time_s"] for c in out["candidates"]]
    assert starts == [5.0, 754.567]
    assert out["candidates"][1]["evidence"]["cue_end_s"] == 756.001


def test_duplicate_phrase_returns_all_moments_for_user_choice(server: Server) -> None:
    server.subtitle(srt())
    out = resolver().search(ITEM, SRC, "Keep the lamp burning")
    assert out["needs_choice"] is True and len(out["candidates"]) == 2
    assert [c["evidence"]["cue_indices"] for c in out["candidates"]] == [[1], [6]]
    assert "more than once" in out["hint"]
    one = resolver().search(ITEM, SRC, "Keep the lamp burning", limit=1)
    assert len(one["candidates"]) == 1 and one["truncated"] is True and one["total_matches"] == 2


def test_no_match_is_explicit_with_fallback_hint(server: Server) -> None:
    server.subtitle(srt())
    out = resolver().search(ITEM, SRC, "the dragon lands on the tower")
    assert out["ok"] is True and out["no_match"] is True and out["candidates"] == []
    assert out["method"] == "none"
    assert "marker" in out["hint"] and "timestamp" in out["hint"]


def test_lexical_fallback_is_labelled(server: Server) -> None:
    server.subtitle(srt())
    out = resolver().search(ITEM, SRC, "where did the key go, blue tin?")
    assert out["method"] == "lexical"
    cand = out["candidates"][0]
    assert_contract(cand)
    assert cand["evidence"]["method"] == "lexical" and 0 < cand["evidence"]["score"] < 1
    assert "approximate" in out["hint"]


def test_cues_past_source_duration_are_not_candidates(server: Server) -> None:
    server.item = item([source(RunTimeTicks=30 * 60 * 10_000_000)])
    server.subtitle(srt())
    out = resolver().search(ITEM, SRC, "cafe au lait sil vous plait")
    assert out["no_match"] is True and out["duration_s"] == 1800.0


def test_server_converted_text_codec_requests_srt(server: Server) -> None:
    server.item = item([source(streams=[sub_stream(2, "mov_text")])])
    route = server.subtitle(srt())
    out = resolver().search(ITEM, SRC, "abandon ship")
    assert route.called and out["track"]["converted_by_server"] is True
    assert out["candidates"][0]["evidence"]["excerpt"] == "Captain & crew, abandon ship."


# --- editions, tracks and languages --------------------------------------------------------------


def test_multi_edition_without_source_is_ambiguous(server: Server) -> None:
    server.item = item([source(SRC), source(SRC2)])
    out = resolver().search(ITEM, None, "keep the lamp burning")
    assert out["ok"] is False and out["reason"] == "edition_ambiguous"
    assert [s["media_source_id"] for s in out["sources"]] == [SRC, SRC2]
    assert not any("/Subtitles/" in str(c.request.url) for c in server.mock.calls)


def test_single_source_may_be_omitted(server: Server) -> None:
    server.subtitle(srt())
    out = resolver().search(ITEM, None, "abandon ship")
    assert out["ok"] and out["candidates"][0]["media_source_id"] == SRC


def test_edition_mismatch_refuses_foreign_source(server: Server) -> None:
    other = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    out = resolver().search(ITEM, other, "abandon ship")
    assert out["ok"] is False and out["reason"] == "edition_mismatch"
    assert out["sources"][0]["media_source_id"] == SRC
    assert not any("/Subtitles/" in str(c.request.url) for c in server.mock.calls)


def test_each_edition_uses_its_own_track(server: Server) -> None:
    cut = (
        b"1\n00:00:09,000 --> 00:00:11,000\nKeep the lamp burning,\n\n"
        b"2\n00:20:00,000 --> 00:20:02,000\nA scene only in the long cut.\n"
    )
    server.item = item([source(SRC), source(SRC2, [sub_stream(5)])])
    server.subtitle(srt())
    server.subtitle(cut, src=SRC2, index=5)
    store: dict[str, Any] = {}
    a = resolver(store).search(ITEM, SRC, "keep the lamp burning")
    b = resolver(store).search(ITEM, SRC2, "keep the lamp burning")
    assert [c["start_time_s"] for c in a["candidates"]] == [5.0, 754.567]
    assert [c["start_time_s"] for c in b["candidates"]] == [9.0]
    assert {c["media_source_id"] for c in b["candidates"]} == {SRC2}
    assert (
        a["candidates"][0]["evidence"]["track_fingerprint"]
        != b["candidates"][0]["evidence"]["track_fingerprint"]
    )
    assert resolver(store).search(ITEM, SRC, "only in the long cut")["no_match"] is True


def test_multiple_tracks_need_language_or_index(server: Server) -> None:
    fre = ("1\n00:00:02,000 --> 00:00:04,000\nGarde la lampe allumée.\n").encode()
    server.item = item([source(streams=[sub_stream(2), sub_stream(3, "subrip", "fre")])])
    server.subtitle(srt())
    server.subtitle(fre, index=3)
    out = resolver().search(ITEM, SRC, "abandon ship")
    assert out["reason"] == "subtitle_track_ambiguous"
    assert [t["track_index"] for t in out["tracks"]] == [2, 3]
    en = resolver().search(ITEM, SRC, "abandon ship", language="en")
    assert en["candidates"][0]["evidence"]["language"] == "eng"
    fr = resolver().search(ITEM, SRC, "garde la lampe allumee", language="fra")
    assert fr["candidates"][0]["evidence"]["track_index"] == 3
    by_index = resolver().search(ITEM, SRC, "garde la lampe", track_index=3)
    assert by_index["candidates"][0]["start_time_s"] == 2.0
    missing = resolver().search(ITEM, SRC, "abandon ship", language="de")
    assert missing["reason"] == "no_subtitles_in_language"
    assert resolver().search(ITEM, SRC, "x", track_index=9)["reason"] == "track_not_found"


def test_same_language_tracks_stay_ambiguous(server: Server) -> None:
    server.item = item(
        [source(streams=[sub_stream(2), sub_stream(3, IsForced=True, IsHearingImpaired=True)])]
    )
    out = resolver().search(ITEM, SRC, "abandon ship", language="eng")
    assert out["reason"] == "subtitle_track_ambiguous"
    assert out["tracks"][1]["forced"] is True


def test_missing_and_image_only_captions(server: Server) -> None:
    server.item = item([source(streams=[])])
    assert resolver().search(ITEM, SRC, "abandon ship")["reason"] == "no_subtitles"
    server.item = item([source(streams=[sub_stream(3, "PGSSUB")])])
    out = resolver().search(ITEM, SRC, "abandon ship")
    assert out["reason"] == "subtitles_image_only" and "OCR" in out["hint"]
    server.item = item([source(streams=[sub_stream(3, "subrip", IsTextSubtitleStream=False)])])
    assert resolver().search(ITEM, SRC, "abandon ship")["reason"] == "subtitles_image_only"
    assert not any("/Subtitles/" in str(c.request.url) for c in server.mock.calls)


# --- cache, refresh and isolation ---------------------------------------------------------------


def _entries(store: dict[str, Any]) -> list[str]:
    return [k for k in store if k.startswith(STORE_PREFIX) and k != STORE_LRU_KEY]


def test_index_is_cached_but_content_always_rechecked(server: Server) -> None:
    store: dict[str, Any] = {}
    route = server.subtitle(srt())
    first = resolver(store).search(ITEM, SRC, "abandon ship")
    second = resolver(store).search(ITEM, SRC, "abandon ship")
    assert (first["index"], second["index"]) == ("built", "cached")
    assert route.call_count == 2 and server.item_route.call_count == 2
    assert len(_entries(store)) == 1
    json.dumps(store)  # JSON-compatible for ctx.state
    assert KEY not in json.dumps(store) and SECRET_PATH not in json.dumps(store)
    assert (
        first["candidates"][0]["evidence"]["track_fingerprint"]
        == second["candidates"][0]["evidence"]["track_fingerprint"]
    )


def test_changed_content_refreshes_index(server: Server) -> None:
    store: dict[str, Any] = {}
    route = server.subtitle(srt())
    before = resolver(store).search(ITEM, SRC, "abandon ship")
    changed = srt().replace(b"00:25:00,000 --> 00:25:03", b"00:26:00,000 --> 00:26:03")
    route.mock(return_value=httpx.Response(200, content=changed))
    after = resolver(store).search(ITEM, SRC, "abandon ship")
    assert after["index"] == "refreshed"
    assert after["candidates"][0]["start_time_s"] == 1560.0
    assert (
        before["candidates"][0]["evidence"]["track_fingerprint"]
        != after["candidates"][0]["evidence"]["track_fingerprint"]
    )


def test_track_change_with_same_text_rebuilds_with_new_fingerprint(server: Server) -> None:
    store: dict[str, Any] = {}
    server.subtitle(srt())
    before = resolver(store).search(ITEM, SRC, "abandon ship")
    changed = copy.deepcopy(server.item)
    changed["MediaSources"][0]["MediaStreams"][2]["Path"] = "/elsewhere/new.srt"
    server.item = changed
    after = resolver(store).search(ITEM, SRC, "abandon ship")
    assert after["index"] == "refreshed"
    assert (
        before["candidates"][0]["evidence"]["track_fingerprint"]
        != after["candidates"][0]["evidence"]["track_fingerprint"]
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda it: it["MediaSources"][0].update(ETag="src-etag-2"),
        lambda it: it["MediaSources"][0].update(Path="/other/file.mp4"),
        lambda it: it["MediaSources"][0]["MediaStreams"][2].update(Codec="srt"),
        lambda it: it["MediaSources"][0]["MediaStreams"][2].update(Language="spa"),
        lambda it: it.update(Etag="item-etag-2"),
    ],
)
def test_source_or_track_metadata_change_never_reuses_stale_etag(server: Server, change) -> None:
    store: dict[str, Any] = {}
    route = server.subtitle(srt(), headers={"etag": '"sub-1"'})
    resolver(store).search(ITEM, SRC, "abandon ship")
    changed = copy.deepcopy(server.item)
    change(changed)
    server.item = changed
    # A stale index must not be revalidated by its old ETag after metadata changes.
    route.mock(return_value=httpx.Response(304))
    out = resolver(store).search(ITEM, SRC, "abandon ship")
    assert route.calls.last.request.headers.get("if-none-match") is None
    assert out["ok"] is False and out["reason"] == "jellyfin_bad_response"


def test_etag_304_reuses_index_only_when_metadata_unchanged(server: Server) -> None:
    store: dict[str, Any] = {}
    route = server.subtitle(srt(), headers={"etag": '"sub-1"'})
    resolver(store).search(ITEM, SRC, "abandon ship")
    route.mock(return_value=httpx.Response(304))
    out = resolver(store).search(ITEM, SRC, "abandon ship")
    assert route.calls.last.request.headers["if-none-match"] == '"sub-1"'
    assert out["index"] == "cached" and out["candidates"][0]["start_time_s"] == 1500.0


def test_cache_is_isolated_per_user_and_validated(server: Server) -> None:
    store: dict[str, Any] = {}
    server.subtitle(srt())
    resolver(store, USER).search(ITEM, SRC, "abandon ship")
    out = resolver(store, USER2).search(ITEM, SRC, "abandon ship")
    assert out["index"] == "built"
    assert len(_entries(store)) == 2
    # a tampered entry is ignored, never trusted
    for key in _entries(store):
        store[key]["cues"] = [[0, 5, 1, "bad"]]
    again = resolver(store, USER).search(ITEM, SRC, "abandon ship")
    assert again["index"] == "built" and again["candidates"][0]["start_time_s"] == 1500.0


def test_store_is_bounded(server: Server, monkeypatch) -> None:
    store: dict[str, Any] = {"unrelated": 1}
    sources = [source(f"{i:032x}", [sub_stream(2)]) for i in range(1, 6)]
    server.item = item(sources)
    for s in sources:
        server.subtitle(srt(), src=s["Id"])
        assert resolver(store).search(ITEM, s["Id"], "abandon ship")["ok"]
    assert len(_entries(store)) == scene_search.MAX_STORE_ENTRIES
    assert store["unrelated"] == 1
    assert store[STORE_LRU_KEY][-1].startswith(STORE_PREFIX)
    monkeypatch.setattr(scene_search, "MAX_ENTRY_CHARS", 10)
    out = resolver(store).search(ITEM, sources[0]["Id"], "abandon ship")
    assert out["ok"] and out["index"].endswith("_not_stored")


def test_default_store_is_private_memory(server: Server) -> None:
    server.subtitle(srt())
    r = resolver()
    assert r.search(ITEM, SRC, "abandon ship")["index"] == "built"
    assert r.search(ITEM, SRC, "abandon ship")["index"] == "cached"
    assert resolver().search(ITEM, SRC, "abandon ship")["index"] == "built"


# --- failures ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status, reason",
    [
        (401, "jellyfin_auth"),
        (403, "jellyfin_forbidden"),
        (404, "not_found"),
        (400, "jellyfin_bad_request"),
    ],
)
def test_subtitle_http_errors(server: Server, status: int, reason: str) -> None:
    server.subtitle(b"no", status=status)
    out = resolver().search(ITEM, SRC, "abandon ship")
    assert out == {"ok": False, "reason": reason, "hint": out["hint"]}
    assert_no_leaks(out)


def test_extraction_failure_is_honest(server: Server) -> None:
    server.subtitle(b"System.InvalidOperationException at /srv/x", status=500)
    out = resolver().search(ITEM, SRC, "abandon ship")
    assert out["reason"] == "subtitles_unavailable"
    assert "InvalidOperation" not in json.dumps(out)


@pytest.mark.parametrize(
    "body, ctype",
    [
        (b"<html>login</html>", "text/html"),
        (b'{"x": 1}', "application/json"),
        (b"1\n00:00:01,000 -> 00:00:02,000\nbad\n" * 5, "application/x-subrip"),
        (b"\xff\xfe\x00garbage", "application/x-subrip"),
        (b"", "application/x-subrip"),
    ],
)
def test_unusable_subtitle_payloads(server: Server, body: bytes, ctype: str) -> None:
    server.subtitle(body, ctype=ctype)
    out = resolver().search(ITEM, SRC, "abandon ship")
    assert out["ok"] is False and out["reason"] == "subtitles_unusable"
    assert "candidates" not in out


def test_oversized_subtitle_is_refused(server: Server, monkeypatch) -> None:
    monkeypatch.setattr(scene_search, "MAX_SUBTITLE_BYTES", 100)
    server.subtitle(srt())
    assert resolver().search(ITEM, SRC, "abandon ship")["reason"] == "jellyfin_bad_response"


def test_redirect_is_not_followed(server: Server) -> None:
    server.subtitle(status=302, headers={"location": "http://evil.test/steal"})
    evil = server.mock.get(url__startswith="http://evil.test").mock(
        return_value=httpx.Response(200)
    )
    out = resolver().search(ITEM, SRC, "abandon ship")
    assert out["reason"] == "jellyfin_redirect" and not evil.called


def test_timeout_and_connect_errors(server: Server) -> None:
    server.mock.get(sub_url()).mock(side_effect=httpx.ReadTimeout("slow"))
    out = resolver().search(ITEM, SRC, "abandon ship")
    assert out["reason"] == "jellyfin_unreachable" and "8 seconds" in out["hint"]
    server.mock.get(sub_url()).mock(side_effect=httpx.ConnectError(f"refused {BASE} {KEY}"))
    out = resolver().search(ITEM, SRC, "abandon ship")
    assert out["reason"] == "jellyfin_unreachable"
    assert_no_leaks(out)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda it: it.update(Id="ffffffffffffffffffffffffffffffff"),
        lambda it: it.update(MediaSources="nope"),
        lambda it: it["MediaSources"].append({"Id": "not-hex"}),
        lambda it: it["MediaSources"].append(copy.deepcopy(it["MediaSources"][0])),
    ],
)
def test_malformed_item_metadata(server: Server, mutate) -> None:
    broken = copy.deepcopy(server.item)
    mutate(broken)
    server.item = broken
    out = resolver().search(ITEM, SRC, "abandon ship")
    assert out["ok"] is False and out["reason"] in ("jellyfin_bad_response", "no_media_source")


def test_non_json_item_and_unknown_user(server: Server) -> None:
    server.item_route.mock(return_value=httpx.Response(200, content=b"<html>"))
    assert resolver().search(ITEM, SRC, "abandon ship")["reason"] == "jellyfin_bad_response"
    out = resolver(user="99999999999999999999999999999999").search(ITEM, SRC, "abandon ship")
    assert out["ok"] is False


def test_unexpected_errors_do_not_leak(server: Server, monkeypatch) -> None:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError(f"{KEY} {SECRET_PATH}")

    monkeypatch.setattr(scene_search, "parse_subtitles", boom)
    server.subtitle(srt())
    out = resolver().search(ITEM, SRC, "abandon ship")
    assert out["reason"] == "internal_error"
    assert_no_leaks(out)


@pytest.mark.parametrize(
    "kwargs, reason",
    [
        ({"item_id": "nope"}, "invalid_argument"),
        ({"media_source_id": "x" * 32}, "invalid_argument"),
        ({"query": ""}, "invalid_argument"),
        ({"query": "a" * 201}, "invalid_argument"),
        ({"query": "!!!"}, "invalid_argument"),
        ({"limit": 0}, "invalid_argument"),
        ({"limit": 11}, "invalid_argument"),
        ({"limit": True}, "invalid_argument"),
        ({"track_index": True}, "invalid_argument"),
        ({"track_index": -1}, "invalid_argument"),
        ({"language": "en; DROP"}, "invalid_argument"),
    ],
)
def test_argument_validation(server: Server, kwargs: dict[str, Any], reason: str) -> None:
    args: dict[str, Any] = {"item_id": ITEM, "media_source_id": SRC, "query": "abandon ship"}
    args.update(kwargs)
    out = resolver().search(**args)
    assert out["ok"] is False and out["reason"] == reason


def test_closed_resolver(server: Server) -> None:
    r = resolver()
    r.close()
    assert r.search(ITEM, SRC, "abandon ship")["reason"] == "client_closed"


# --- local embedding protocol (NOT a semantic model quality test) -------------------------------


class FakeBagOfWords:
    """Protocol-test double: deterministic hashed bag of words, no model at all."""

    model_id = "fake-bow-protocol-test"

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        vocab = ["storm", "west", "wind", "key", "tin", "stove", "lamp", "ship", "crew"]
        synonyms = {"gale": "storm", "breeze": "wind", "boat": "ship", "sailors": "crew"}
        out = []
        for text in texts:
            words = [synonyms.get(w, w) for w in re.findall(r"[a-z]+", text.lower())]
            out.append([float(words.count(v)) for v in vocab])
        return out


def test_embedding_protocol_disabled_by_default(server: Server) -> None:
    server.subtitle(srt())
    out = resolver().search(ITEM, SRC, "the gale from the west")
    assert out["method"] in ("none", "lexical")
    assert all(c["evidence"]["method"] != "semantic_local" for c in out["candidates"])


def test_embedding_protocol_used_only_without_exact_or_lexical(server: Server) -> None:
    server.subtitle(srt())
    fake = FakeBagOfWords()
    assert isinstance(fake, scene_search.LocalEmbedder)
    exact = resolver(embedder=fake).search(ITEM, SRC, "abandon ship")
    assert exact["method"] == "exact" and fake.calls == 0
    out = resolver(embedder=fake).search(ITEM, SRC, "sailors leave the boat")
    assert out["method"] == "semantic_local" and fake.calls == 1
    cand = out["candidates"][0]
    assert_contract(cand)
    assert cand["evidence"]["model_id"] == "fake-bow-protocol-test"
    assert cand["evidence"]["cue_indices"] == [7] and cand["start_time_s"] == 1500.0


def test_embedding_protocol_bad_output_is_an_error(server: Server) -> None:
    server.subtitle(srt())

    class Broken:
        model_id = "broken"

        def embed(self, texts: Sequence[str]) -> list[list[float]]:
            return [[1.0]]

    out = resolver(embedder=Broken()).search(ITEM, SRC, "sailors leave the boat")
    assert out["ok"] is False and out["reason"] == "semantic_unavailable"
