"""Exercise the native entry point through real YAML and mocked HTTP."""

import builtins
import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
UID = "a" * 32


class FakeCtx:
    def __init__(self, url="http://jellyfin.test:8096", **settings):
        self.settings = {"jellyfin_url": url, **settings}
        self.registered = []

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_tool(self, **kwargs):
        self.registered.append(kwargs)


@pytest.fixture
def plugin():
    name = "screen_test_plugin"
    spec = importlib.util.spec_from_file_location(name, ROOT / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    module.register(FakeCtx())
    yield module
    for key in list(sys.modules):
        if key == name or key.startswith(name + "."):
            del sys.modules[key]


def status_routes(router, url="http://jellyfin.test:8096", name="Alice"):
    router.get(url + "/System/Info/Public").respond(
        200, json={"ServerName": "Demo", "Version": "12.4.0"}
    )
    router.get(url + "/Users").respond(200, json=[{"Id": UID, "Name": name}])
    router.get(url + "/Items/Counts").respond(200, json={"MovieCount": 3})


def call(plugin, ctx=None, reader=lambda _: "test-key"):
    return json.loads(plugin.tools.library_status({}, ctx=ctx, secret_reader=reader))


def test_manifest_and_registration(plugin):
    manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text())
    ctx = FakeCtx()
    plugin.register(ctx)
    assert [t["name"] for t in ctx.registered] == manifest["provides_tools"] == ["library_status"]
    assert manifest["provides_hooks"] == []


def test_real_handler_client_http(plugin, respx_mock):
    status_routes(respx_mock)
    result = call(plugin, FakeCtx(jellyfin_user="Alice"))
    assert result == {
        "ok": True,
        "server": {"name": "Demo", "version": "12.4.0"},
        "user": {"id": UID, "name": "Alice"},
        "counts": {"movies": 3},
    }
    requests = [c.request for c in respx_mock.calls]
    assert "Authorization" not in requests[0].headers
    assert 'Token="test-key"' in requests[1].headers["Authorization"]
    assert all(r.extensions["timeout"]["read"] == 8 for r in requests)


def test_contexts_do_not_leak(plugin, respx_mock, monkeypatch):
    config = sys.modules[plugin.__name__ + ".hermes_screen.config"]
    key = ["first-key"]
    monkeypatch.setattr(config, "_default_secret_reader", lambda _: key[0])
    first, second = FakeCtx("http://first.test"), FakeCtx("http://second.test")
    plugin.register(first)
    plugin.register(second)
    status_routes(respx_mock, "http://first.test", "First")
    status_routes(respx_mock, "http://second.test", "Second")
    assert json.loads(first.registered[0]["handler"]({}))["user"]["name"] == "First"
    key[0] = "second-key"
    assert json.loads(second.registered[0]["handler"]({}))["user"]["name"] == "Second"
    key[0] = "new-first-key"
    assert json.loads(first.registered[0]["handler"]({}, ctx=second))["user"]["name"] == "First"
    auth = [c.request.headers.get("Authorization") for c in respx_mock.calls]
    assert 'Token="first-key"' in auth[1]
    assert 'Token="second-key"' in auth[4]
    assert 'Token="new-first-key"' in auth[7]
    assert call(plugin)["reason"] == "not_configured"


@pytest.mark.parametrize("field", ["jellyfin_url", "jellyfin_user", "secret"])
@pytest.mark.parametrize("value", [True, 3, [], {}, ["secret-value"]])
def test_wrong_setting_types_fail_safely(plugin, field, value):
    ctx = FakeCtx()

    def reader(_):
        return "test-key"

    if field == "secret":

        def reader(_):
            return value
    else:
        ctx.settings[field] = value
    result = call(plugin, ctx, reader)
    assert result["reason"] == "jellyfin_config"
    assert "secret-value" not in json.dumps(result)


@pytest.mark.parametrize("source", ["config", "secret", "import", "client"])
def test_failures_never_echo_exception(plugin, monkeypatch, source):
    ctx = FakeCtx()

    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE-KEY https://private:password@host")

    def reader(_):
        return "test-key"

    if source == "config":
        monkeypatch.setattr(ctx, "get_config", fail)
    elif source == "secret":
        reader = fail
    elif source == "import":
        original = builtins.__import__

        def importing(name, *args, **kwargs):
            if name == "hermes_screen.jellyfin":
                fail()
            return original(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", importing)
    else:
        module = __import__(
            plugin.__name__ + ".hermes_screen.jellyfin", fromlist=["JellyfinClient"]
        )
        monkeypatch.setattr(module.JellyfinClient, "status", fail)
    result = call(plugin, ctx, reader)
    assert result["ok"] is False
    assert set(result) == {"ok", "reason", "hint"}
    assert "PRIVATE-KEY" not in json.dumps(result)
    assert "password" not in json.dumps(result)


@pytest.mark.parametrize(
    "response,reason", [(401, "jellyfin_auth"), (503, "jellyfin_server_error")]
)
def test_http_error_is_structured(plugin, respx_mock, response, reason):
    respx_mock.get("http://jellyfin.test:8096/System/Info/Public").respond(
        response, text="PRIVATE-KEY"
    )
    result = call(plugin, FakeCtx())
    assert result["reason"] == reason
    assert "PRIVATE-KEY" not in json.dumps(result)


def test_constructor_validation_is_structured(plugin):
    result = call(plugin, FakeCtx("http://user:PRIVATE-KEY@host"))
    assert result["reason"] == "jellyfin_config"
    assert "PRIVATE-KEY" not in json.dumps(result)


def test_transport_failure_is_structured(plugin, respx_mock):
    respx_mock.get("http://jellyfin.test:8096/System/Info/Public").mock(
        side_effect=httpx.ConnectError("PRIVATE-KEY")
    )
    assert call(plugin, FakeCtx())["reason"] == "jellyfin_unreachable"


def test_missing_config(plugin):
    assert call(plugin, FakeCtx(""))["reason"] == "not_configured"
