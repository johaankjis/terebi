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
    assert [t["name"] for t in ctx.registered] == manifest["provides_tools"]
    assert manifest["provides_tools"] == [
        "library_status",
        "library_pick",
        "tv_play",
        "tv_pause",
        "library_scene_find",
        "library_scene_save",
        "tv_scene_play",
        "tv_game_start",
    ]
    assert plugin.PROVIDES_TOOLS == manifest["provides_tools"]
    assert manifest["provides_hooks"] == []
    schemas = {t["name"]: t["schema"] for t in ctx.registered}
    assert all(name == schema["name"] for name, schema in schemas.items())
    pick = schemas["library_pick"]["parameters"]
    assert pick["required"] == ["max_minutes"]
    assert pick["properties"]["max_minutes"]["type"] == "number"
    limit = pick["properties"]["limit"]
    assert (limit["type"], limit["minimum"], limit["maximum"], limit["default"]) == (
        "integer",
        1,
        3,
        3,
    )
    assert all(t["toolset"] == "hermes_screen" and callable(t["handler"]) for t in ctx.registered)


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


# --- library_pick ------------------------------------------------------------------------

BASE = "http://jellyfin.test:8096"
MIN = 600_000_000  # ticks per minute


def iid(n):
    return f"{n:032x}"


def movie(n, **kw):
    data = {
        "Id": iid(n),
        "Name": f"Movie {n}",
        "Type": "Movie",
        "ProductionYear": 2010,
        "RunTimeTicks": 30 * MIN,
        "Genres": ["Comedy"],
        "UserData": {"Played": False, "PlaybackPositionTicks": 0},
    }
    data.update(kw)
    return data


def page(items):
    return {"Items": items, "TotalRecordCount": len(items), "StartIndex": 0}


def pick_routes(router, resume=(), next_up=(), items=(), url=BASE):
    router.get(f"{url}/Users/{UID}").respond(200, json={"Id": UID, "Name": "Ann"})
    router.get(f"{url}/UserItems/Resume").respond(200, json=page(list(resume)))
    router.get(f"{url}/Shows/NextUp").respond(200, json=page(list(next_up)))
    router.get(f"{url}/Items").respond(200, json=page(list(items)))


def pick(plugin, args, ctx=None, reader=lambda _: "test-key"):
    ctx = FakeCtx(jellyfin_user=UID) if ctx is None else ctx
    return json.loads(plugin.tools.library_pick(args, ctx=ctx, secret_reader=reader))


def test_pick_ranks_resume_then_next_up_then_unwatched(plugin, respx_mock):
    resume = movie(
        1,
        Name="Sintel",
        RunTimeTicks=15 * MIN,
        UserData={"Played": False, "PlaybackPositionTicks": 9 * MIN},
    )
    episode = movie(
        2,
        Name="Chapter Two",
        Type="Episode",
        RunTimeTicks=22 * MIN,
        SeriesId=iid(50),
        SeriesName="Big Show",
        ParentIndexNumber=1,
        IndexNumber=2,
    )
    pick_routes(respx_mock, [resume], [episode], [movie(3, Name="Spring", RunTimeTicks=8 * MIN)])
    result = pick(plugin, {"max_minutes": 30})
    assert result["ok"] is True and result["complete"] is True
    assert [(p["source"], p["title"]) for p in result["picks"]] == [
        ("resume", "Sintel"),
        ("next_up", "Chapter Two"),
        ("unwatched", "Spring"),
    ]
    assert "9 min in on Sintel" in result["picks"][0]["why"]
    assert "Big Show S1E2" in result["picks"][1]["why"]
    assert "tagged Comedy" in result["picks"][2]["why"]
    requests = [c.request for c in respx_mock.calls]
    assert all('Token="test-key"' in r.headers["Authorization"] for r in requests)
    assert all(r.extensions["timeout"]["read"] == 8 for r in requests)


def test_pick_limit_stops_after_enough_picks(plugin, respx_mock):
    resumes = [
        movie(n, UserData={"Played": False, "PlaybackPositionTicks": 5 * MIN}) for n in (1, 2)
    ]
    pick_routes(respx_mock, resumes, [], [movie(3)])
    result = pick(plugin, {"max_minutes": 60, "limit": 2})
    assert [p["source"] for p in result["picks"]] == ["resume", "resume"]
    assert result["sources"]["next_up"] == {"status": "skipped", "reason": "enough_picks"}
    assert all(c.request.url.path != "/Items" for c in respx_mock.calls)


def test_pick_filters_by_runtime(plugin, respx_mock):
    long_resume = movie(
        1, RunTimeTicks=120 * MIN, UserData={"Played": False, "PlaybackPositionTicks": 10 * MIN}
    )
    unknown = movie(2)
    del unknown["RunTimeTicks"]
    pick_routes(
        respx_mock,
        [long_resume],
        [],
        [movie(3, Name="Too Long", RunTimeTicks=61 * MIN), unknown, movie(4, Name="Fits")],
    )
    result = pick(plugin, {"max_minutes": 60})
    assert [p["title"] for p in result["picks"]] == ["Fits"]


def test_pick_accepts_json_string_and_default_limit(plugin, respx_mock):
    pick_routes(respx_mock, items=[movie(n, RunTimeTicks=n * MIN) for n in range(1, 6)])
    result = pick(plugin, json.dumps({"max_minutes": 30, "limit": None}))
    assert result["ok"] is True and len(result["picks"]) == 3
    assert [p["minutes"] for p in result["picks"]] == [5, 4, 3]


def test_pick_nothing_fits_is_ok_with_note(plugin, respx_mock):
    pick_routes(respx_mock)
    result = pick(plugin, {"max_minutes": 5})
    assert result["ok"] is True and result["picks"] == [] and "note" in result


def test_pick_jellyfin_failure_is_not_empty_success(plugin, respx_mock):
    respx_mock.get(f"{BASE}/Users/{UID}").respond(401, text="PRIVATE-KEY")
    result = pick(plugin, {"max_minutes": 30})
    assert result["ok"] is False and result["reason"] == "jellyfin_auth"
    assert "PRIVATE-KEY" not in json.dumps(result)


@pytest.mark.parametrize(
    "args",
    [
        None,
        [],
        3,
        True,
        "",
        "not json",
        "[1]",
        "3",
        {},
        {"limit": 2},
        {"max_minutes": 30, "mood": "happy"},
        {"max_minutes": "30"},
        {"max_minutes": None},
        {"max_minutes": True},
        {"max_minutes": 0},
        {"max_minutes": -5},
        {"max_minutes": 1441},
        {"max_minutes": float("nan")},
        {"max_minutes": float("inf")},
        {"max_minutes": 30, "limit": 0},
        {"max_minutes": 30, "limit": 4},
        {"max_minutes": 30, "limit": 10**30},
        {"max_minutes": 30, "limit": 2.0},
        {"max_minutes": 30, "limit": "2"},
        {"max_minutes": 30, "limit": True},
        '{"max_minutes": NaN}',
    ],
)
def test_pick_invalid_arguments_make_no_http_call(plugin, respx_mock, args):
    result = pick(plugin, args)
    assert result["ok"] is False and result["reason"] == "invalid_argument"
    assert set(result) == {"ok", "reason", "hint"}
    assert len(respx_mock.calls) == 0


def test_pick_unknown_argument_hint_is_bounded_and_text_only(plugin, respx_mock):
    result = pick(plugin, {"max_minutes": 30, "x" * 500: 1})
    assert result["reason"] == "invalid_argument" and len(result["hint"]) < 250


def test_pick_missing_config_and_context(plugin):
    assert pick(plugin, {"max_minutes": 30}, FakeCtx(""))["reason"] == "not_configured"
    assert pick(plugin, {"max_minutes": 30}, reader=lambda _: None)["reason"] == "not_configured"
    result = json.loads(plugin.tools.library_pick({"max_minutes": 30}, secret_reader=None))
    assert result["reason"] == "not_configured"


@pytest.mark.parametrize("field", ["jellyfin_url", "jellyfin_user", "secret"])
@pytest.mark.parametrize("value", [True, 3, [], {}, ["secret-value"]])
def test_pick_wrong_setting_types_fail_safely(plugin, field, value):
    ctx = FakeCtx()
    reader = (lambda _: value) if field == "secret" else (lambda _: "test-key")
    if field != "secret":
        ctx.settings[field] = value
    result = pick(plugin, {"max_minutes": 30}, ctx, reader)
    assert result["reason"] == "jellyfin_config"
    assert "secret-value" not in json.dumps(result)


@pytest.mark.parametrize("source", ["config", "secret", "import", "picker", "client"])
def test_pick_failures_never_echo_exception(plugin, monkeypatch, source):
    ctx = FakeCtx(jellyfin_user=UID)

    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE-KEY https://private:password@host")

    reader = lambda _: "test-key"  # noqa: E731
    if source == "config":
        monkeypatch.setattr(ctx, "get_config", fail)
    elif source == "secret":
        reader = fail
    elif source == "import":
        original = builtins.__import__

        def importing(name, *args, **kwargs):
            if name == "hermes_screen.picker":
                fail()
            return original(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", importing)
    elif source == "picker":
        module = __import__(plugin.__name__ + ".hermes_screen.picker", fromlist=["pick_titles"])
        monkeypatch.setattr(module, "pick_titles", fail)
    else:
        module = __import__(
            plugin.__name__ + ".hermes_screen.jellyfin", fromlist=["JellyfinClient"]
        )
        monkeypatch.setattr(module.JellyfinClient, "__enter__", fail)
    result = pick(plugin, {"max_minutes": 30}, ctx, reader)
    assert result["ok"] is False
    assert set(result) == {"ok", "reason", "hint"}
    assert "PRIVATE-KEY" not in json.dumps(result)
    assert "password" not in json.dumps(result)


def test_pick_transport_failure_is_structured(plugin, respx_mock):
    respx_mock.get(f"{BASE}/Users/{UID}").mock(side_effect=httpx.ConnectError("PRIVATE-KEY"))
    result = pick(plugin, {"max_minutes": 30})
    assert result["ok"] is False and result["reason"] == "jellyfin_unreachable"
    assert "PRIVATE-KEY" not in json.dumps(result)


def test_pick_constructor_validation_is_structured(plugin):
    ctx = FakeCtx("http://user:PRIVATE-KEY@host")
    result = pick(plugin, {"max_minutes": 30}, ctx)
    assert result["reason"] == "jellyfin_config"
    assert "PRIVATE-KEY" not in json.dumps(result)


def test_pick_contexts_do_not_leak(plugin, respx_mock, monkeypatch):
    config = sys.modules[plugin.__name__ + ".hermes_screen.config"]
    key = ["first-key"]
    monkeypatch.setattr(config, "_default_secret_reader", lambda _: key[0])
    first = FakeCtx("http://first.test", jellyfin_user=UID)
    second = FakeCtx("http://second.test", jellyfin_user=UID)
    plugin.register(first)
    plugin.register(second)
    pick_routes(respx_mock, items=[movie(1, Name="First Pick")], url="http://first.test")
    pick_routes(respx_mock, items=[movie(2, Name="Second Pick")], url="http://second.test")
    handler = lambda ctx: ctx.registered[1]["handler"]  # noqa: E731
    titles = []
    for ctx, secret, passed in [
        (first, "first-key", None),
        (second, "second-key", None),
        (first, "new-first-key", second),  # a ctx kwarg from the caller is ignored
    ]:
        key[0] = secret
        kwargs = {} if passed is None else {"ctx": passed}
        result = json.loads(handler(ctx)({"max_minutes": 30}, **kwargs))
        titles.append(result["picks"][0]["title"])
        assert f'Token="{secret}"' in respx_mock.calls[-1].request.headers["Authorization"]
        assert str(respx_mock.calls[-1].request.url).startswith(ctx.settings["jellyfin_url"])
    assert titles == ["First Pick", "Second Pick", "First Pick"]
