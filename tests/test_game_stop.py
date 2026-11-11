"""Caller-scoped end tool: real handlers, mocked service/Cast, no hardware."""

import importlib
import json

import httpx
from test_game_tools import result
from test_plugin import FakeCtx
from test_plugin import plugin as plugin


def setup(plugin, router, *, ctx=None):
    module = importlib.import_module(plugin.__name__ + ".game_tools")
    ctx = ctx or FakeCtx(
        games_service_url="https://games.test",
        chromecast_host="192.0.2.5",
        games_receiver_app_id="AB12CD34",
    )
    created = router.post("https://games.test/v1/sessions").respond(json=result())
    started = json.loads(
        module.start_rps(
            {},
            ctx=ctx,
            identity="caller-one",
            secret_reader=lambda _: "private-admin-key",
            cast_launcher=lambda *a: {"ok": False},
        )
    )
    assert started["ok"]
    end = router.post("https://games.test/v1/sessions/" + result()["session_id"] + "/end").respond(
        json={
            "ok": True,
            "ended": True,
            "already_ended": False,
            "session_id": result()["session_id"],
        }
    )
    return module, ctx, created, end


def call(module, ctx, stopper, *, identity="caller-one", args=None):
    return json.loads(
        module.stop_rps(
            {} if args is None else args,
            ctx=ctx,
            identity=identity,
            secret_reader=lambda _: "private-admin-key",
            cast_stopper=stopper,
        )
    )


def test_stop_and_repeat_revoke_exact_caller_session_without_second_cast(plugin, respx_mock):
    module, ctx, created, end = setup(plugin, respx_mock)
    calls = []

    def stop(*args):
        calls.append(args)
        return {
            "ok": True,
            "closed": True,
            "evidence": "receiver_backdrop",
            "session_id": result()["session_id"],
        }

    stopped = call(module, ctx, stop)
    assert stopped["ok"] and stopped["game_ended"] and stopped["tv_verified"]
    assert calls == [
        ("192.0.2.5", "AB12CD34", result()["session_id"], "read-only-viewer-token-123456789")
    ]
    assert json.loads(created.calls[0].request.content) == json.loads(end.calls[0].request.content)
    assert end.calls[0].request.headers["Authorization"] == "Bearer private-admin-key"
    repeated = call(module, ctx, stop)
    assert repeated["already_ended"] and not repeated["tv_verified"]
    assert repeated["tv"]["reason"] == "not_touched"
    assert len(calls) == 1 and len(end.calls) == 1
    assert "private-admin-key" not in str(stopped)
    assert "read-only-viewer-token" not in str(stopped)


def test_other_caller_cannot_end_or_target_any_session(plugin, respx_mock):
    module, ctx, _, end = setup(plugin, respx_mock)

    def forbidden(*args):
        raise AssertionError("Must not touch Cast")

    assert call(module, ctx, forbidden, identity="another-caller")["outcome"] == "no_active_game"
    assert call(module, ctx, forbidden, identity=None)["reason"] == "game_context_missing"
    assert (
        call(module, ctx, forbidden, args={"session_id": result()["session_id"]})["reason"]
        == "invalid_argument"
    )
    assert not end.calls


def test_service_end_failure_does_not_send_receiver_stop(plugin, respx_mock):
    module, ctx, _, end = setup(plugin, respx_mock)
    calls = []
    end.respond(500)
    assert call(module, ctx, lambda *args: calls.append(args))["reason"] == "games_end_unverified"
    end.mock(side_effect=httpx.ReadTimeout("private-admin-key"))
    failed = call(module, ctx, lambda *args: calls.append(args))
    assert not failed["game_ended"] and "private-admin-key" not in str(failed) and not calls


def test_game_ended_but_unconfirmed_close_is_explicit_and_retryable(plugin, respx_mock):
    module, ctx, _, end = setup(plugin, respx_mock)
    failed = call(module, ctx, lambda *a: {"ok": False, "reason": "cast_unreachable"})
    assert failed["game_ended"] and not failed["tv_verified"] and not failed["ok"]
    assert failed["reason"] == "game_ended_tv_unverified"

    def close(*args):
        return {
            "ok": True,
            "closed": True,
            "evidence": "receiver_backdrop",
            "session_id": result()["session_id"],
        }

    assert call(module, ctx, close)["tv_verified"]
    assert len(end.calls) == 2


def test_unrelated_playback_and_newer_game_are_left_alone(plugin, respx_mock):
    for reason in ["other_playback_untouched", "newer_game_untouched"]:
        module, ctx, _, _ = setup(plugin, respx_mock)
        stopped = call(
            module, ctx, lambda *a, reason=reason: {"ok": True, "closed": False, "reason": reason}
        )
        assert stopped["ok"] and stopped["game_ended"] and not stopped["tv_verified"]
        assert stopped["tv"]["reason"] == reason


def test_active_record_survives_context_reload_in_profile_state(plugin, respx_mock):
    state = {}
    first = FakeCtx(
        games_service_url="https://games.test",
        chromecast_host="192.0.2.5",
        games_receiver_app_id="AB12CD34",
    )
    first.state = state
    module, _, _, _ = setup(plugin, respx_mock, ctx=first)
    second = FakeCtx(games_service_url="https://games.test")
    second.state = state
    stopped = call(
        module,
        second,
        lambda *a: {"ok": True, "closed": False, "reason": "other_playback_untouched"},
    )
    assert stopped["game_ended"]
