"""CastPlaybackManager against a scripted fake receiver and a real local relay."""

from __future__ import annotations

import http.client
import json
import threading

import pytest
from cast_fixtures import BBB_ID, OTHER_ID
from fake_cast import BACKDROP, FakeClock, FakeReceiver

from hermes_screen.cast import APP_DEFAULT_MEDIA_RECEIVER, CastError
from hermes_screen.playback import CastPlaybackManager, CastSettings, parse_cast_settings
from hermes_screen.relay import MediaRelay

KEY = "playback-secret-key"
AUTH = f'MediaBrowser Token="{KEY}"'
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


def loads(receiver):
    return [c for c in receiver.commands if c[0] == "LOAD"]


def no_secrets(result, relay=None):
    text = json.dumps(result)
    assert KEY not in text and "/cast/" not in text and "jf.test" not in text
    if relay is not None and relay.current() is not None:
        assert relay.current().token not in text


def test_play_from_idle_verifies_exact_url_playing(manager, receiver, relay):
    result = play(manager)
    assert result["ok"] is True and result["verified"] is True
    assert result["state"] == "playing" and result["action"] == "started"
    assert result["item"] == {"item_id": BBB_ID, "title": "BigBuckBunny_320x180"}
    assert result["relay_expires_in_minutes"] == 25  # 596 s + 15 min margin
    cap = relay.current()
    assert cap is not None and cap.item_id == BBB_ID
    assert loads(receiver) == [("LOAD", cap.media_url, "BigBuckBunny_320x180")]
    assert cap.media_url.startswith(BASE + "/cast/")
    assert receiver.content_id == cap.media_url and receiver.app_id == APP_DEFAULT_MEDIA_RECEIVER
    assert all(s.closed for s in receiver.open_sessions)
    assert relay.running  # media keeps flowing after the call returns
    no_secrets(result, relay)


def test_repeat_play_does_not_restart_confirmed_playback(manager, receiver, relay):
    play(manager)
    token = relay.current().token
    again = play(manager)
    assert again["ok"] is True and again["action"] == "already_playing"
    assert len(loads(receiver)) == 1 and relay.current().token == token


def test_play_after_pause_resumes_same_session(manager, receiver, relay):
    play(manager)
    manager.pause()
    sid = receiver.session_id
    result = play(manager)
    assert result["ok"] is True and result["action"] == "resumed"
    assert ("PLAY", sid) in receiver.commands and len(loads(receiver)) == 1


@pytest.mark.parametrize(
    ("behavior", "evidence"), [("ignore", "timeout"), ("reject", "command_failed")]
)
def test_unconfirmed_resume_keeps_the_loaded_media_link(
    manager, receiver, relay, behavior, evidence
):
    play(manager)
    manager.pause()
    cap = relay.current()
    receiver.on_play = behavior
    result = play(manager)
    assert result["ok"] is False and result["reason"] == "playback_unverified"
    assert result["evidence"] == evidence
    assert relay.current() is cap and not cap.revoked and relay.running
    assert len(loads(receiver)) == 1
    assert manager.pause()["already_paused"] is True


def test_repeat_after_media_ended_loads_with_new_capability(manager, receiver, relay):
    play(manager)
    first = relay.current()
    receiver.state, receiver.idle_reason = "IDLE", "FINISHED"
    result = play(manager)
    assert result["ok"] is True and result["action"] == "started"
    assert len(loads(receiver)) == 2 and first.revoked and relay.current() is not first


def test_other_item_replaces_and_revokes_previous_capability(manager, receiver, relay):
    play(manager)
    first = relay.current()
    result = play(manager, OTHER_ID)
    assert result["ok"] is True and result["item"]["item_id"] == OTHER_ID
    assert first.revoked and relay.current().item_id == OTHER_ID
    host, port = relay.server_address
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request("HEAD", first.media_url.removeprefix(BASE))
    assert conn.getresponse().status == 404
    conn.close()


@pytest.mark.parametrize(
    ("behavior", "reason", "evidence", "kept"),
    [
        ("error", "playback_failed", "receiver_error", False),
        ("load_failed", "playback_failed", "load_failed", False),
        ("stall", "playback_unverified", "loading", True),
        ("silent", "playback_unverified", "app_opened", False),
        ("other", "playback_unverified", "unknown_title_playing", False),
    ],
)
def test_play_failures_are_reported_honestly(
    manager, receiver, relay, behavior, reason, evidence, kept
):
    receiver.on_load = behavior
    result = play(manager)
    assert result["ok"] is False and result["reason"] == reason
    assert result["evidence"] == evidence
    assert result["item"]["item_id"] == BBB_ID
    assert (relay.current() is not None) is kept
    assert relay.running is kept
    no_secrets(result)
    if not kept:
        assert manager.pause()["reason"] == "nothing_playing"


def test_load_rejected_cleans_up(manager, receiver, relay):
    receiver.on_load = "reject"
    result = play(manager)
    assert result == {
        "ok": False,
        "reason": "cast_command_failed",
        "hint": "The Chromecast didn't accept the video.",
    }
    assert relay.current() is None and not relay.running


def test_unreachable_chromecast_starts_no_relay(manager, receiver, relay):
    receiver.unreachable = True
    result = play(manager)
    assert result["reason"] == "cast_unreachable"
    assert not relay.running and relay.current() is None


def test_launch_failure_revokes(manager, receiver, relay):
    receiver.launch_fails = True
    result = play(manager)
    assert result["reason"] == "cast_launch_failed"
    assert relay.current() is None and not relay.running and loads(receiver) == []


def test_unexpected_errors_are_generic(relay, clock):
    def boom(host, port):
        raise RuntimeError(f"secret {KEY} at {BASE}/cast/abc")

    m = CastPlaybackManager(connector=boom, relay=relay, clock=clock)
    result = play(m)
    assert result["reason"] == "cast_failed"
    no_secrets(result)
    assert KEY not in json.dumps(m.pause())


def test_pause_verifies_same_session_then_is_idempotent(manager, receiver):
    play(manager)
    sid = receiver.session_id
    result = manager.pause()
    assert result == {
        "ok": True,
        "state": "paused",
        "verified": True,
        "already_paused": False,
        "item": {"item_id": BBB_ID, "title": "BigBuckBunny_320x180"},
        "position_s": 14.5,
    }
    assert ("PAUSE", sid) in receiver.commands
    again = manager.pause()
    assert again["ok"] is True and again["already_paused"] is True
    assert [c for c in receiver.commands if c[0] == "PAUSE"] == [("PAUSE", sid)]


def test_pause_without_our_playback_contacts_nothing(manager, receiver):
    result = manager.pause()
    assert result["reason"] == "nothing_playing"
    assert receiver.commands == []


def test_pause_leaves_other_app_alone(manager, receiver):
    play(manager)
    receiver.app_id, receiver.state = "233637DE", "PLAYING"  # e.g. another app took over
    result = manager.pause()
    assert result["reason"] == "not_our_playback"
    assert not [c for c in receiver.commands if c[0] == "PAUSE"]


def test_pause_leaves_other_media_in_receiver_alone(manager, receiver):
    play(manager)
    receiver.someone_else_casts()
    assert manager.pause()["reason"] == "not_our_playback"
    assert not [c for c in receiver.commands if c[0] == "PAUSE"]


def test_pause_rejects_same_url_in_a_different_session(manager, receiver):
    play(manager)
    receiver.session_id += 1  # same URL re-loaded by someone else: new media session
    assert manager.pause()["reason"] == "not_our_playback"
    assert not [c for c in receiver.commands if c[0] == "PAUSE"]


@pytest.mark.parametrize(
    ("behavior", "evidence"), [("ignore", "timeout"), ("reject", "command_failed")]
)
def test_pause_unconfirmed_is_not_success(manager, receiver, behavior, evidence):
    play(manager)
    receiver.on_pause = behavior
    result = manager.pause()
    assert result["ok"] is False and result["reason"] == "pause_unverified"
    assert result["evidence"] == evidence


def test_pause_after_media_ended(manager, receiver):
    play(manager)
    receiver.state, receiver.idle_reason = "IDLE", "FINISHED"
    assert manager.pause()["reason"] == "playback_ended"


def test_expiry_ends_ownership_and_releases_relay(manager, receiver, relay, clock):
    play(manager)
    cap = relay.current()
    clock.advance(cap.ttl_s + 1)
    assert manager.pause()["reason"] == "nothing_playing"
    assert cap.revoked and not relay.running
    assert not [c for c in receiver.commands if c[0] == "PAUSE"]


def test_unverified_play_can_be_paused_by_exact_url(manager, receiver):
    receiver.on_load = "stall"
    assert play(manager)["reason"] == "playback_unverified"
    receiver.state = "PLAYING"  # it started later
    result = manager.pause()
    assert result["ok"] is True and result["state"] == "paused"


def test_close_revokes_without_touching_receiver(manager, receiver, relay):
    play(manager)
    cap = relay.current()
    before = list(receiver.commands)
    manager.close()
    manager.close()
    assert cap.revoked and not relay.running
    assert receiver.commands == before
    assert play(manager)["reason"] == "not_configured"
    assert manager.pause()["reason"] == "not_configured"


def test_release_revokes_but_keeps_tools_usable(manager, receiver, relay):
    play(manager)
    cap = relay.current()
    manager.release()
    assert cap.revoked and not relay.running
    assert manager.pause()["reason"] == "nothing_playing"
    assert play(manager)["ok"] is True


def test_contexts_are_isolated(receiver, clock):
    a = CastPlaybackManager(connector=receiver.connect, relay=MediaRelay(clock=clock), clock=clock)
    b = CastPlaybackManager(connector=receiver.connect, relay=MediaRelay(clock=clock), clock=clock)
    try:
        assert play(a)["ok"] is True
        assert b.pause()["reason"] == "nothing_playing"
        assert not [c for c in receiver.commands if c[0] == "PAUSE"]
        assert a.pause()["ok"] is True
    finally:
        a.close()
        b.close()


def test_competing_calls_are_serialized(receiver, relay, clock):
    entered = threading.Event()
    release = threading.Event()
    active = []

    def slow_connect(host, port):
        active.append(1)
        assert len(active) == 1, "overlapping Cast calls"
        entered.set()
        release.wait(5)
        active.pop()
        return receiver.connect(host, port)

    m = CastPlaybackManager(connector=slow_connect, relay=relay, clock=clock, lock_timeout_s=0.2)
    results = []
    worker = threading.Thread(target=lambda: results.append(play(m)))
    worker.start()
    assert entered.wait(5)
    assert m.pause()["reason"] == "busy"
    release.set()
    worker.join(10)
    assert results[0]["ok"] is True
    assert m.pause()["ok"] is True
    m.close()


def test_receiver_starts_from_backdrop(receiver):
    assert receiver.app_id == BACKDROP


# --- settings --------------------------------------------------------------------


def test_parse_settings_ok():
    s = parse_cast_settings("192.168.0.134", "http://192.168.0.126:8765/", "0.0.0.0:8765")
    assert s == CastSettings("192.168.0.134", 8009, "http://192.168.0.126:8765", ("0.0.0.0", 8765))
    s = parse_cast_settings("fe80::1", "http://[fd00::2]:8765", "[::]:8765")
    assert s.advertised_base == "http://[fd00::2]:8765" and s.bind == ("::", 8765)


def test_parse_settings_missing_names_each_setting():
    with pytest.raises(CastError) as exc:
        parse_cast_settings(None, "", None)
    assert exc.value.reason == "not_configured"
    for name in ("chromecast_host", "cast_media_base_url", "cast_relay_bind"):
        assert name in exc.value.hint


@pytest.mark.parametrize(
    ("host", "base", "bind"),
    [
        ("den-tv.local", "http://h:8765", "0.0.0.0:8765"),
        ("192.168.0.134", "https://h:8765", "0.0.0.0:8765"),
        ("192.168.0.134", "http://user:pw@h:8765", "0.0.0.0:8765"),
        ("192.168.0.134", "http://h:8765/prefix", "0.0.0.0:8765"),
        ("192.168.0.134", "http://h:8765?x=1", "0.0.0.0:8765"),
        ("192.168.0.134", "http://h:99999", "0.0.0.0:8765"),
        ("192.168.0.134", "ftp://h", "0.0.0.0:8765"),
        ("192.168.0.134", "http://h:8765", "0.0.0.0:22"),
        ("192.168.0.134", "http://h:8765", "anyhost:8765"),
    ],
)
def test_parse_settings_rejects(host, base, bind):
    with pytest.raises(CastError) as exc:
        parse_cast_settings(host, base, bind)
    assert exc.value.reason == "cast_config"
