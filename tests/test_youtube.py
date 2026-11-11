"""YouTube parsing, bounded API search and exact-video verification; no hardware."""

import httpx
import pytest

from hermes_screen.youtube import APP_YOUTUBE, YouTubePlayback, search, video_id

VID = "aqz-KE-bpKQ"
OTHER = "M7lc1UVf-VE"


@pytest.mark.parametrize(
    "link",
    [
        VID,
        f"https://www.youtube.com/watch?v={VID}",
        f"https://youtu.be/{VID}?si=share",
        f"https://m.youtube.com/watch?v={VID}&list=ignored",
        f"https://youtube.com/shorts/{VID}",
        f"https://youtube.com/embed/{VID}",
        f"https://youtube.com/live/{VID}",
    ],
)
def test_video_links_normalize_without_network(link):
    assert video_id(link) == VID


@pytest.mark.parametrize(
    "link",
    [
        None,
        42,
        "",
        "short",
        "a" * 2049,
        f"https://youtube.com.evil.test/watch?v={VID}",
        f"https://evil.test/{VID}",
        f"http://youtube.com/watch?v={VID}",
        f"https://user@youtube.com/watch?v={VID}",
        f"https://youtube.com:443/watch?v={VID}",
        f"https://youtu.be/{VID}/more",
        f"https://youtube.com/watch?v={VID}&v={OTHER}",
        "https://youtube.com/playlist?list=abc",
        f"https://youtube.com/watch?v={VID}&t=60",
        f"https://youtu.be/{VID}#t=1",
        "file:///etc/passwd",
        "https://youtube.com/watch?v=has%20spaces",
    ],
)
def test_invalid_urls_and_unsupported_offsets(link):
    with pytest.raises(ValueError):
        video_id(link)


def event(vid=VID, state="PLAYING", sid=7, app=APP_YOUTUBE):
    return {
        "app_id": app,
        "video_id": vid,
        "state": state,
        "session_id": sid,
        "position_s": 2.5,
        "title": "Bunny",
    }


class Fake:
    def __init__(self, initial=None, response=None, failure=None):
        self.now = 0.0
        self.events = []
        self.current = initial
        self.response = response or event()
        self.failure = failure
        self.closed = False
        self.actions = []
        self.active_app = initial["app_id"] if initial else "B94F303E"

    def app_id(self):
        return self.active_app

    def emit(self, e):
        if e is not None:
            self.current = {**e, "seq": len(self.events) + 1}
            self.events.append(self.current)

    def mark(self):
        return len(self.events)

    def snapshot(self):
        return self.current

    def request_status(self):
        self.emit(self.current)

    def load(self, requested):
        self.actions.append(("load", requested))
        self.active_app = APP_YOUTUBE
        if self.failure:
            raise self.failure
        self.emit(self.response)

    def events_after(self, mark, timeout):
        self.now += timeout
        return self.events[mark:]

    def pause(self, session_id):
        self.actions.append(("pause",))
        self.emit({**self.current, "state": "PAUSED"})

    def resume(self, session_id):
        self.actions.append(("resume",))
        self.emit({**self.current, "state": "PLAYING"})

    def close(self):
        self.closed = True


def manager(fake):
    return YouTubePlayback(transport_factory=lambda _: fake, clock=lambda: fake.now)


def test_exact_video_and_fresh_status_required():
    fake = Fake()
    result = manager(fake).call("192.0.2.1", VID)
    assert result["ok"] and result["verified"]
    assert result["video_id"] == VID and result["evidence"] == "receiver_exact_video"
    assert fake.actions == [("load", VID)] and fake.closed


@pytest.mark.parametrize(
    "response",
    [
        event(vid=OTHER),
        event(state="BUFFERING"),
        event(state="IDLE"),
        event(state="PLAYING", app="OTHERAPP"),
        event(sid=None),
        event(sid=True),
        event(vid=None),
    ],
)
def test_wrong_video_or_app_or_buffering_is_not_success(response):
    fake = Fake(response=response)
    result = manager(fake).call("192.0.2.1", VID)
    assert not result["ok"] and result["reason"] == "youtube_playback_unverified"
    assert result["outcome"] == "app_opened" and fake.closed


def test_opened_app_control_exception_is_honest_and_sanitized():
    fake = Fake(failure=RuntimeError("private-lounge-token"))
    result = manager(fake).call("192.0.2.1", VID)
    assert result["outcome"] == "app_opened" and not result["verified"]
    assert "private-lounge-token" not in str(result) and fake.closed


def test_repeated_play_does_not_restart_and_paused_video_resumes():
    for state, actions in [("PLAYING", []), ("PAUSED", [("resume",)])]:
        fake = Fake(initial=event(state=state))
        result = manager(fake).call("192.0.2.1", VID)
        assert result["ok"] and fake.actions == actions


def test_pause_requires_owned_video_and_same_media_session():
    fake = Fake()
    m = manager(fake)
    assert not m.call("192.0.2.1", pause=True)["ok"]
    fake.closed = False
    assert m.call("192.0.2.1", VID)["ok"]
    paused = m.call("192.0.2.1", pause=True)
    assert paused["ok"] and paused["state"] == "PAUSED" and paused["media_session_id"] == 7
    assert m.call("192.0.2.1", pause=True)["ok"]
    fake.current = event(sid=8)
    assert m.call("192.0.2.1", pause=True)["reason"] == "not_our_playback"
    fake.current = event(vid=OTHER)
    assert m.call("192.0.2.1", pause=True)["reason"] == "not_our_playback"


def test_missing_host_never_connects():
    def forbidden(_):
        pytest.fail("must validate before connection")

    assert YouTubePlayback(forbidden).call("invalid", VID)["reason"] == "not_configured"


def test_optional_search_key_and_bounded_queries():
    assert search("Bunny", None)["reason"] == "youtube_search_not_configured"
    for q in ("", None, "x" * 201):
        assert search(q, "private-key")["reason"] == "invalid_argument"


def test_official_search_title_channel_choices_and_secret_header(respx_mock):
    route = respx_mock.get("https://www.googleapis.com/youtube/v3/search").respond(
        json={
            "items": [
                {
                    "id": {"videoId": v},
                    "snippet": {"title": "Bunny &amp; Friends", "channelTitle": "Official"},
                }
                for v in (VID, OTHER)
            ]
        }
    )
    result = search("Bunny", "private-key")
    assert result["ok"] and result["needs_choice"]
    assert result["candidates"][0] == {
        "choice": 1,
        "video_id": VID,
        "title": "Bunny & Friends",
        "channel": "Official",
    }
    request = route.calls[0].request
    assert request.headers["X-Goog-Api-Key"] == "private-key"
    assert "private-key" not in str(request.url) and "private-key" not in str(result)
    assert request.url.params["type"] == "video"
    assert request.extensions["timeout"]["read"] == 8


@pytest.mark.parametrize(
    "status,reason",
    [
        (401, "youtube_search_access"),
        (403, "youtube_search_access"),
        (429, "youtube_search_access"),
        (500, "youtube_search_unavailable"),
        (302, "youtube_search_unavailable"),
    ],
)
def test_search_failure_does_not_echo_response_or_follow_redirects(respx_mock, status, reason):
    respx_mock.get("https://www.googleapis.com/youtube/v3/search").respond(
        status, text="private-key", headers={"Location": "https://evil.test/"}
    )
    result = search("Bunny", "private-key")
    assert result["reason"] == reason and "private-key" not in str(result)


def test_search_timeout_and_malformed_data(respx_mock):
    route = respx_mock.get("https://www.googleapis.com/youtube/v3/search")
    route.side_effect = httpx.ReadTimeout("private-key")
    assert search("Bunny", "private-key")["reason"] == "youtube_search_unavailable"
    route.side_effect = None
    route.respond(json={"items": None})
    assert search("Bunny", "private-key")["reason"] == "youtube_search_unavailable"


def test_other_device_cannot_inherit_pause_ownership():
    fake = Fake()
    m = manager(fake)
    assert m.call("192.0.2.1", VID)["ok"]
    assert m.call("192.0.2.2", pause=True)["reason"] == "not_our_playback"
    assert ("pause",) not in fake.actions


def test_media_commands_pin_session_and_never_launch_another_app():
    from types import SimpleNamespace

    from hermes_screen.cast import CastError
    from hermes_screen.youtube import MEDIA_NAMESPACE, YouTubeTransport

    sent = []
    transport = YouTubeTransport.__new__(YouTubeTransport)
    transport.connection = SimpleNamespace(app_id=lambda: APP_YOUTUBE)
    transport.cast = SimpleNamespace(
        socket_client=SimpleNamespace(app_namespaces={MEDIA_NAMESPACE}),
        media_controller=SimpleNamespace(send_message=lambda msg: sent.append(msg)),
    )
    transport.pause(123)
    transport.resume(123)
    assert sent == [
        {"type": "PAUSE", "mediaSessionId": 123},
        {"type": "PLAY", "mediaSessionId": 123},
    ]
    transport.connection.app_id = lambda: "B94F303E"
    with pytest.raises(CastError):
        transport.pause(456)
    assert len(sent) == 2


def test_requested_video_receiver_error_is_unavailable_not_success():
    fake = Fake(response={**event(state="IDLE"), "idle_reason": "ERROR"})
    result = manager(fake).call("192.0.2.1", VID)
    assert result["reason"] == "youtube_video_unavailable" and not result["verified"]


def test_mdx_screen_and_lounge_capabilities_are_not_debug_logged(caplog):
    import logging

    from hermes_screen.cast import install_log_redaction

    install_log_redaction()
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("pychromecast.socket_client").debug(
            "urn:x-cast:com.google.youtube.mdx screenId=private-screen"
        )
        logging.getLogger("urllib3.connectionpool").debug(
            "POST /api/lounge/bc/bind?gsessionid=private-session"
        )
    assert "private-screen" not in caplog.text and "private-session" not in caplog.text
