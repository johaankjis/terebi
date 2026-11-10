"""End to end: register() -> tv_play/tv_pause handlers -> real JellyfinClient (respx)
-> real relay on 127.0.0.1 -> scripted fake Chromecast. No LAN or hardware."""

from __future__ import annotations

import http.client
import importlib.util
import json
import socket
import sys
from pathlib import Path

import httpx
import pytest
from cast_fixtures import BBB_ID, OTHER_ID, cast_item
from fake_cast import FakeClock, FakeReceiver

ROOT = Path(__file__).resolve().parents[1]
JF = "http://jellyfin.test:8096"
UID = "a" * 32
KEY = "tv-secret-key-0123456789"
ADVERTISED = "http://192.0.2.10:8765"
STREAM_BODY = bytes(range(256)) * 64


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Ctx:
    def __init__(self, port: int, **settings) -> None:
        self.settings = {
            "jellyfin_url": JF,
            "jellyfin_user": UID,
            "chromecast_host": "192.0.2.50",
            "cast_media_base_url": ADVERTISED,
            "cast_relay_bind": f"127.0.0.1:{port}",
            **settings,
        }
        self.tools: dict[str, dict] = {}
        self.unload: list = []

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_tool(self, **kwargs):
        self.tools[kwargs["name"]] = kwargs

    def on_unload(self, callback):
        self.unload.append(callback)

    def call(self, name, args):
        return json.loads(self.tools[name]["handler"](args))


@pytest.fixture
def plugin(monkeypatch):
    name = "screen_tv_plugin"
    spec = importlib.util.spec_from_file_location(name, ROOT / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    module.register(Ctx(free_port()))  # import submodules
    yield module
    for key in list(sys.modules):
        if key == name or key.startswith(name + "."):
            del sys.modules[key]


@pytest.fixture
def secret(plugin, monkeypatch):
    config = sys.modules[plugin.__name__ + ".hermes_screen.config"]
    key = [KEY]
    monkeypatch.setattr(config, "_default_secret_reader", lambda _: key[0])
    return key


@pytest.fixture
def receiver(plugin, monkeypatch):
    cast_mod = sys.modules[plugin.__name__ + ".hermes_screen.cast"]
    playback = sys.modules[plugin.__name__ + ".hermes_screen.playback"]
    fake = FakeReceiver(FakeClock(), cast_module=cast_mod)
    monkeypatch.setattr(playback, "connect_chromecast", fake.connect)
    # register() builds the manager with the real clock: keep unverified paths short.
    for name, value in [
        ("PLAY_TIMEOUT_S", 0.5),
        ("PAUSE_TIMEOUT_S", 0.5),
        ("STATUS_TIMEOUT_S", 0.5),
    ]:
        monkeypatch.setattr(playback, name, value)
    monkeypatch.setattr(playback, "POLL_S", 0.05)
    return fake


@pytest.fixture
def ctx(plugin, secret, receiver):
    c = Ctx(free_port())
    plugin.register(c)
    yield c
    for callback in c.unload:
        callback()


def jellyfin(router, item=None, item_id=BBB_ID):
    router.get(f"{JF}/Users/{UID}").respond(json={"Id": UID, "Name": "homelab"})
    router.get(f"{JF}/Items/{item_id}").respond(json=item or cast_item(item_id))

    def stream(request: httpx.Request) -> httpx.Response:
        rng = request.headers.get("Range")
        if rng == "bytes=0-":
            return httpx.Response(
                206,
                headers={"Content-Range": f"bytes 0-{len(STREAM_BODY) - 1}/{len(STREAM_BODY)}"},
                content=STREAM_BODY,
            )
        return httpx.Response(200, content=STREAM_BODY)

    return router.get(f"{JF}/Videos/{item_id}/stream").mock(side_effect=stream)


def fetch(ctx, url, headers=None):
    port = int(ctx.settings["cast_relay_bind"].rsplit(":", 1)[1])
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", url.removeprefix(ADVERTISED), headers=headers or {})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp, body


def assert_clean(result, receiver=None):
    text = json.dumps(result)
    assert KEY not in text and "/cast/" not in text and "jellyfin.test" not in text
    if receiver is not None and receiver.content_id:
        assert receiver.content_id not in text


def test_registers_four_tools_and_unload_hook(plugin):
    c = Ctx(free_port())
    plugin.register(c)
    assert list(c.tools) == [
        "library_status",
        "library_pick",
        "tv_play",
        "tv_pause",
        "library_scene_find",
        "library_scene_save",
        "tv_scene_play",
    ]
    assert len(c.unload) == 1
    assert c.tools["tv_play"]["schema"]["parameters"]["required"] == ["item_id"]
    assert c.tools["tv_pause"]["schema"]["parameters"]["properties"] == {}


def test_play_stream_pause_unload(ctx, receiver, respx_mock):
    stream = jellyfin(respx_mock)
    result = ctx.call("tv_play", {"item_id": BBB_ID})
    assert result["ok"] is True and result["verified"] is True and result["state"] == "playing"
    assert result["item"] == {
        "item_id": BBB_ID,
        "title": "BigBuckBunny_320x180",
        "media_source_id": BBB_ID,
    }
    assert_clean(result, receiver)

    # The receiver got only a capability URL on the advertised base: no key, no Jellyfin host.
    url = receiver.content_id
    assert url.startswith(ADVERTISED + "/cast/") and url.endswith("/video.mp4")
    assert KEY not in url and "jellyfin" not in url and BBB_ID not in url
    item_request = next(c.request for c in respx_mock.calls if "/Items/" in str(c.request.url))
    assert dict(item_request.url.params) == {"userId": UID}

    # The receiver can fetch it (range from the start), the key stays upstream.
    resp, body = fetch(ctx, url, {"Range": "bytes=0-"})
    assert resp.status == 206 and body == STREAM_BODY
    upstream = stream.calls[-1].request
    assert upstream.url.path == f"/Videos/{BBB_ID}/stream"
    assert dict(upstream.url.params) == {"static": "true", "mediaSourceId": BBB_ID}
    assert f'Token="{KEY}"' in upstream.headers["Authorization"]
    assert all(KEY not in v for _, v in resp.getheaders())

    paused = ctx.call("tv_pause", {})
    assert (
        paused["ok"] is True and paused["state"] == "paused" and paused["already_paused"] is False
    )
    again = ctx.call("tv_pause", "{}")
    assert again["ok"] is True and again["already_paused"] is True
    assert len([c for c in receiver.commands if c[0] == "PAUSE"]) == 1

    for callback in ctx.unload:
        callback()
    resp_status = None
    try:
        resp_status = fetch(ctx, url)[0].status
    except OSError:
        pass
    assert resp_status in (None, 404)
    assert ctx.call("tv_pause", {})["reason"] == "not_configured"


def test_repeat_play_same_item_does_not_reload(ctx, receiver, respx_mock):
    jellyfin(respx_mock)
    assert ctx.call("tv_play", {"item_id": BBB_ID})["action"] == "started"
    assert ctx.call("tv_play", {"item_id": BBB_ID})["action"] == "already_playing"
    assert len([c for c in receiver.commands if c[0] == "LOAD"]) == 1


@pytest.mark.parametrize(
    "args",
    [
        {"item_id": "BigBuckBunny_320x180"},
        {"item_id": "Big Buck Bunny"},
        {"item_id": BBB_ID[:-1]},
        {"item_id": BBB_ID + "0"},
        {"item_id": 123},
        {"item_id": None},
        {},
        {"item_id": BBB_ID, "device": "den"},
        {"title": "Big Buck Bunny"},
        "not json",
        ["x"],
    ],
)
def test_invalid_play_args_touch_nothing(ctx, receiver, respx_mock, args):
    result = ctx.call("tv_play", args)
    assert result["ok"] is False and result["reason"] == "invalid_argument"
    assert set(result) == {"ok", "reason", "hint"}
    assert not respx_mock.calls and receiver.commands == []


@pytest.mark.parametrize("args", [{"item_id": BBB_ID}, {"force": True}, "[1]", "nope"])
def test_invalid_pause_args(ctx, receiver, args):
    assert ctx.call("tv_pause", args)["reason"] == "invalid_argument"
    assert receiver.commands == []


def test_pause_none_args_is_empty(ctx, receiver):
    assert ctx.call("tv_pause", None)["reason"] == "nothing_playing"


@pytest.mark.parametrize(
    ("missing", "named"),
    [
        ("chromecast_host", "chromecast_host"),
        ("cast_media_base_url", "cast_media_base_url"),
        ("cast_relay_bind", "cast_relay_bind"),
    ],
)
def test_missing_cast_settings(plugin, secret, receiver, respx_mock, missing, named):
    c = Ctx(free_port(), **{missing: ""})
    plugin.register(c)
    result = c.call("tv_play", {"item_id": BBB_ID})
    assert result["reason"] == "not_configured" and named in result["hint"]
    assert not respx_mock.calls and receiver.commands == []


@pytest.mark.parametrize("value", [5, ["192.0.2.50"], True])
def test_wrong_cast_setting_types(plugin, secret, receiver, value):
    c = Ctx(free_port(), chromecast_host=value)
    plugin.register(c)
    result = c.call("tv_play", {"item_id": BBB_ID})
    assert result["reason"] == "cast_config" and "192.0.2.50" not in json.dumps(result)


def test_missing_jellyfin_secret(plugin, secret, receiver, respx_mock):
    secret[0] = None
    c = Ctx(free_port())
    plugin.register(c)
    assert c.call("tv_play", {"item_id": BBB_ID})["reason"] == "not_configured"
    assert not respx_mock.calls and receiver.commands == []


def test_unsupported_media_is_rejected_before_casting(ctx, receiver, respx_mock):
    jellyfin(respx_mock, cast_item(source={"Container": "mkv", "Path": "/m/x.mkv"}))
    result = ctx.call("tv_play", {"item_id": BBB_ID})
    assert result["reason"] == "unsupported_media" and "transcoding" in result["hint"]
    assert receiver.commands == []


@pytest.mark.parametrize(("status", "reason"), [(401, "jellyfin_auth"), (404, "not_found")])
def test_jellyfin_errors_before_casting(ctx, receiver, respx_mock, status, reason):
    respx_mock.get(f"{JF}/Users/{UID}").respond(json={"Id": UID, "Name": "homelab"})
    respx_mock.get(f"{JF}/Items/{BBB_ID}").respond(status, text=f"oops {KEY}")
    result = ctx.call("tv_play", {"item_id": BBB_ID})
    assert result["reason"] == reason
    assert_clean(result)
    assert receiver.commands == []


def test_unverified_playback_is_not_success(ctx, receiver, respx_mock):
    jellyfin(respx_mock)
    receiver.on_load = "silent"
    result = ctx.call("tv_play", {"item_id": BBB_ID})
    assert result["ok"] is False and result["evidence"] == "app_opened"
    assert "playing" not in result.get("state", "")
    assert_clean(result)


def test_contexts_do_not_share_playback(plugin, secret, receiver, respx_mock):
    jellyfin(respx_mock)
    first, second = Ctx(free_port()), Ctx(free_port())
    plugin.register(first)
    plugin.register(second)
    try:
        assert first.call("tv_play", {"item_id": BBB_ID})["ok"] is True
        assert second.call("tv_pause", {})["reason"] == "nothing_playing"
        assert first.call("tv_pause", {})["ok"] is True
    finally:
        for callback in first.unload + second.unload:
            callback()


def test_secret_is_read_per_call(ctx, secret, receiver, respx_mock):
    stream = jellyfin(respx_mock)
    ctx.call("tv_play", {"item_id": BBB_ID})
    secret[0] = "rotated-key-999"
    jellyfin(respx_mock, item_id=OTHER_ID)
    ctx.call("tv_play", {"item_id": OTHER_ID})
    fetch(ctx, receiver.content_id)
    auth = [c.request.headers["Authorization"] for c in respx_mock.calls]
    assert 'Token="rotated-key-999"' in auth[-1]
    assert not stream.called  # first item's capability was revoked before any fetch


def test_cast_crash_is_generic(ctx, receiver, respx_mock, plugin, monkeypatch):
    jellyfin(respx_mock)
    playback = sys.modules[plugin.__name__ + ".hermes_screen.playback"]

    def boom(host, port):
        raise RuntimeError(f"PRIVATE {KEY}")

    monkeypatch.setattr(playback, "connect_chromecast", boom)
    result = ctx.call("tv_play", {"item_id": BBB_ID})
    assert result["reason"] == "cast_failed" and "PRIVATE" not in json.dumps(result)


def test_close_cast_relay_is_exposed(ctx, receiver, respx_mock):
    jellyfin(respx_mock)
    ctx.call("tv_play", {"item_id": BBB_ID})
    url = receiver.content_id
    ctx.tools["tv_pause"]["handler"].close_cast_relay()
    assert ctx.call("tv_pause", {})["reason"] == "nothing_playing"
    try:
        assert fetch(ctx, url)[0].status == 404
    except OSError:
        pass  # listener already stopped
    assert ctx.call("tv_play", {"item_id": BBB_ID})["ok"] is True  # still usable
