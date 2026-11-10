"""Saved-description wiring on synthetic timestamps; no live movie timing claims."""

from __future__ import annotations

import copy
import sys

import pytest
from cast_fixtures import BBB_ID, OTHER_ID, cast_item
from test_scene_tools import call, find, routes
from test_scene_tools import plugin as plugin
from test_scene_tools import receiver as receiver
from test_scene_tools import scene_ctx as scene_ctx
from test_scene_tools import secret as secret

SCENES = [
    ("emerging", 12, "Bunny wakes up and comes out of his burrow"),
    ("butterfly", 120, "The bullies attack the butterfly"),
    ("traps", 300, "Bunny sets traps for the bullies"),
]


def save(ctx, label, seconds, **extra):
    return call(
        ctx,
        "library_scene_save",
        {"item_id": BBB_ID, "label": label, "start_time_s": seconds, **extra},
    )


def populate(ctx):
    for label, seconds, description in SCENES:
        assert save(ctx, label, seconds, description=description)["ok"]


def test_clear_paraphrase_uses_saved_offset_and_verified_receiver(scene_ctx, respx_mock):
    routes(respx_mock)
    populate(scene_ctx)
    found = find(scene_ctx, description="Play the part where the rabbit gets up and goes outside")
    assert found["match"] == "clear" and not found["needs_choice"]
    assert found["method"] == "local_saved_description"
    choice = found["candidates"][0]
    assert choice["start_time_s"] == 12
    played = call(scene_ctx, "tv_scene_play", {"candidate_id": choice["candidate_id"]})
    assert played["ok"] and played["verified"]
    assert played["requested_start_time_s"] == 12
    assert played["position_s"] == pytest.approx(12.2)
    assert played["item"]["media_source_id"] == BBB_ID
    assert played["scene_evidence"]["description"] == SCENES[0][2]
    assert call(scene_ctx, "tv_pause", {})["verified"]
    assert all("/Subtitles/" not in str(c.request.url) for c in respx_mock.calls)


@pytest.mark.parametrize(
    ("query", "expected", "count"),
    [("the bullies", "ambiguous", 2), ("the car explodes", "none", 0)],
)
def test_ambiguous_or_unmatched_lookup_never_calls_playback(
    scene_ctx, respx_mock, plugin, monkeypatch, query, expected, count
):
    routes(respx_mock)
    populate(scene_ctx)

    def forbidden(*args, **kwargs):
        pytest.fail("Lookup must not start playback")

    monkeypatch.setattr(sys.modules[plugin.__name__ + ".tools"], "tv_play", forbidden)
    result = find(scene_ctx, description=query)
    assert result["match"] == expected
    assert result["needs_choice"] == (expected == "ambiguous")
    assert len(result["candidates"]) == count
    if expected == "none":
        assert "timestamp" in result["hint"]
    assert all("/Subtitles/" not in str(c.request.url) for c in respx_mock.calls)


def test_existing_marker_and_metadata_survive_description_saves(scene_ctx, respx_mock):
    routes(respx_mock)
    old = save(scene_ctx, "one-minute test scene", 60)["saved"]
    populate(scene_ctx)
    result = save(
        scene_ctx,
        "emerging",
        12,
        description="Bunny wakes and emerges",
        aliases=["the morning exit"],
        end_time_s=24,
    )
    assert result["ok"]
    marker = result["saved"]
    assert save(scene_ctx, "emerging", 12)["saved"] == marker
    assert (
        find(scene_ctx, marker="one-minute test scene")["candidates"][0]["evidence"]
        == old["evidence"]
    )
    assert len(find(scene_ctx)["markers"]) == 4
    assert find(scene_ctx, description="the morning exit")["match"] == "clear"


@pytest.mark.parametrize(
    "extra",
    [
        {"description": ""},
        {"description": "x" * 501},
        {"aliases": "not a list"},
        {"aliases": ["x"] * 9},
        {"aliases": [""]},
        {"end_time_s": 10},
        {"end_time_s": float("nan")},
        {"end_time_s": 1000},
    ],
)
def test_invalid_metadata_does_not_replace_old_state(scene_ctx, respx_mock, extra):
    routes(respx_mock)
    assert save(scene_ctx, "old", 10)["ok"]
    before = copy.deepcopy(scene_ctx.state.data)
    result = save(scene_ctx, "new", 20, **extra)
    assert result["reason"] == "invalid_argument"
    assert scene_ctx.state.data == before


def test_changed_saved_description_invalidates_an_offered_choice(scene_ctx, respx_mock):
    routes(respx_mock)
    populate(scene_ctx)
    choice = find(scene_ctx, description="rabbit gets up and goes outside")["candidates"][0]
    assert save(scene_ctx, "emerging", 12, description="Bunny eats a carrot")["ok"]
    result = call(scene_ctx, "tv_scene_play", {"candidate_id": choice["candidate_id"]})
    assert result["reason"] == "scene_changed"


def test_stale_or_different_edition_never_matches_description(scene_ctx, respx_mock):
    item = cast_item()
    route = routes(respx_mock, item)
    populate(scene_ctx)
    item["MediaSources"][0]["Size"] += 1
    route.respond(json=item)
    assert find(scene_ctx, description="Bunny wakes up")["match"] == "none"
    item["MediaSources"][0]["Id"] = OTHER_ID
    route.respond(json=item)
    assert (
        find(scene_ctx, description="Bunny wakes up", media_source_id=OTHER_ID)["match"] == "none"
    )


def test_description_cannot_mix_with_other_selectors(scene_ctx, respx_mock):
    routes(respx_mock)
    assert (
        find(scene_ctx, description="Bunny wakes", marker="emerging")["reason"]
        == "invalid_argument"
    )
