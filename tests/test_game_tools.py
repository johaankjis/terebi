"""Native Hermes game entry with mocked standalone service; no hardware."""

import importlib
import json

import httpx
from test_plugin import FakeCtx
from test_plugin import plugin as plugin


def call(plugin, ctx, identity="session-one", args=None):
    module = importlib.import_module(plugin.__name__ + ".game_tools")
    return json.loads(
        module.start_rps(
            {} if args is None else args,
            ctx=ctx,
            identity=identity,
            secret_reader=lambda _: "private-game-key",
        )
    )


def result():
    return {
        "ok": True,
        "session_id": "game-session-123456789",
        "pairing_url": "https://games.test/play/#pair=random",
        "display_url": "https://games.test/display/#session=game-session-123456789&token=read-only-viewer-token-123456789",
        "pairing_expires_at_ms": 1234,
        "state": {"expires_at_ms": 4567, "phase": "waiting_for_player"},
    }


def test_game_entry_links_and_context_idempotence(plugin, respx_mock):
    ctx = FakeCtx(games_service_url="http://games.test:8766")
    route = respx_mock.post("http://games.test:8766/v1/sessions").respond(json=result())
    first = call(plugin, ctx)
    again = call(plugin, ctx)
    assert first == again and first["ok"] and not first["tv_verified"]
    assert first["display_path"] == "manual_chrome_mirroring"
    assert route.calls[0].request.content == route.calls[1].request.content
    call(plugin, ctx, identity="different-session")
    assert route.calls[0].request.content != route.calls[2].request.content
    assert "private-game-key" not in json.dumps(first)
    assert route.calls[0].request.headers["Authorization"] == "Bearer private-game-key"


def test_game_entry_no_identity_or_config_does_not_call_service(plugin, respx_mock):
    assert call(plugin, FakeCtx(), identity=None)["reason"] == "game_context_missing"
    assert call(plugin, FakeCtx())["reason"] == "not_configured"
    assert call(plugin, FakeCtx(), args={"game": "trivia"})["reason"] == "invalid_argument"
    assert not respx_mock.calls


def test_game_service_error_hides_secret(plugin, respx_mock):
    ctx = FakeCtx(games_service_url="http://games.test:8766")
    route = respx_mock.post("http://games.test:8766/v1/sessions")
    route.mock(side_effect=httpx.ConnectError("private-game-key"))
    assert "private-game-key" not in json.dumps(call(plugin, ctx))
    route.respond(401)
    assert call(plugin, ctx)["reason"] == "games_auth"
    route.respond(302, headers={"Location": "https://evil.test"})
    assert call(plugin, ctx)["reason"] == "games_unavailable"


def test_game_launch_receives_only_viewer_capability_and_keeps_phone_link(plugin, respx_mock):
    module = importlib.import_module(plugin.__name__ + ".game_tools")
    ctx = FakeCtx(
        games_service_url="https://games.test",
        chromecast_host="192.0.2.5",
        games_receiver_app_id="AB12CD34",
    )
    respx_mock.post("https://games.test/v1/sessions").respond(json=result())
    calls = []

    def launcher(*args):
        calls.append(args)
        return {
            "ok": True,
            "phase": "waiting_for_player",
            "evidence": "receiver_rendered_session",
            "session_id": result()["session_id"],
        }

    data = json.loads(
        module.start_rps(
            {},
            ctx=ctx,
            identity="telegram-user",
            secret_reader=lambda _: "admin-secret",
            cast_launcher=launcher,
        )
    )
    assert data["tv_verified"] and data["display_path"] == "custom_cast_receiver"
    assert data["pairing_url"] == result()["pairing_url"]
    assert data["display_url"] == result()["display_url"]
    assert calls == [
        ("192.0.2.5", "AB12CD34", result()["session_id"], "read-only-viewer-token-123456789")
    ]
    assert "admin-secret" not in str(calls) and "pair=" not in str(calls)
    assert not data["wake_verified"] and not data["input_verified"]


def test_launch_failure_preserves_game_and_manual_fallback(plugin, respx_mock):
    module = importlib.import_module(plugin.__name__ + ".game_tools")
    ctx = FakeCtx(
        games_service_url="https://games.test",
        chromecast_host="192.0.2.5",
        games_receiver_app_id="AB12CD34",
    )
    respx_mock.post("https://games.test/v1/sessions").respond(json=result())
    data = json.loads(
        module.start_rps(
            {},
            ctx=ctx,
            identity="telegram-user",
            secret_reader=lambda _: "admin-secret",
            cast_launcher=lambda *args: {
                "ok": False,
                "reason": "receiver_render_unverified",
                "hint": "Use manual display",
            },
        )
    )
    assert data["ok"] and not data["tv_verified"]
    assert data["tv"]["reason"] == "receiver_render_unverified"
    assert data["display_path"] == "manual_chrome_mirroring"
    assert data["display_url"] == result()["display_url"]


def test_launch_only_success_does_not_claim_tv_readiness(plugin, respx_mock):
    module = importlib.import_module(plugin.__name__ + ".game_tools")
    ctx = FakeCtx(
        games_service_url="https://games.test",
        chromecast_host="192.0.2.5",
        games_receiver_app_id="AB12CD34",
    )
    respx_mock.post("https://games.test/v1/sessions").respond(json=result())
    data = json.loads(
        module.start_rps(
            {},
            ctx=ctx,
            identity="telegram-user",
            secret_reader=lambda _: "admin-secret",
            cast_launcher=lambda *args: {"ok": True, "app_opened": True},
        )
    )
    assert data["ok"] and not data["tv_verified"]
    assert data["tv"]["reason"] == "receiver_render_unverified"
    assert data["display_url"] == result()["display_url"]
