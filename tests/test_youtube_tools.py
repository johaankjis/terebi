"""Hermes YouTube registration/wiring and context isolation without hardware."""

import importlib
import json
from types import SimpleNamespace

from test_plugin import FakeCtx
from test_plugin import plugin as plugin


def test_direct_link_never_reads_search_secret_and_invalid_input_never_casts(plugin):
    module = importlib.import_module(plugin.__name__ + ".youtube_tools")
    calls = []
    manager = SimpleNamespace(call=lambda *a, **k: calls.append((a, k)) or {"ok": True})

    def forbidden(_):
        raise AssertionError("No secret needed for direct video")

    ctx = FakeCtx(chromecast_host="192.0.2.10")
    result = module.call(
        "play",
        {"video": "https://youtu.be/aqz-KE-bpKQ"},
        ctx=ctx,
        manager=manager,
        secret_reader=forbidden,
    )
    assert json.loads(result)["ok"]
    assert calls == [(("192.0.2.10", "aqz-KE-bpKQ"), {"pause": False})]
    assert (
        json.loads(module.call("play", {"video": "https://evil.test/"}, ctx=ctx, manager=manager))[
            "reason"
        ]
        == "invalid_argument"
    )
    assert (
        json.loads(module.call("pause", {"video": "extra"}, ctx=ctx, manager=manager))["reason"]
        == "invalid_argument"
    )
    assert len(calls) == 1


def test_search_secret_scope_and_no_key_fallback(plugin):
    module = importlib.import_module(plugin.__name__ + ".youtube_tools")
    names = []
    result = json.loads(
        module.call(
            "search",
            {"query": "Bunny"},
            ctx=FakeCtx(),
            manager=None,
            secret_reader=lambda name: names.append(name),
        )
    )
    assert names == ["YOUTUBE_API_KEY"]
    assert result["reason"] == "youtube_search_not_configured"


def test_registered_contexts_have_distinct_ownership(plugin):
    a, b = FakeCtx(), FakeCtx()
    plugin.register(a)
    plugin.register(b)

    def owner(ctx):
        handler = next(t["handler"] for t in ctx.registered if t["name"] == "tv_youtube_play")
        return dict(
            zip(
                handler.__code__.co_freevars,
                (cell.cell_contents for cell in handler.__closure__),
                strict=True,
            )
        )["youtube_manager"]

    assert owner(a) is not owner(b)
