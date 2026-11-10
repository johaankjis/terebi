"""PyChromecastSession wiring against the real pychromecast package, no sockets.

``pychromecast.Chromecast`` is replaced by a recorder so we can check what the
adapter asks for: explicit cast type (no get_cast_type), a direct host service
(no mDNS), bounded tries/timeouts, and that nothing is sent to an app that is
not the Default Media Receiver.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

pychromecast = pytest.importorskip("pychromecast")

from hermes_screen import cast as cast_mod  # noqa: E402
from hermes_screen.cast import (  # noqa: E402
    APP_DEFAULT_MEDIA_RECEIVER,
    CastError,
    PyChromecastSession,
    install_log_redaction,
)


class FakeMediaController:
    def __init__(self) -> None:
        self.listeners = []
        self.sent = []
        self.loads = []
        self.status_requests = 0

    def register_status_listener(self, listener):
        self.listeners.append(listener)

    def update_status(self):
        self.status_requests += 1

    def play_media(self, url, content_type, **kwargs):
        self.loads.append((url, content_type, kwargs))

    def send_message(self, data, **kwargs):
        self.sent.append((data, kwargs))


class FakeChromecast:
    instances: list[FakeChromecast] = []
    wait_ok = True

    def __init__(self, cast_info, **kwargs) -> None:
        self.cast_info = cast_info
        self.kwargs = kwargs
        self.media_controller = FakeMediaController()
        self.socket_client = SimpleNamespace(app_namespaces=[])
        self.app_id = "E8C28D3C"
        self.started = []
        self.disconnected = []
        FakeChromecast.instances.append(self)

    def wait(self, timeout=None):
        self.wait_timeout = timeout
        if not FakeChromecast.wait_ok:
            raise pychromecast.error.RequestTimeout("wait", timeout)

    def start_app(self, app_id, force_launch=False, timeout=10):
        self.started.append((app_id, timeout))
        self.app_id = app_id
        self.socket_client.app_namespaces = [cast_mod.MEDIA_NAMESPACE]

    def disconnect(self, timeout=None):
        self.disconnected.append(timeout)


@pytest.fixture(autouse=True)
def fake_pychromecast(monkeypatch):
    FakeChromecast.instances = []
    FakeChromecast.wait_ok = True

    def forbidden(*args, **kwargs):
        raise AssertionError("get_cast_type must not be called")

    monkeypatch.setattr(pychromecast, "Chromecast", FakeChromecast)
    monkeypatch.setattr(pychromecast, "get_cast_type", forbidden)
    monkeypatch.setattr(pychromecast.dial, "get_cast_type", forbidden)


def test_direct_connection_with_explicit_cast_type_and_bounded_timeouts():
    session = PyChromecastSession("192.0.2.50", 8009, connect_timeout=6.0)
    cast = FakeChromecast.instances[0]
    info = cast.cast_info
    assert info.cast_type == pychromecast.const.CAST_TYPE_CHROMECAST
    assert info.host == "192.0.2.50" and info.port == 8009
    assert {type(s).__name__ for s in info.services} == {"HostServiceInfo"}
    assert cast.kwargs == {"tries": 1, "timeout": 6.0, "retry_wait": 0.5}
    assert "zconf" not in cast.kwargs
    assert cast.wait_timeout == 6.0
    assert cast.media_controller.listeners
    cast.socket_client._open_channels = ["receiver-0", "transport-1"]
    session.close()
    session.close()
    assert cast.socket_client._open_channels == []
    assert cast.disconnected == [2.0]


def test_unreachable_is_structured_and_disconnects():
    FakeChromecast.wait_ok = False
    with pytest.raises(CastError) as exc:
        PyChromecastSession("192.0.2.50", 8009)
    assert exc.value.reason == "cast_unreachable"
    assert FakeChromecast.instances[0].disconnected == [2.0]


def test_status_and_commands_never_touch_another_app():
    session = PyChromecastSession("192.0.2.50", 8009)
    cast = FakeChromecast.instances[0]
    cast.app_id = "233637DE"
    session.request_status()
    assert cast.media_controller.status_requests == 0
    with pytest.raises(CastError) as exc:
        session.pause(3)
    assert exc.value.reason == "not_our_playback"
    with pytest.raises(CastError):
        session.load("http://x/cast/t/video.mp4", title="T", duration_s=1.0)
    with pytest.raises(CastError):
        session.seek(3, 60.0)
    assert cast.media_controller.sent == [] and cast.media_controller.loads == []


def test_load_passes_current_time_only_for_an_explicit_start():
    session = PyChromecastSession("192.0.2.50", 8009)
    session.launch_receiver()  # load refuses to send while another app is open
    controller = FakeChromecast.instances[0].media_controller
    session.load("http://h:1/cast/tok/video.mp4", title="BBB", duration_s=596.459)
    session.load(
        "http://h:1/cast/tok2/video.mp4", title="BBB", duration_s=596.459, start_time_s=60.0
    )
    session.load(
        "http://h:1/cast/tok3/video.mp4", title="BBB", duration_s=596.459, start_time_s=0.0
    )
    plain, timed, from_start = controller.loads
    assert "current_time" not in plain[2]  # ordinary LOADs carry no new keyword
    assert timed[2]["current_time"] == 60.0
    assert from_start[2]["current_time"] == 0.0  # explicit zero (not None) is sent


def test_launch_load_pause_play_wire_format():
    session = PyChromecastSession("192.0.2.50", 8009)
    cast = FakeChromecast.instances[0]
    session.launch_receiver()
    assert cast.started == [(APP_DEFAULT_MEDIA_RECEIVER, cast_mod.LAUNCH_TIMEOUT_S)]
    session.launch_receiver()  # already running: no relaunch
    assert len(cast.started) == 1
    session.load("http://h:1/cast/tok/video.mp4", title="BBB", duration_s=596.459)
    url, content_type, kwargs = cast.media_controller.loads[0]
    assert (url, content_type) == ("http://h:1/cast/tok/video.mp4", "video/mp4")
    assert kwargs["stream_type"] == "BUFFERED" and kwargs["title"] == "BBB"
    assert kwargs["media_info"] == {"duration": 596.459}
    session.pause(7)
    session.play(7)
    sent = [data for data, _ in cast.media_controller.sent]
    assert sent == [{"type": "PAUSE", "mediaSessionId": 7}, {"type": "PLAY", "mediaSessionId": 7}]
    session.request_status()
    assert cast.media_controller.status_requests == 1


def test_seek_sends_documented_seek_message():
    session = PyChromecastSession("192.0.2.50", 8009)
    cast = FakeChromecast.instances[0]
    session.launch_receiver()  # _media_ready needs the Default Media Receiver
    session.seek(7, 60.0)
    ((data, kwargs),) = cast.media_controller.sent
    assert data == {
        "type": "SEEK",
        "mediaSessionId": 7,
        "currentTime": 60.0,
        "resumeState": "PLAYBACK_START",
    }
    assert kwargs["inc_session_id"] is True and kwargs["callback_function"] is not None


def test_recorder_turns_statuses_into_ordered_events():
    session = PyChromecastSession("192.0.2.50", 8009)
    listener = FakeChromecast.instances[0].media_controller.listeners[0]
    assert session.mark() == 0
    status = SimpleNamespace(
        content_id="http://h/cast/t/video.mp4",
        media_session_id=1,
        player_state="PLAYING",
        idle_reason=None,
        current_time=2.4,
        duration=596.459,
    )
    listener.new_media_status(status)
    listener.load_media_failed(1, 104)
    listener.command_result(True, {})
    listener.command_result(False, None)
    events = session.events_after(0, 0)
    assert [e.kind for e in events] == ["status", "load_failed", "command_failed"]
    assert events[0].content_id == status.content_id and events[0].session_id == 1
    assert events[0].player_state == "PLAYING" and events[0].position_s == 2.4
    assert session.events_after(3, 0.01) == []


def test_pychromecast_logs_are_redacted(caplog):
    install_log_redaction()
    caplog.set_level(logging.DEBUG)
    token = "A" * 43
    logging.getLogger("pychromecast.controllers.media").debug(
        "Media:Updated status %s", {"contentId": f"http://h:8765/cast/{token}/video.mp4"}
    )
    logging.getLogger("pychromecast.socket_client").debug("payload /cast/%s/video.mp4", token)
    try:
        raise ValueError(f"bad /cast/{token}/video.mp4")
    except ValueError:
        logging.getLogger("pychromecast").exception("failed")
    assert token not in caplog.text
    assert "/cast/<redacted>" in caplog.text
