"""Tests for Config secret/settings access."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from hermes_screen.config import Config  # noqa: E402


class FakeCtx:
    def __init__(self, config=None):
        self.config = dict(config or {})

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def set_config(self, key, value):
        self.config[key] = value


def test_config_reads_values():
    ctx = FakeCtx(
        config={
            "jellyfin_url": "http://example:8096",
            "jellyfin_user": "alice",
            "roku_ip": "10.0.0.5",
            "default_room": "den",
        }
    )
    cfg = Config(ctx, secret_reader=lambda name: "key-123")
    assert cfg.jellyfin_url() == "http://example:8096"
    assert cfg.jellyfin_api_key() == "key-123"
    assert cfg.jellyfin_user() == "alice"
    assert cfg.roku_ip() == "10.0.0.5"
    assert cfg.default_room() == "den"
    assert cfg.is_jellyfin_configured() is True


def test_config_missing_uses_defaults():
    ctx = FakeCtx(config={})
    cfg = Config(ctx, secret_reader=lambda name: None)
    assert cfg.jellyfin_url() is None
    assert cfg.jellyfin_api_key() is None
    assert cfg.jellyfin_user() is None
    assert cfg.roku_ip() is None
    assert cfg.default_room() == "living room"
    assert cfg.is_jellyfin_configured() is False


def test_config_empty_strings_treated_as_missing():
    ctx = FakeCtx(config={"jellyfin_url": "   ", "default_room": ""})
    cfg = Config(ctx, secret_reader=lambda name: "")
    assert cfg.jellyfin_url() is None
    assert cfg.jellyfin_api_key() is None
    assert cfg.default_room() == "living room"
    assert cfg.is_jellyfin_configured() is False


def test_config_secret_reader_receives_env_name():
    seen = []

    def reader(name):
        seen.append(name)
        return "k"

    ctx = FakeCtx(config={"jellyfin_url": "http://example:8096"})
    cfg = Config(ctx, secret_reader=reader)
    assert cfg.jellyfin_api_key() == "k"
    assert seen == ["JELLYFIN_API_KEY"]
