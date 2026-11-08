# Hermes Screen

A Jellyfin-first plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent).
Work in progress for the November 2026 Hermes Agent Plugin Hackathon.

## Implemented today

The only registered tool is **`library_status`**. It checks your configured Jellyfin
server, resolves a user, and returns the server name/version and available library
counts. Failures return a short reason and a hint.

The underlying client also has mocked coverage for library filtering, resume,
Next Up and session evidence. Those methods are not yet exposed as tools.
Picking titles, Roku playback/control, Telegram pick/play/pause, `/watch`, YouTube
and Friday voting are planned, not available. Roku ECP shipping restrictions remain
unresolved; this build contains no TV control or discovery.

## Install and configure

This branch is not published in the catalog. For local development, use Python
3.11+ and install from the checkout:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
ruff check .
ruff format --check .
```

Hermes loads the repository as a native directory plugin with `plugin.yaml` and
`__init__.py` at its root. Install/enable that directory using your Hermes plugin
workflow. A Python wheel contains the same layout under `hermes_screen_plugin`;
installing the wheel alone does not enable it in Hermes.

In Hermes plugin settings, set `jellyfin_url` (including any server base path),
optional `jellyfin_user` (exact, case-sensitive username or GUID), and the
`JELLYFIN_API_KEY` secret (Jellyfin Dashboard > API Keys). If user is omitted, the
server must have exactly one enabled user. Settings and secrets are read through
Hermes on every tool call; the plugin does not read `.env` files.

The compatible source floor was checked against released Hermes **v0.22.0**:
official doctor and isolated validate passed. The installed ZimaOS Hermes version
is still unknown. Jellyfin requests follow the upstream **12.4.0 OpenAPI**; the
laptop server version is unknown and no live-server compatibility is claimed.
See [integration evidence](docs/INTEGRATION.md) for exact commands and revisions.

## Troubleshooting

- Missing settings: set the URL and API-key secret in Hermes, then retry.
- Ambiguous user: set the exact username or GUID; the plugin never picks the first user.
- Authentication failure: check the API key and user permissions.
- Connection failure: check the URL, base path and server reachability from Hermes.
- Secret-scope/configuration failure: check the active Hermes profile and plugin settings.

## Privacy and network use

The implemented tool makes HTTP requests only to the configured Jellyfin server,
with explicit 8-second request timeouts. Redirects are not followed. API keys are
sent in authentication headers, never query strings. There are no shell commands,
background processes, SSDP, Roku requests or third-party service calls at runtime.
Server/user names and library data returned in chat may be seen by your model provider.

Session `verified` means matching item identity on a fresh target session, including
paused sessions. `playing: true` separately reports active-play evidence;
`playing: null` establishes neither play nor pause. This is not Roku verification.

## Contributing

Read [AGENTS.md](AGENTS.md), [SOUL.md](SOUL.md) and [the plan](docs/PLAN.md).
All automated HTTP tests use mocks; hardware verification remains open.

## License

MIT
