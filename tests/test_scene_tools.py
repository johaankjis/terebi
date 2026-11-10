"""Registered scene tools with real resolver + mocked Jellyfin; no hardware."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
import test_tv_tools as tv_fixtures
from cast_fixtures import BBB_ID, OTHER_ID, cast_item
from test_tv_tools import JF, KEY, UID, Ctx, free_port

plugin = tv_fixtures.plugin
receiver = tv_fixtures.receiver
secret = tv_fixtures.secret


class State:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return copy.deepcopy(self.data.get(key, default))

    def set(self, key, value):
        self.data[key] = copy.deepcopy(value)


@pytest.fixture
def scene_ctx(plugin, secret, receiver):
    ctx = Ctx(free_port())
    ctx.state = State()
    plugin.register(ctx)
    yield ctx
    for callback in ctx.unload:
        callback()


def call(ctx, tool, args, who="conversation-one"):
    return json.loads(ctx.tools[tool]["handler"](args, conversation_id=who))


def routes(router, item=None):
    item = item or cast_item()
    router.get(f"{JF}/Users/{UID}").respond(json={"Id": UID, "Name": "homelab"})
    return router.get(f"{JF}/Items/{BBB_ID}").respond(json=item)


def find(ctx, **kwargs):
    return call(ctx, "library_scene_find", {"item_id": BBB_ID, **kwargs})


def test_dialogue_query_returns_original_timestamp_and_choice(scene_ctx, respx_mock):
    item = cast_item()
    item["MediaSources"][0]["MediaStreams"].append(
        {"Type": "Subtitle", "Index": 2, "Codec": "subrip", "Language": "eng"}
    )
    routes(respx_mock, item)
    payload = (Path(__file__).parent / "fixtures/scenes/lighthouse.en.srt").read_bytes()
    respx_mock.get(f"{JF}/Videos/{BBB_ID}/{BBB_ID}/Subtitles/2/Stream.srt").respond(
        content=payload, headers={"Content-Type": "application/x-subrip"}
    )
    result = find(scene_ctx, query="In the blue tin by the old stove")
    assert result["ok"] and result["method"] == "exact"
    candidate = result["candidates"][0]
    assert candidate["start_time_s"] == 66
    assert candidate["timestamp"] == "00:01:06.000"
    assert candidate["media_source_id"] == BBB_ID
    assert candidate["evidence"]["cue_indices"] == [4, 5]
    assert candidate["candidate_id"]
    assert KEY not in json.dumps(result)
    assert any(key == "scene_cache_v1" for key in scene_ctx.state.data)


def test_multiple_matches_remain_candidates(scene_ctx, respx_mock):
    item = cast_item(RunTimeTicks=1000 * 10_000_000)
    item["MediaSources"][0]["MediaStreams"].append(
        {"Type": "Subtitle", "Index": 2, "Codec": "subrip", "Language": "eng"}
    )
    routes(respx_mock, item)
    payload = (Path(__file__).parent / "fixtures/scenes/lighthouse.en.srt").read_bytes()
    respx_mock.get(f"{JF}/Videos/{BBB_ID}/{BBB_ID}/Subtitles/2/Stream.srt").respond(content=payload)
    result = find(scene_ctx, query="Keep the lamp burning")
    assert result["needs_choice"] and len(result["candidates"]) == 2


def test_movie_ambiguity_does_not_guess(scene_ctx, respx_mock):
    routes(respx_mock)
    respx_mock.get(f"{JF}/Items").respond(
        json={"Items": [cast_item(), cast_item(OTHER_ID)], "TotalRecordCount": 2}
    )
    result = call(scene_ctx, "library_scene_find", {"movie": "Bunny", "query": "leaving"})
    assert result["reason"] == "movie_ambiguous" and len(result["movies"]) == 2


def test_edition_ambiguity_then_explicit_source(scene_ctx, respx_mock):
    item = cast_item()
    item["MediaSources"].append({**copy.deepcopy(item["MediaSources"][0]), "Id": OTHER_ID})
    routes(respx_mock, item)
    assert find(scene_ctx, start_time_s=60)["reason"] == "edition_ambiguous"
    result = find(scene_ctx, media_source_id=OTHER_ID, start_time_s=60)
    assert result["candidates"][0]["media_source_id"] == OTHER_ID
    assert find(scene_ctx, media_source_id="d" * 32)["reason"] == "edition_mismatch"


def test_marker_saved_for_edition_and_updates_idempotently(scene_ctx, respx_mock):
    routes(respx_mock)
    args = {"item_id": BBB_ID, "media_source_id": BBB_ID, "label": "User scene", "start_time_s": 60}
    first = call(scene_ctx, "library_scene_save", args)
    again = call(scene_ctx, "library_scene_save", {**args, "start_time_s": 61.5})
    assert first["ok"] and again["ok"]
    assert first["saved"]["evidence"]["marker_id"] == again["saved"]["evidence"]["marker_id"]
    result = find(scene_ctx, marker="user SCENE")
    assert len(result["candidates"]) == 1 and result["candidates"][0]["start_time_s"] == 61.5
    assert result["candidates"][0]["evidence"]["method"] == "user_supplied"


@pytest.mark.parametrize("offset", [-1, True, float("nan"), float("inf"), 1 << 2000, 600, "60"])
def test_invalid_timestamps_cannot_be_saved(scene_ctx, respx_mock, offset):
    routes(respx_mock)
    result = call(
        scene_ctx,
        "library_scene_save",
        {"item_id": BBB_ID, "label": "scene", "start_time_s": offset},
    )
    assert result["reason"] == "invalid_argument"
    assert not any(key.startswith("scene_markers") for key in scene_ctx.state.data)


def test_captionless_scene_offers_marker_or_timestamp(scene_ctx, respx_mock):
    routes(respx_mock)
    assert find(scene_ctx, query="the rabbit dances")["reason"] == "no_subtitles"
    candidate = find(scene_ctx, start_time_s=60)["candidates"][0]
    assert candidate["evidence"]["kind"] == "timestamp"
    assert candidate["evidence"]["method"] == "user_supplied"
    assert len(candidate["evidence"]["source_fingerprint"]) == 64


def test_scene_play_handoff_and_conversation_isolation(scene_ctx, respx_mock, plugin, monkeypatch):
    routes(respx_mock)
    choice = find(scene_ctx, start_time_s=60)["candidates"][0]
    assert (
        call(scene_ctx, "tv_scene_play", {"candidate_id": choice["candidate_id"]}, who="other")[
            "reason"
        ]
        == "scene_choice_missing"
    )
    module = sys.modules[plugin.__name__ + ".tools"]
    passed = []

    def fake_play(args, **kwargs):
        passed.append(args)
        return json.dumps({"ok": True, "state": "playing", "verified": True, "position_s": 60})

    monkeypatch.setattr(module, "tv_play", fake_play)
    result = call(scene_ctx, "tv_scene_play", {"candidate_id": choice["candidate_id"]})
    assert result["ok"] and result["scene_evidence"]["kind"] == "timestamp"
    assert passed == [{"item_id": BBB_ID, "media_source_id": BBB_ID, "start_time_s": 60}]


def test_expired_choice_refused(scene_ctx, respx_mock, plugin, monkeypatch):
    routes(respx_mock)
    module = sys.modules[plugin.__name__ + ".scene_tools"]
    now = [0]
    service = module.SceneTools(scene_ctx, None, clock=lambda: now[0])
    choice = json.loads(service.call("find", {"item_id": BBB_ID, "start_time_s": 60}, "one"))
    now[0] = 901
    result = json.loads(
        service.call("play", {"candidate_id": choice["candidates"][0]["candidate_id"]}, "one")
    )
    assert result["reason"] == "scene_choice_expired"


def test_changed_subtitle_refuses_old_candidate(scene_ctx, respx_mock):
    item = cast_item()
    item["MediaSources"][0]["MediaStreams"].append(
        {"Type": "Subtitle", "Index": 2, "Codec": "subrip", "Language": "eng"}
    )
    routes(respx_mock, item)
    route = respx_mock.get(f"{JF}/Videos/{BBB_ID}/{BBB_ID}/Subtitles/2/Stream.srt")
    route.respond(content=b"1\n00:01:00,000 --> 00:01:03,000\nWe must leave now.\n")
    choice = find(scene_ctx, query="We must leave now")["candidates"][0]
    route.respond(content=b"1\n00:02:00,000 --> 00:02:03,000\nWe must leave now.\n")
    result = call(scene_ctx, "tv_scene_play", {"candidate_id": choice["candidate_id"]})
    assert result["reason"] == "scene_changed"


def test_real_registered_marker_play_seeks_and_pause(scene_ctx, respx_mock, receiver):
    routes(respx_mock)
    saved = call(
        scene_ctx,
        "library_scene_save",
        {"item_id": BBB_ID, "label": "one-minute test scene", "start_time_s": 60},
    )
    assert saved["ok"]
    found = find(scene_ctx, marker="one-minute test scene")
    candidate = found["candidates"][0]
    args = {"candidate_id": candidate["candidate_id"]}
    played = call(scene_ctx, "tv_scene_play", args)
    assert played["ok"] and played["verified"]
    assert played["position_s"] == pytest.approx(60.2)
    assert played["requested_start_time_s"] == 60
    assert played["item"]["media_source_id"] == BBB_ID
    paused = call(scene_ctx, "tv_pause", {})
    assert paused["ok"] and paused["state"] == "paused"
    sought = call(scene_ctx, "tv_scene_play", args)
    assert sought["ok"] and sought["action"] == "seeked"
    assert sought["position_s"] == pytest.approx(60.0)
    assert call(scene_ctx, "tv_pause", {})["ok"]
    assert KEY not in json.dumps(scene_ctx.state.data)


def test_changed_edition_invalidates_saved_marker(scene_ctx, respx_mock):
    item = cast_item()
    route = routes(respx_mock, item)
    assert call(
        scene_ctx, "library_scene_save", {"item_id": BBB_ID, "label": "scene", "start_time_s": 60}
    )["ok"]
    item["MediaSources"][0]["Size"] += 1
    route.respond(json=item)
    assert find(scene_ctx, marker="scene")["reason"] == "marker_stale"


@pytest.mark.parametrize("offset", [True, -1, float("nan"), float("inf"), "60", None])
def test_tv_play_rejects_bad_offset_before_http(scene_ctx, respx_mock, offset):
    result = call(scene_ctx, "tv_play", {"item_id": BBB_ID, "start_time_s": offset})
    assert result["reason"] == "invalid_argument"
    assert len(respx_mock.calls) == 0


def test_movie_must_be_identified_before_scene_search(scene_ctx, respx_mock):
    result = call(scene_ctx, "library_scene_find", {"query": "leaving"})
    assert result["reason"] == "movie_required"
    assert not respx_mock.calls
