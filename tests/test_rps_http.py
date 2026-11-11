"""Loopback-only HTTP checks: capabilities, privacy headers and input bounds."""

import threading
from urllib.parse import urlsplit

import httpx
import pytest

from games.service import GameServer

KEY = "test-admin-token-" * 3


@pytest.fixture
def server():
    srv = GameServer(("127.0.0.1", 0), {"admin_token": KEY, "public_url": "https://games.test"})
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    with httpx.Client(
        base_url=f"http://127.0.0.1:{srv.server_port}", trust_env=False, timeout=3
    ) as client:
        yield client
    srv.shutdown()
    srv.server_close()
    thread.join(timeout=2)


def create(server):
    return server.post(
        "/v1/sessions",
        headers={"Authorization": "Bearer " + KEY},
        json={"request_key": "request-key-123456"},
    ).json()


def test_pair_once_viewer_sees_same_state_but_cannot_start(server):
    c = create(server)
    pair = urlsplit(c["pairing_url"]).fragment[5:]
    p = server.post("/v1/pair", json={"pair_token": pair}).json()
    assert p["ok"] and p["state"]["phase"] == "ready"
    assert server.post("/v1/pair", json={"pair_token": pair}).status_code == 410
    path = "/v1/sessions/" + c["session_id"]
    viewer = urlsplit(c["display_url"]).fragment.split("token=")[1]
    h = {"Authorization": "Bearer " + viewer}
    snapshot = server.get(path, headers=h)
    assert snapshot.json()["state"]["round_id"] == p["state"]["round_id"]
    assert "hermes_move" not in snapshot.text and "nonce" not in snapshot.text
    assert (
        server.post(
            path + "/next", headers=h, json={"round_id": p["state"]["round_id"]}
        ).status_code
        == 401
    )
    h = {"Authorization": "Bearer " + p["player_token"]}
    assert (
        server.post(path + "/next", headers=h, json={"round_id": p["state"]["round_id"]}).json()[
            "state"
        ]["phase"]
        == "countdown"
    )


def test_admin_auth_and_origin_gate(server):
    assert (
        server.post("/v1/sessions", json={"request_key": "request-key-123456"}).status_code == 401
    )
    assert (
        server.post(
            "/v1/pair", headers={"Origin": "https://evil.test"}, json={"pair_token": "x"}
        ).status_code
        == 403
    )


def test_privacy_headers_static_and_path_bounds(server):
    r = server.get("/display/")
    assert r.status_code == 200 and "Terebi Games" in r.text
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "connect-src 'self'" in r.headers["content-security-policy"]
    assert "microphone=()" in r.headers["permissions-policy"]
    assert "no-store" in r.headers["cache-control"]
    assert server.get("/display/%2e%2e/service.py").status_code == 404
    assert server.get("/display/?token=do-not-log").status_code == 400
    assert server.get("/config.json").status_code == 404


def test_image_payloads_and_invalid_json_rejected(server):
    assert (
        server.post(
            "/v1/pair", content=b"x" * 3000, headers={"Content-Type": "application/json"}
        ).status_code
        == 413
    )
    assert (
        server.post(
            "/v1/pair", content=b"{", headers={"Content-Type": "application/json"}
        ).status_code
        == 400
    )
    assert server.post("/v1/pair", json={"pair_token": "x", "image": "private"}).status_code == 400


def test_receiver_is_static_reuses_display_and_has_scoped_sdk_policy(server):
    receiver = server.get("/receiver/")
    assert receiver.status_code == 200
    assert "/display/style.css" in receiver.text and "cast_receiver_framework.js" in receiver.text
    assert "www.gstatic.com" in receiver.headers["Content-Security-Policy"]
    assert "www.gstatic.com" not in server.get("/play/").headers["Content-Security-Policy"]
    assert server.get("/receiver/receiver.js").status_code == 200
    assert server.get("/receiver/%2e%2e/service.py").status_code == 404
    assert server.get("/receiver/?token=forbidden").status_code == 400


def test_cast_and_manual_display_share_one_tv_renderer(server):
    display, receiver = server.get("/display/"), server.get("/receiver/")
    for page in (display, receiver):
        # The receiver policy is style-src 'self': the scene may not rely on inline styles.
        assert 'id="tv"' in page.text and "style=" not in page.text
    assert "/display/display.js" in server.get("/receiver/receiver.js").text
    for module in ("display.js", "scene.js", "view.js", "hands.js", "style.css"):
        assert server.get(f"/display/{module}").status_code == 200
    scene = server.get("/display/scene.js").text
    assert "style=" not in scene and "http" not in scene.replace("http://www.w3.org", "")


def test_tv_background_music_serves_from_display_origin(server):
    with server.stream("GET", "/display/hydrate.mp3") as r:
        assert r.status_code == 200
        assert r.headers["content-type"] == "audio/mpeg"
        assert int(r.headers["content-length"]) > 1_000_000
        assert "no-store" in r.headers["cache-control"]
    assert server.get("/display/hydrate.mp4").status_code == 404
    assert server.get("/display/%2e%2e/hydrate.mp3").status_code == 404


def test_display_can_report_render_timings_but_nothing_else(server):
    c = create(server)
    path = "/v1/sessions/" + c["session_id"]
    viewer = {"Authorization": "Bearer " + urlsplit(c["display_url"]).fragment.split("token=")[1]}
    before = server.get(path, headers=viewer).json()["state"]
    good = {
        "mode": "3d",
        "tier": "lite",
        "turn": "css",
        "ambient": [90, 33, 120, 4],
        "reveal": [60, 40, 180, 9],
        "hand": [24, 41, 96],
        "screen": [1280, 720, 100],
    }
    assert server.post(path + "/profile", headers=viewer, json=good).json() == {"ok": True}
    after = server.get(path, headers=viewer).json()["state"]
    assert after["revision"] == before["revision"] and after["phase"] == before["phase"]
    assert server.post(path + "/profile", json=good).status_code == 401
    for bad in (
        {**good, "note": "free text"},
        {**good, "mode": "<script>"},
        {**good, "ambient": [1, 2, 3]},
        {**good, "hand": [1, 2, 99999]},
        {**good, "screen": [1280, 720, True]},
        {k: v for k, v in good.items() if k != "tier"},
    ):
        assert server.post(path + "/profile", headers=viewer, json=bad).status_code == 400
    for _ in range(31):
        assert server.post(path + "/profile", headers=viewer, json=good).status_code == 200
    assert server.post(path + "/profile", headers=viewer, json=good).status_code == 429


def test_baked_hands_are_served_to_both_tv_pages(server):
    hands = server.get("/display/hands.json")
    assert hands.status_code == 200 and set(hands.json()["moves"]) == {"rock", "paper", "scissors"}
    assert "/display/hands.json" in server.get("/display/scene.js").text


def test_end_is_admin_only_owner_scoped_and_invalidates_links(server):
    created = create(server)
    sid = created["session_id"]
    viewer = urlsplit(created["display_url"]).fragment.split("token=")[1]
    pair = urlsplit(created["pairing_url"]).fragment[5:]
    path = "/v1/sessions/" + sid
    for token in (viewer, "wrong-token"):
        assert (
            server.post(
                path + "/end",
                headers={"Authorization": "Bearer " + token},
                json={"request_key": "request-key-123456"},
            ).status_code
            == 401
        )
    headers = {"Authorization": "Bearer " + KEY}
    assert (
        server.post(
            path + "/end", headers=headers, json={"request_key": "different-owner-key"}
        ).status_code
        == 403
    )
    assert (
        server.post(
            path + "/end",
            headers=headers,
            json={"request_key": "request-key-123456", "extra": True},
        ).status_code
        == 400
    )
    body = {"request_key": "request-key-123456"}
    assert server.post(path + "/end", headers=headers, json=body).json()["ended"]
    assert server.post(path + "/end", headers=headers, json=body).json()["already_ended"]
    assert server.get(path, headers={"Authorization": "Bearer " + viewer}).status_code == 410
    assert server.post("/v1/pair", json={"pair_token": pair}).status_code == 410
    fresh = create(server)
    assert fresh["session_id"] != sid
    assert server.post(path + "/end", headers=headers, json=body).json()["already_ended"]
    assert (
        server.post(
            "/v1/pair", json={"pair_token": urlsplit(fresh["pairing_url"]).fragment[5:]}
        ).json()["state"]["phase"]
        == "ready"
    )
