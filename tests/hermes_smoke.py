"""Optional official-loader smoke: run with Hermes + respx installed, outside the repo.

Usage: python /path/to/tests/hermes_smoke.py /path/to/native/plugin/root
This is separate from pytest so unit tests do not require Hermes.
"""

import http.client
import json
import socket
import sys
from pathlib import Path

import respx
from agent.secret_scope import reset_secret_scope, set_secret_scope
from cast_fixtures import BBB_ID, cast_item  # tests/ is sys.path[0] when run as a script
from fake_cast import FakeClock, FakeReceiver
from hermes_cli.plugins_loader import PluginLoaderMixin
from hermes_cli.plugins_manifest import PluginManifest
from utils import fast_safe_load


def empty_page() -> dict:
    return {"Items": [], "TotalRecordCount": 0, "StartIndex": 0}


def movie(server: str) -> dict:
    return {
        "Id": "b" * 32,
        "Name": f"{server} Movie",
        "Type": "Movie",
        "ProductionYear": 2010,
        "RunTimeTicks": 20 * 600_000_000,
        "Genres": ["Comedy"],
        "UserData": {"Played": False, "PlaybackPositionTicks": 0},
    }


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    assert str(root) not in sys.path
    manifest_data = fast_safe_load((root / "plugin.yaml").read_text())
    manifest = PluginManifest(name=manifest_data["name"], path=str(root))
    loader = PluginLoaderMixin()
    module = loader._load_directory_module(manifest, module_name="hermes_plugins.screen_smoke")
    assert module.__package__ == "hermes_plugins.screen_smoke"

    def free_port() -> int:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    class Context:
        def __init__(self, url):
            self.url = url
            self.tools = []
            self.unload = []
            self.port = free_port()
            self.settings = {
                "jellyfin_url": url,
                "chromecast_host": "192.0.2.50",
                "cast_media_base_url": "http://192.0.2.10:8765",
                "cast_relay_bind": f"127.0.0.1:{self.port}",
            }

        def get_config(self, name, default=None):
            return self.settings.get(name, default)

        def register_tool(self, **kwargs):
            self.tools.append(kwargs)

        def on_unload(self, callback):
            self.unload.append(callback)

    first, second = Context("http://first.test"), Context("http://second.test")
    module.register(first)
    module.register(second)
    assert [t["name"] for t in first.tools] == manifest_data["provides_tools"]
    assert manifest_data["provides_tools"] == [
        "library_status",
        "library_pick",
        "tv_play",
        "tv_pause",
    ]
    assert [t["name"] for t in second.tools] == manifest_data["provides_tools"]
    status_tool, pick_tool, play_tool, pause_tool = 0, 1, 2, 3
    uid = "a" * 32
    with respx.mock(assert_all_called=True) as router:
        for url, name in [(first.url, "First"), (second.url, "Second")]:
            router.get(url + "/System/Info/Public").respond(
                200, json={"ServerName": name, "Version": "12.4.0"}
            )
            router.get(url + "/Users").respond(200, json=[{"Id": uid, "Name": name}])
            router.get(url + "/Items/Counts").respond(200, json={"MovieCount": 3})
            router.get(url + "/UserItems/Resume").respond(200, json=empty_page())
            router.get(url + "/Shows/NextUp").respond(200, json=empty_page())
            router.get(url + "/Items").respond(
                200, json={"Items": [movie(name)], "TotalRecordCount": 1, "StartIndex": 0}
            )
        for ctx, name, secret in [
            (first, "First", "key-one"),
            (second, "Second", "key-two"),
            (first, "First", "key-three"),
        ]:
            token = set_secret_scope({"JELLYFIN_API_KEY": secret})
            try:
                result = json.loads(ctx.tools[status_tool]["handler"]({}))
            finally:
                reset_secret_scope(token)
            assert result["ok"] is True and result["server"]["name"] == name
            assert f'Token="{secret}"' in router.calls[-1].request.headers["Authorization"]
        for ctx, name, secret in [
            (first, "First", "pick-one"),
            (second, "Second", "pick-two"),
            (first, "First", "pick-three"),
        ]:
            token = set_secret_scope({"JELLYFIN_API_KEY": secret})
            try:
                result = json.loads(
                    ctx.tools[pick_tool]["handler"]({"max_minutes": 30, "limit": 1})
                )
            finally:
                reset_secret_scope(token)
            assert result["ok"] is True, result
            assert [p["title"] for p in result["picks"]] == [f"{name} Movie"]
            assert result["picks"][0]["source"] == "unwatched"
            assert f'Token="{secret}"' in router.calls[-1].request.headers["Authorization"]
            assert router.calls[-1].request.url.host == ctx.url.split("//")[1].split(":")[0]
        token = set_secret_scope({"JELLYFIN_API_KEY": "bad-args"})
        try:
            bad = json.loads(first.tools[pick_tool]["handler"]({"max_minutes": 0}))
            wrong = json.loads(first.tools[pick_tool]["handler"]({"limit": 2}))
        finally:
            reset_secret_scope(token)
        assert bad["ok"] is False and bad["reason"] == "invalid_argument"
        assert wrong["ok"] is False and wrong["reason"] == "invalid_argument"
        # No scoped secret: a structured error, not an exception.
        missing = json.loads(first.tools[pick_tool]["handler"]({"max_minutes": 30}))
        assert missing["ok"] is False and missing["reason"] in ("not_configured", "jellyfin_config")
    # tv_play / tv_pause: real Jellyfin client (respx), real relay on 127.0.0.1,
    # scripted fake Chromecast swapped in for the plugin's own connector.
    cast_mod = sys.modules[module.__name__ + ".hermes_screen.cast"]
    playback = sys.modules[module.__name__ + ".hermes_screen.playback"]
    receiver = FakeReceiver(FakeClock(), cast_module=cast_mod)
    playback.connect_chromecast = receiver.connect
    with respx.mock(assert_all_called=True) as router:
        router.get(first.url + "/Users").respond(200, json=[{"Id": uid, "Name": "First"}])
        router.get(first.url + f"/Items/{BBB_ID}").respond(200, json=cast_item())
        stream = router.get(first.url + f"/Videos/{BBB_ID}/stream").respond(
            200, content=b"mp4-bytes"
        )
        token = set_secret_scope({"JELLYFIN_API_KEY": "cast-key"})
        try:
            bad = json.loads(first.tools[play_tool]["handler"]({"item_id": "Big Buck Bunny"}))
            played = json.loads(first.tools[play_tool]["handler"]({"item_id": BBB_ID}))
        finally:
            reset_secret_scope(token)
        assert bad["ok"] is False and bad["reason"] == "invalid_argument"
        assert played["ok"] is True and played["verified"] is True, played
        assert played["item"]["item_id"] == BBB_ID
        assert "cast-key" not in json.dumps(played) and "/cast/" not in json.dumps(played)
        url = receiver.content_id
        assert "cast-key" not in url and url.startswith("http://192.0.2.10:8765/cast/")
        conn = http.client.HTTPConnection("127.0.0.1", first.port, timeout=5)
        conn.request("GET", url.removeprefix("http://192.0.2.10:8765"))
        response = conn.getresponse()
        assert response.status == 200 and response.read() == b"mp4-bytes"
        conn.close()
        assert 'Token="cast-key"' in stream.calls[-1].request.headers["Authorization"]
        other = json.loads(second.tools[pause_tool]["handler"]({}))
        assert other["ok"] is False and other["reason"] == "nothing_playing"
        paused = json.loads(first.tools[pause_tool]["handler"]({}))
        assert paused["ok"] is True and paused["state"] == "paused", paused
        again = json.loads(first.tools[pause_tool]["handler"]({}))
        assert again["ok"] is True and again["already_paused"] is True
    assert len(first.unload) == 1 and len(second.unload) == 1
    for callback in first.unload + second.unload:
        callback()
    try:
        socket.create_connection(("127.0.0.1", first.port), timeout=1).close()
        raise AssertionError("relay still listening after unload")
    except OSError:
        pass
    print(
        "PASS: official namespaced loader, YAML, library_status + library_pick + tv_play + "
        "tv_pause through real client + respx + local relay + fake Chromecast, scoped "
        "secret rotation, context isolation, on_unload cleanup"
    )


if __name__ == "__main__":
    main()
