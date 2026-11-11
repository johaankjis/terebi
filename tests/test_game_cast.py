"""Game Cast handshake tests; no device, discovery, or real Cast socket."""

import logging
from types import SimpleNamespace

import pytest

from hermes_screen import game_cast
from hermes_screen.cast import CastError, install_log_redaction

SID = "session-id-1234567890"
TOKEN = "viewer-token-1234567890123456789"
APP = "AB12CD34"


class FakeTransport:
    def __init__(self, *, mutate=None, error=None):
        self.now = 0.0
        self.sent = None
        self.closed = False
        self.mutate = mutate or (lambda e: e)
        self.error = error
        self.match = True

    def launch(self):
        if self.error:
            raise self.error

    def matches_app(self):
        return self.match

    def send(self, data):
        self.sent = data

    def receive(self, timeout):
        self.now += timeout
        return self.mutate(
            {
                "type": "DISPLAY_RENDERED",
                "session_id": SID,
                "request_id": self.sent["request_id"],
                "phase": "waiting_for_player",
                "revision": 1,
            }
        )

    def close(self):
        self.closed = True


def launch(fake, **kwargs):
    return game_cast.launch_game_display(
        "192.0.2.5",
        APP,
        SID,
        TOKEN,
        transport_factory=lambda *args: fake,
        clock=lambda: fake.now,
        ack_timeout_s=0.6,
        **kwargs,
    )


def test_only_matching_render_ack_is_success_and_capability_is_not_returned():
    fake = FakeTransport()
    result = launch(fake)
    assert result["ok"] and result["evidence"] == "receiver_rendered_session"
    assert result["phase"] == "waiting_for_player"
    assert set(fake.sent) == {"type", "session_id", "request_id", "display_token"}
    assert fake.sent["display_token"] == TOKEN
    assert TOKEN not in str(result) and fake.sent["request_id"] not in str(result)
    assert fake.closed


@pytest.mark.parametrize(
    "change",
    [
        {"session_id": "other-session-123456"},
        {"request_id": "old-challenge-12345"},
        {"type": "LAUNCHED"},
        {"revision": 0},
        {"revision": True},
        {"revision": "1"},
        {"phase": "unknown"},
    ],
)
def test_launch_or_wrong_stale_malformed_ack_never_proves_display(change):
    fake = FakeTransport(mutate=lambda e: {**e, **change})
    result = launch(fake)
    assert not result["ok"] and result["reason"] == "receiver_render_unverified"
    assert fake.closed


def test_changed_app_or_no_ack_does_not_claim_ready():
    for fake in [FakeTransport(), FakeTransport(mutate=lambda e: None)]:
        fake.match = False
        assert not launch(fake)["ok"]
        assert fake.closed


def test_receiver_failure_and_connection_exception_are_sanitized(caplog):
    caplog.set_level(logging.INFO, logger=game_cast.__name__)
    fake = FakeTransport(mutate=lambda e: {**e, "type": "DISPLAY_FAILED", "reason": TOKEN})
    result = launch(fake)
    assert result["reason"] == "receiver_display_failed" and TOKEN not in str(result)
    fake = FakeTransport(error=RuntimeError(TOKEN))
    assert launch(fake)["reason"] == "games_cast_failed" and fake.closed
    fake = FakeTransport(error=CastError("cast_unreachable", "Check Chromecast power."))
    assert launch(fake)["reason"] == "cast_unreachable" and fake.closed
    assert "stage=launch_and_namespace exception_type=RuntimeError" in caplog.text
    assert TOKEN not in caplog.text and SID not in caplog.text


@pytest.mark.parametrize(
    "host,app,sid,token",
    [
        ("http://192.0.2.5", APP, SID, TOKEN),
        ("192.0.2.5", "CC1AD845", SID, TOKEN),
        ("192.0.2.5", "unknown", SID, TOKEN),
        ("192.0.2.5", APP, "short", TOKEN),
        ("192.0.2.5", APP, SID, "bad token"),
    ],
)
def test_invalid_config_never_connects(host, app, sid, token):
    def forbidden(*args):
        pytest.fail("Must not connect for invalid configuration")

    assert (
        game_cast.launch_game_display(host, app, sid, token, transport_factory=forbidden)["reason"]
        == "games_cast_config"
    )


def test_namespace_debug_and_exception_payloads_are_suppressed(caplog):
    install_log_redaction()
    logger = logging.getLogger("pychromecast.socket_client")
    with caplog.at_level(logging.DEBUG):
        logger.debug("Sending %s %s", game_cast.NAMESPACE, {"display_token": TOKEN})
        try:
            raise RuntimeError("display_token=" + TOKEN)
        except RuntimeError:
            logger.exception("Failed send")
        logger.info("Still logging safe operational messages")
    assert TOKEN not in caplog.text
    assert "Still logging" in caplog.text


def test_real_controller_adapter_sends_only_custom_namespace_and_leaves_app_running(monkeypatch):
    sent = []
    socket = SimpleNamespace(
        send_platform_message=lambda *a, **k: pytest.fail("No platform control message"),
        send_app_message=lambda *a, **k: sent.append((a, k)),
        app_namespaces={game_cast.NAMESPACE},
        receiver_controller=SimpleNamespace(app_id=APP),
    )
    cast = SimpleNamespace(
        socket_client=socket,
        start_app=lambda app, timeout: sent.append((app, timeout)),
        register_handler=lambda handler: handler.registered(socket),
    )
    connection = SimpleNamespace(
        _cast=cast, app_id=lambda: APP, close=lambda: sent.append("disconnected")
    )
    monkeypatch.setattr(game_cast, "PyChromecastSession", lambda *a: connection)
    transport = game_cast.GameCastTransport("192.0.2.5", APP)
    transport.launch()
    transport.send({"display_token": TOKEN})
    transport.controller.receive_message(None, {"type": "DISPLAY_RENDERED"})
    assert transport.receive(0)["type"] == "DISPLAY_RENDERED"
    transport.close()
    args, kwargs = sent[1]
    assert args == (game_cast.NAMESPACE, {"display_token": TOKEN})
    assert kwargs["no_add_request_id"] is True
    assert sent[-1] == "disconnected"


class StopTransport:
    def __init__(self, *, active=APP, event_type="SESSION_ENDING", go_home=True):
        self.active, self.event_type, self.go_home = active, event_type, go_home
        self.now = 0
        self.sent = []
        self.closed = False

    def refresh_status(self):
        pass

    def current_app(self):
        return self.active

    def matches_app(self):
        return self.active == APP

    def send(self, data):
        self.sent.append(data)

    def receive(self, timeout):
        self.now += timeout
        if not self.sent:
            return None
        data = self.sent[-1]
        if self.go_home:
            self.active = game_cast.APP_BACKDROP
        return {
            "type": self.event_type,
            "session_id": data["session_id"],
            "request_id": data["request_id"],
        }

    def close(self):
        self.closed = True


def stop_cast(fake):
    return game_cast.stop_game_display(
        "192.0.2.5",
        APP,
        SID,
        TOKEN,
        transport_factory=lambda *args: fake,
        clock=lambda: fake.now,
        timeout_s=0.5,
    )


def test_stop_sends_only_session_end_and_requires_backdrop():
    fake = StopTransport()
    result = stop_cast(fake)
    assert result["closed"] and result["evidence"] == "receiver_backdrop"
    assert fake.sent[0]["type"] == "END_SESSION"
    assert set(fake.sent[0]) == {"type", "session_id", "request_id", "display_token"}
    assert TOKEN not in str(result) and fake.closed
    # Already home is safe, with no launch or stop message.
    repeated = StopTransport(active=game_cast.APP_BACKDROP)
    assert stop_cast(repeated)["closed"] and not repeated.sent


@pytest.mark.parametrize("other", ["233637DE", "CC1AD845", "OTHERAPP"])
def test_stop_leaves_other_apps_alone(other):
    fake = StopTransport(active=other)
    assert stop_cast(fake)["reason"] == "other_playback_untouched"
    assert not fake.sent and fake.closed


def test_stop_newer_game_or_missing_close_ack_is_honest():
    newer = StopTransport(event_type="SESSION_NOT_CURRENT", go_home=False)
    assert stop_cast(newer)["reason"] == "newer_game_untouched"
    # A matching ending acknowledgement alone does not prove the receiver closed.
    pending = StopTransport(go_home=False)
    assert stop_cast(pending)["reason"] == "receiver_close_unverified"
    assert len(pending.sent) == 1
