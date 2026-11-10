"""Explicit start_time_s playback: fresh load at a point and SEEK on running media.

Manager-level tests on the scripted receiver plus a real local relay. Verified
always requires the receiver's own fresh report of the exact capability URL,
PLAYING, and a measured position within the documented tolerance of the
requested point; a sent command or a sender-side timestamp is never enough.
Ordinary no-offset behavior is unchanged and covered in test_playback.py.
"""

from __future__ import annotations

import pytest
from cast_fixtures import BBB_ID, OTHER_ID
from fake_cast import FakeClock, FakeReceiver

from hermes_screen.playback import POSITION_TOLERANCE_S, CastPlaybackManager, CastSettings
from hermes_screen.relay import MediaRelay

# Same rig as test_playback.py (kept local so this module stays self-contained).
AUTH = 'MediaBrowser Token="playback-secret-key"'
BASE = "http://192.0.2.10:8765"
SETTINGS = CastSettings("192.0.2.50", 8009, BASE, ("127.0.0.1", 0))


def source(item_id=BBB_ID, title="BigBuckBunny_320x180", duration=596.459):
    return {
        "item_id": item_id,
        "title": title,
        "type": "Movie",
        "minutes": 10,
        "duration_s": duration,
        "media_source_id": item_id,
    }


def upstream(item_id=BBB_ID):
    return f"http://jf.test/Videos/{item_id}/stream?static=true&mediaSourceId={item_id}"


def loads(receiver):
    return [c for c in receiver.commands if c[0] == "LOAD"]


def no_secrets(result, relay=None):
    text = repr(result)
    assert (
        "playback-secret-key" not in text
        and "/cast/" not in text
        and "jf.test" not in text
        and (relay is None or relay.current() is None or relay.current().token not in text)
    )


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def receiver(clock):
    return FakeReceiver(clock)


@pytest.fixture
def relay(clock):
    r = MediaRelay(clock=clock)
    yield r
    r.close()


@pytest.fixture
def manager(receiver, relay, clock):
    m = CastPlaybackManager(connector=receiver.connect, relay=relay, clock=clock)
    yield m
    m.close()


def play(manager, item_id=BBB_ID, settings=SETTINGS):
    return manager.play(settings, source(item_id), upstream(item_id), AUTH)


def edition(item_id: str = BBB_ID, source_id: str | None = None):
    """A second edition (media source) of the same item."""
    src = source(item_id)
    src["title"] = "Extended cut"
    src["duration_s"] = 700.0
    src["media_source_id"] = source_id or "b" * 32
    return src


def seek_commands(receiver: FakeReceiver):
    return [c for c in receiver.commands if c[0] == "SEEK"]


# --- validation before anything is sent -----------------------------------------------


def test_offset_with_unknown_runtime_is_refused_honestly(manager, receiver, relay):
    bad = source()
    bad["duration_s"] = None
    result = manager.play(SETTINGS, bad, upstream(), AUTH, start_time_s=60.0)
    assert result["ok"] is False and result["reason"] == "unknown_runtime"
    assert "runtime" in result["hint"]
    assert receiver.commands == [] and not relay.running


@pytest.mark.parametrize(
    "start",
    [True, False, "60", float("nan"), float("inf"), float("-inf"), -5.0, -0.01],
)
def test_invalid_offset_values_are_refused_honestly(start, manager, receiver, relay):
    result = manager.play(SETTINGS, source(), upstream(), AUTH, start_time_s=start)
    assert result["ok"] is False and result["reason"] == "invalid_argument"
    assert receiver.commands == [] and not relay.running


def test_out_of_runtime_and_unknown_endian_offsets_are_refused_honestly(manager, receiver, relay):
    for start in (10**400, 596.459, 600.0):
        result = manager.play(SETTINGS, source(), upstream(), AUTH, start_time_s=start)
        assert result["ok"] is False
        assert result["reason"] == "start_time_beyond_runtime", result
    unknown = source()
    unknown["duration_s"] = "unknown"
    result = manager.play(SETTINGS, unknown, upstream(), AUTH, start_time_s=10.0)
    assert result["ok"] is False and result["reason"] == "unknown_runtime"
    assert receiver.commands == [] and not relay.running


# --- fresh launch at an explicit point ------------------------------------------------


def test_fresh_load_with_offset_reports_measured_position(manager, receiver, relay):
    result = manager.play(SETTINGS, source(), upstream(), AUTH, start_time_s=60.0)
    assert result["ok"] is True and result["verified"] is True
    assert result["action"] == "started" and result["state"] == "playing"
    assert result["item"]["media_source_id"] == BBB_ID
    assert result["requested_start_time_s"] == 60.0
    assert result["position_s"] == pytest.approx(60.2)
    assert result["position_tolerance_s"] == POSITION_TOLERANCE_S
    assert receiver.last_load_start_time_s == 60.0
    assert len(loads(receiver)) == 1
    cap = relay.current()
    assert cap is not None and cap.item_id == BBB_ID
    no_secrets(result, relay)


def test_fresh_load_offset_not_verified_when_receiver_starts_from_zero(manager, receiver, relay):
    receiver.on_load = "from_zero"
    result = manager.play(SETTINGS, source(), upstream(), AUTH, start_time_s=60.0)
    assert result["ok"] is False
    # The offset could not be confirmed on the receiver, whatever the medium: same code
    # path as a SEEK that never lands near the requested point.
    assert result["reason"] == "seek_unverified"
    assert result["requested_start_time_s"] == 60.0
    assert result["position_s"] == pytest.approx(0.2)
    assert result["position_tolerance_s"] == POSITION_TOLERANCE_S
    assert result["item"]["item_id"] == BBB_ID
    no_secrets(result, relay)


# --- explicit SEEK on media this context already started --------------------------------


def test_explicit_offset_seeks_running_movie_verifying_measured_point(manager, receiver, relay):
    assert play(manager)["ok"] is True
    sid = receiver.session_id
    token = relay.current().token
    result = manager.play(SETTINGS, source(), upstream(), AUTH, start_time_s=60.0)
    assert result["ok"] is True and result["verified"] is True
    assert result["action"] == "seeked"
    assert result["requested_start_time_s"] == 60.0
    assert result["position_s"] == pytest.approx(60.0)
    assert ("SEEK", sid, 60.0) in receiver.commands
    assert len(loads(receiver)) == 1  # same edition: seeked, never reloaded
    assert relay.current().token == token  # same live capability


def test_explicit_zero_seeks_back_to_the_start_while_playing(manager, receiver):
    assert play(manager)["ok"] is True
    result = manager.play(SETTINGS, source(), upstream(), AUTH, start_time_s=0)
    assert result["ok"] is True and result["action"] == "seeked"
    assert result["requested_start_time_s"] == 0.0
    assert result["position_s"] == 0.0
    assert len(seek_commands(receiver)) == 1


def test_explicit_offset_resumes_paused_movie_near_target(manager, receiver):
    assert play(manager)["ok"] is True
    assert manager.pause()["ok"] is True
    result = manager.play(SETTINGS, source(), upstream(), AUTH, start_time_s=90.0)
    assert result["ok"] is True and result["verified"] is True and result["action"] == "seeked"
    assert result["state"] == "playing"  # resumeState PLAYBACK_START: paused -> playing
    assert result["position_s"] == pytest.approx(90.0)
    assert [c[1] for c in seek_commands(receiver)] == [receiver.session_id]


def test_omitted_offset_after_pause_still_resumes_without_seek_or_restart(manager, receiver):
    assert play(manager)["ok"] is True
    assert manager.pause()["ok"] is True
    result = play(manager)
    assert result["ok"] is True and result["action"] == "resumed"
    assert result["requested_start_time_s"] is None
    assert result["position_tolerance_s"] is None
    assert seek_commands(receiver) == []
    assert len(loads(receiver)) == 1


# --- seek failure modes report honestly -------------------------------------------------


def test_seek_that_stays_buffering_reports_seek_unverified_and_keeps_link(manager, receiver, relay):
    assert play(manager)["ok"] is True
    cap = relay.current()
    receiver.on_seek = "stall"
    result = manager.play(SETTINGS, source(), upstream(), AUTH, start_time_s=60.0)
    assert result["ok"] is False
    assert result["reason"] == "seek_unverified"
    assert result["evidence"] == "timeout"
    assert result["requested_start_time_s"] == 60.0
    assert result["position_s"] == pytest.approx(60.0)  # moved, but never reported PLAYING
    assert result["item"]["media_source_id"] == BBB_ID
    assert relay.current() is cap and not cap.revoked and relay.running  # it is still loaded

    # Media is still ours: a later call with the offset verifies.
    receiver.on_seek = "ok"
    again = manager.play(SETTINGS, source(), upstream(), AUTH, start_time_s=120.0)
    assert again["ok"] is True and again["action"] == "seeked"
    assert again["position_s"] == pytest.approx(120.0)


def test_seek_rejected_reports_command_failure(manager, receiver):
    assert play(manager)["ok"] is True
    receiver.on_seek = "reject"
    result = manager.play(SETTINGS, source(), upstream(), AUTH, start_time_s=60.0)
    assert result["ok"] is False and result["reason"] == "seek_unverified"
    assert result["evidence"] == "command_failed"  # like an unconfirmed PAUSE
    no_secrets(result)


def test_seek_without_measured_position_is_never_verified(manager, receiver, relay):
    assert play(manager)["ok"] is True
    cap = relay.current()
    receiver.on_seek = "ok_noposition"
    result = manager.play(SETTINGS, source(), upstream(), AUTH, start_time_s=60.0)
    assert result["ok"] is False and result["reason"] == "seek_unverified"
    assert result["position_s"] == pytest.approx(0.2)  # the last measured position
    assert result["requested_start_time_s"] == 60.0
    assert relay.current() is cap and not cap.revoked


def test_seek_that_receiver_ignores_is_reported_with_its_measured_position(manager, receiver):
    assert play(manager)["ok"] is True
    receiver.on_seek = "wrongpos"  # PLAYING reported, position never moves
    result = manager.play(SETTINGS, source(), upstream(), AUTH, start_time_s=60.0)
    assert result["ok"] is False and result["reason"] == "seek_unverified"
    assert result["position_s"] == pytest.approx(0.2)
    assert result["evidence"] == "timeout"


def test_seek_on_a_wrong_media_session_changes_nothing_on_the_receiver(clock):
    """Fake-level contract: a SEEK for a stale media session id does nothing."""
    receiver = FakeReceiver(clock)
    session = receiver.connect("192.0.2.50", 8009)
    session.load("http://h/cast/t/video.mp4", title="T", duration_s=596.459)
    before = (receiver.state, receiver.position, receiver.session_id)
    session.seek(receiver.session_id + 1, 60.0)
    assert (receiver.state, receiver.position, receiver.session_id) == before


# --- editions (same item, different media source) ----------------------------------------


def test_same_item_different_edition_freshly_loads_a_new_capability(manager, receiver, relay):
    assert play(manager)["ok"] is True
    first = relay.current()
    result = manager.play(SETTINGS, edition(), upstream(BBB_ID), AUTH, start_time_s=60.0)
    assert result["ok"] is True and result["action"] == "started"
    assert result["item"]["media_source_id"] == "b" * 32
    assert first.revoked and relay.current() is not first
    assert len(loads(receiver)) == 2
    assert receiver.last_load_start_time_s == 60.0
    assert relay.current().media_url == receiver.content_id  # exact pinned capability


def test_after_edition_switch_repeat_play_resumes_the_new_edition(manager, receiver, relay):
    assert play(manager)["ok"] is True
    assert manager.play(SETTINGS, edition(), upstream(BBB_ID), AUTH)["ok"] is True
    token = relay.current().token
    result = manager.play(SETTINGS, edition(), upstream(BBB_ID), AUTH, start_time_s=30.0)
    assert result["ok"] is True and result["action"] == "seeked"
    assert relay.current().token == token and len(loads(receiver)) == 2


def test_back_to_the_first_edition_after_a_switch_freshly_loads_again(manager, receiver, relay):
    assert play(manager)["ok"] is True
    assert manager.play(SETTINGS, edition(), upstream(BBB_ID), AUTH)["ok"] is True
    result = play(manager)
    assert result["ok"] is True and result["action"] == "started"
    assert result["item"]["media_source_id"] == BBB_ID
    assert len(loads(receiver)) == 3


def test_other_item_with_offset_still_replaces_the_capability(manager, receiver, relay):
    assert play(manager)["ok"] is True
    first = relay.current()
    result = manager.play(SETTINGS, source(OTHER_ID), upstream(OTHER_ID), AUTH, start_time_s=15.0)
    assert result["ok"] is True and result["item"]["item_id"] == OTHER_ID
    assert first.revoked and len(loads(receiver)) == 2
    assert receiver.last_load_start_time_s == 15.0
