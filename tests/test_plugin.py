"""Tests for plugin registration and the library_status tool."""

import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tools  # noqa: E402
from hermes_screen import errors  # noqa: E402


class FakeState:
    def __init__(self):
        self._data = {}

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value


class FakeCtx:
    def __init__(self, config=None):
        self.config = dict(config or {})
        self.state = FakeState()
        self.registered_tools = []
        self.registered_hooks = []

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def set_config(self, key, value):
        self.config[key] = value

    def register_tool(self, **kwargs):
        self.registered_tools.append(kwargs)

    def register_hook(self, *args, **kwargs):
        self.registered_hooks.append((args, kwargs))


def _load_plugin_module():
    path = os.path.join(ROOT, "__init__.py")
    spec = importlib.util.spec_from_file_location("hermes_screen_plugin_init", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_register_registers_only_library_status():
    ctx = FakeCtx()
    tools.bind_context(None)
    tools.bind_client_factory(None)
    module = _load_plugin_module()
    module.register(ctx)
    names = [t["name"] for t in ctx.registered_tools]
    assert names == ["library_status"]
    assert names == module.PROVIDES_TOOLS


def test_library_status_config_missing():
    ctx = FakeCtx(config={})
    tools.bind_context(ctx)
    tools.bind_client_factory(None)
    result = json.loads(tools.library_status({}, ctx=ctx, secret_reader=lambda n: None))
    assert result["ok"] is False
    assert result["reason"] == "not_configured"


def test_library_status_client_unavailable():
    ctx = FakeCtx(config={"jellyfin_url": "http://example:8096"})
    tools.bind_context(ctx)
    tools.bind_client_factory(None)
    result = json.loads(
        tools.library_status(
            {},
            ctx=ctx,
            secret_reader=lambda n: "secret-key",
            client_factory=None,
        )
    )
    assert result["ok"] is False
    assert result["reason"] == "jellyfin_client_unavailable"


class _OkClient:
    def __init__(self, base_url, api_key, user_id=None):
        self.base_url = base_url
        self.api_key = api_key
        self.user_id = user_id

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def status(self):
        return {"server_name": "demo", "version": "10.9.0", "movie_count": 3}


def test_library_status_success():
    ctx = FakeCtx(config={"jellyfin_url": "http://example:8096"})
    tools.bind_context(ctx)
    tools.bind_client_factory(None)
    result = json.loads(
        tools.library_status(
            {},
            ctx=ctx,
            secret_reader=lambda n: "secret-key",
            client_factory=_OkClient,
        )
    )
    assert result["ok"] is True
    assert result["server_name"] == "demo"
    assert result["movie_count"] == 3


class _FailingClient:
    def __init__(self, base_url, api_key, user_id=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def status(self):
        raise RuntimeError("boom")


def test_library_status_connection_failure():
    ctx = FakeCtx(config={"jellyfin_url": "http://example:8096"})
    tools.bind_context(ctx)
    result = json.loads(
        tools.library_status(
            {},
            ctx=ctx,
            secret_reader=lambda n: "secret-key",
            client_factory=_FailingClient,
        )
    )
    assert result["ok"] is False
    assert result["reason"] == "jellyfin_unreachable"
    assert "boom" in result["hint"]


class _ErrorShapedClient:
    def __init__(self, base_url, api_key, user_id=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def status(self):
        return {"ok": False, "reason": "jellyfin_auth", "hint": "bad key"}


def test_library_status_propagates_client_error():
    ctx = FakeCtx(config={"jellyfin_url": "http://example:8096"})
    tools.bind_context(ctx)
    result = json.loads(
        tools.library_status(
            {},
            ctx=ctx,
            secret_reader=lambda n: "secret-key",
            client_factory=_ErrorShapedClient,
        )
    )
    assert result["ok"] is False
    assert result["reason"] == "jellyfin_auth"
    assert result["hint"] == "bad key"


def test_no_context_returns_error():
    tools.bind_context(None)
    result = json.loads(tools.library_status({}, secret_reader=lambda n: "k"))
    assert result["ok"] is False
    assert result["reason"] == "not_configured"


def test_errors_payload_shape():
    assert errors.error_payload("r", "h", extra=1) == {
        "ok": False,
        "reason": "r",
        "hint": "h",
        "extra": 1,
    }
    assert errors.ok_payload(x=2) == {"ok": True, "x": 2}
