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
        "session_id": "test",
        "pairing_url": "https://games.test/play/#pair=random",
        "display_url": "https://games.test/display/#token=random",
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
