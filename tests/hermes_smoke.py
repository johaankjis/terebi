"""Optional official-loader smoke: run with Hermes + respx installed, outside the repo.

Usage: python /path/to/tests/hermes_smoke.py /path/to/native/plugin/root
This is separate from pytest so unit tests do not require Hermes.
"""

import json
import sys
from pathlib import Path

import respx
from agent.secret_scope import reset_secret_scope, set_secret_scope
from hermes_cli.plugins_loader import PluginLoaderMixin
from hermes_cli.plugins_manifest import PluginManifest
from utils import fast_safe_load


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    assert str(root) not in sys.path
    manifest_data = fast_safe_load((root / "plugin.yaml").read_text())
    manifest = PluginManifest(name=manifest_data["name"], path=str(root))
    loader = PluginLoaderMixin()
    module = loader._load_directory_module(manifest, module_name="hermes_plugins.screen_smoke")
    assert module.__package__ == "hermes_plugins.screen_smoke"

    class Context:
        def __init__(self, url):
            self.url = url
            self.tools = []

        def get_config(self, name, default=None):
            return self.url if name == "jellyfin_url" else default

        def register_tool(self, **kwargs):
            self.tools.append(kwargs)

    first, second = Context("http://first.test"), Context("http://second.test")
    module.register(first)
    module.register(second)
    assert [t["name"] for t in first.tools] == manifest_data["provides_tools"]
    with respx.mock(assert_all_called=True) as router:
        for url, name in [(first.url, "First"), (second.url, "Second")]:
            router.get(url + "/System/Info/Public").respond(
                200, json={"ServerName": name, "Version": "12.4.0"}
            )
            router.get(url + "/Users").respond(200, json=[{"Id": "a" * 32, "Name": name}])
            router.get(url + "/Items/Counts").respond(200, json={"MovieCount": 3})
        for ctx, name, secret in [
            (first, "First", "key-one"),
            (second, "Second", "key-two"),
            (first, "First", "key-three"),
        ]:
            token = set_secret_scope({"JELLYFIN_API_KEY": secret})
            try:
                result = json.loads(ctx.tools[0]["handler"]({}))
            finally:
                reset_secret_scope(token)
            assert result["ok"] is True and result["server"]["name"] == name
            assert f'Token="{secret}"' in router.calls[-1].request.headers["Authorization"]
    print("PASS: official namespaced loader, YAML, real client + respx, scoped secret rotation")


if __name__ == "__main__":
    main()
