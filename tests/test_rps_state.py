"""Server-owned rounds: replay, race, retry, expiry and hidden-move guarantees."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import pytest

from games.state import GameError, GameStore


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def game():
    clock = Clock()
    store = GameStore(clock=clock, epoch_ms=1700000000000, choose=lambda _: "rock")
    created = store.create("request-key-123456", "https://games.test")
    paired = store.pair(urlsplit(created["pairing_url"]).fragment.removeprefix("pair="))
    return store, clock, created, paired


def begin(game):
    store, clock, created, paired = game
    sid, token = created["session_id"], paired["player_token"]
    rid = paired["state"]["round_id"]
    result = store.act(sid, token, "next", {"round_id": rid})
    return sid, token, rid, result["state"]


@pytest.mark.parametrize("hermes", ["rock", "paper", "scissors"])
@pytest.mark.parametrize("player", ["rock", "paper", "scissors"])
def test_all_results_are_scored_once(hermes, player):
    clock = Clock()
    store = GameStore(clock=clock, choose=lambda _: hermes)
    c = store.create("request-key-123456", "https://games.test")
    p = store.pair(urlsplit(c["pairing_url"]).fragment[5:])
    sid, token, rid = c["session_id"], p["player_token"], p["state"]["round_id"]
    store.act(sid, token, "next", {"round_id": rid})
    clock.now = 3.45
    state = store.act(sid, token, "move", {"round_id": rid, "move": player})["state"]
    expected = (
        "tie"
        if player == hermes
        else "player"
        if (player, hermes) in {("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")}
        else "hermes"
    )
    assert state["result"]["outcome"] == expected
    assert state["score"]["rounds"] == 1
    assert state["score"]["ties" if expected == "tie" else expected] == 1
    with pytest.raises(GameError) as exc:
        store.act(sid, token, "move", {"round_id": rid, "move": player})
    assert exc.value.reason == "already_scored"
    assert store.state(sid, token)["state"]["score"] == state["score"]


def test_hidden_commitment_before_submission_and_revealed_proof(game):
    store, clock, _, paired = game
    sid, token, rid, countdown = begin(game)
    assert countdown["result"] is None
    assert "move" not in countdown and "nonce" not in countdown
    assert paired["state"]["hermes_commitment"] == countdown["hermes_commitment"]
    clock.now = 3.5
    reveal = store.act(sid, token, "move", {"round_id": rid, "move": "paper"})["state"]
    proof = f"{sid}:1:rock:{reveal['result']['nonce']}"
    assert hashlib.sha256(proof.encode()).hexdigest() == countdown["hermes_commitment"]


def test_missed_hand_retry_keeps_move_and_score_rejects_old_attempt(game):
    store, clock, _, _ = game
    sid, token, rid, initial = begin(game)
    clock.now = 4
    retry = store.act(sid, token, "retry", {"round_id": rid})["state"]
    assert retry["score"]["rounds"] == 0 and retry["round_number"] == 1
    assert retry["hermes_commitment"] == initial["hermes_commitment"]
    assert retry["round_id"] != rid
    clock.now = 8
    with pytest.raises(GameError, match="stale_round"):
        store.act(sid, token, "move", {"round_id": rid, "move": "rock"})
    assert (
        store.act(sid, token, "move", {"round_id": retry["round_id"], "move": "rock"})["state"][
            "score"
        ]["rounds"]
        == 1
    )


def test_simultaneous_camera_and_tap_only_score_once(game):
    store, clock, _, _ = game
    sid, token, rid, _ = begin(game)
    clock.now = 4

    def submit(action):
        try:
            return store.act(sid, token, action, {"round_id": rid, "move": "paper"})
        except GameError as exc:
            return exc.result()

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(submit, ["move", "tap"] * 6))
    assert sum(r["ok"] for r in results) == 1
    assert store.state(sid, token)["state"]["score"] == {
        "player": 1,
        "hermes": 0,
        "ties": 0,
        "rounds": 1,
    }


def test_server_phases_and_next_round_are_shared_and_not_replayed(game):
    store, clock, c, _ = game
    sid, token, rid, _ = begin(game)
    clock.now = 4
    state = store.act(sid, token, "tap", {"round_id": rid, "move": "scissors"})["state"]
    assert state["phase"] == "reveal" and state["result"]["input"] == "tap"
    clock.now = 5.5
    assert store.state(sid, token)["state"]["phase"] == "score"
    clock.now = 7
    assert store.state(sid, token)["state"]["phase"] == "next_round"
    next_state = store.act(sid, token, "next", {"round_id": rid})["state"]
    assert next_state["phase"] == "countdown" and next_state["round_number"] == 2
    viewer = urlsplit(c["display_url"]).fragment.split("token=")[1]
    assert store.state(sid, viewer)["state"] == next_state
    with pytest.raises(GameError, match="stale_round"):
        store.act(sid, token, "next", {"round_id": rid})


@pytest.mark.parametrize("at", [0, 2.99, 13.01, 100])
def test_early_or_late_moves_cannot_score(game, at):
    store, clock, _, _ = game
    sid, token, rid, _ = begin(game)
    clock.now = at
    with pytest.raises(GameError, match="outside_window"):
        store.act(sid, token, "move", {"round_id": rid, "move": "paper"})
    assert store.state(sid, token)["state"]["score"]["rounds"] == 0


def test_pairing_is_single_use_and_creation_idempotent(game):
    store, _, created, _ = game
    with pytest.raises(GameError, match="pair_expired"):
        store.pair(urlsplit(created["pairing_url"]).fragment[5:])
    again = store.create("request-key-123456", "https://games.test")
    assert again["session_id"] == created["session_id"] and again["pairing_url"] is None


def test_pair_link_and_session_expire():
    clock = Clock()
    store = GameStore(clock=clock)
    c = store.create("request-key-123456", "https://games.test")
    clock.now = 181
    with pytest.raises(GameError, match="pair_expired"):
        store.pair(urlsplit(c["pairing_url"]).fragment[5:])
    fresh = store.create("request-key-123456", "https://games.test")
    assert fresh["pairing_url"] != c["pairing_url"]
    p = store.pair(urlsplit(fresh["pairing_url"]).fragment[5:])
    clock.now = 1801
    with pytest.raises(GameError, match="session_expired"):
        store.state(c["session_id"], p["player_token"])


def test_viewer_and_other_player_cannot_control_session(game):
    store, _, c, _ = game
    sid, _, rid, _ = begin(game)
    viewer = urlsplit(c["display_url"]).fragment.split("token=")[1]
    for token in [viewer, "wrong-player"]:
        with pytest.raises(GameError, match="unauthorized"):
            store.act(sid, token, "retry", {"round_id": rid})


@pytest.mark.parametrize("extra", [{"score": 999}, {"image": "base64"}, {"confidence": 0.99}])
def test_client_cannot_send_score_images_or_extra_data(game, extra):
    store, clock, _, _ = game
    sid, token, rid, _ = begin(game)
    clock.now = 4
    with pytest.raises(GameError, match="invalid_request"):
        store.act(sid, token, "move", {"round_id": rid, "move": "rock", **extra})


def test_capacity_is_bounded():
    store = GameStore(capacity=1)
    store.create("request-key-123456", "https://games.test")
    with pytest.raises(GameError, match="capacity"):
        store.create("different-key-12345", "https://games.test")


def test_three_round_protocol_and_audit_have_exactly_three_scores():
    clock = Clock()
    events = []
    store = GameStore(clock=clock, audit=events.append, choose=lambda _: "paper")
    c = store.create("request-key-123456", "https://games.test")
    p = store.pair(urlsplit(c["pairing_url"]).fragment[5:])
    sid, token, state = c["session_id"], p["player_token"], p["state"]
    for index, move in enumerate(["rock", "paper", "scissors"], 1):
        rid = state["round_id"]
        state = store.act(sid, token, "next", {"round_id": rid})["state"]
        rid = state["round_id"]
        clock.now += 4
        if index == 2:
            original = state["hermes_commitment"]
            state = store.act(sid, token, "retry", {"round_id": rid})["state"]
            assert state["score"]["rounds"] == 1
            assert state["hermes_commitment"] == original
            rid = state["round_id"]
            clock.now += 4
        state = store.act(sid, token, "move", {"round_id": rid, "move": move})["state"]
        assert state["score"]["rounds"] == index
        clock.now += 4
        state = store.state(sid, token)["state"]
    scores = [e for e in events if e["event"] == "round_scored"]
    assert len(scores) == 3 and all(e["result"]["input"] == "camera" for e in scores)
    import json

    audit = json.dumps(events)
    assert token not in audit and c["display_url"] not in audit


@pytest.mark.parametrize("token", ["£bad", "❌", None])
def test_non_ascii_or_missing_bearer_is_rejected_cleanly(game, token):
    store, _, c, _ = game
    with pytest.raises(GameError, match="unauthorized"):
        store.state(c["session_id"], token)
