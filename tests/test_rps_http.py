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
