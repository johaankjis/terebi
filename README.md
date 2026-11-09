# Hermes Screen

A Jellyfin-first plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent).
Work in progress for the November 2026 Hermes Agent Plugin Hackathon.

## Implemented today

Two tools are registered:

- **`library_status`** checks your configured Jellyfin server, resolves a user, and
  returns the server name/version and available library counts.
- **`library_pick`** (`max_minutes`, optional `limit` 1 to 3, default 3) picks up to
  three watchable items from your Jellyfin library, in this order: unfinished items
  to resume, Next Up episodes, then never-watched movies/videos. Resume and Next Up
  items must fit in their *remaining* time and unwatched items in their full runtime,
  strictly within `max_minutes`; items with unknown runtime are never picked. Each
  pick carries a one-line reason drawn only from Jellyfin's watch state and metadata.
  It only reads the library: it does **not** start anything on the TV.

Failures return a short reason and a hint. A failed Jellyfin lookup is reported as
an error or a partial result, never as "nothing to watch".

The Jellyfin client also has mocked coverage for library search and session
evidence; those methods are **not** exposed as tools. `library_pick` is verified
only against mocked Jellyfin responses, not yet against the live server or from
Telegram. Roku playback/control (`tv_*`), Telegram pick/play/pause, `/watch`,
YouTube and Friday voting are planned, not available. Roku ECP shipping
restrictions remain unresolved; this build contains no TV control or discovery.

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

Roku settings are not part of the public configuration yet because Roku control is
not implemented.

## Version compatibility

- Declared Hermes floor: `requires_hermes: ">=0.22.0"` (in both `plugin.yaml` and,
  later, the catalog entry).
- The compatible source floor was checked against released Hermes **v0.22.0**
  (`e06df9c2eae6901f4c88f464e0ae6e753c0428b8`): official doctor, isolated
  validate and mocked tool smoke passed.
- The installed ZimaOS Hermes is **v0.16.0**, below this plugin's declared
  minimum; testing uses a separate v0.22.0 runtime without upgrading that
  installation.
- Jellyfin requests follow the upstream **12.4.0 OpenAPI**. The actual server
  reports **12.2.0** and its public endpoint is reachable from the Hermes
  container; authenticated library and session compatibility remain unverified.
- Python 3.11+; production dependency is `httpx` only.

See [integration evidence](docs/INTEGRATION.md) for exact commands and revisions.

## Supported configuration and secrets

Public `config_schema` entries (settings via `ctx.get_config`, secrets via
`agent.secret_scope.get_secret`, read on every call):

- `jellyfin_url` — string, required.
- `jellyfin_api_key` — secret, env `JELLYFIN_API_KEY`, read only through Hermes's
  secret scope (`agent.secret_scope.get_secret`). Never from `.env` or
  `os.environ`.
- `jellyfin_user` — string, optional (exact case-sensitive username or GUID).

Non-text settings are rejected. There are no shell commands, background
processes, SSDP/Roku requests or third-party service calls at runtime in this
build.

## Validation

Official Hermes v0.22.0 doctor, validate (security verdict **safe**) and mocked
loader smoke pass on the integrated tree; 385 tests and Ruff pass. Details are in
[integration evidence](docs/INTEGRATION.md). They do not establish authenticated
live-server compatibility or working TV playback. Catalog rules distinguish a
validation failure from a caution finding requiring review.

## Publication gates (not yet met)

- No catalog PR has been opened and no commit is pinned for publication.
- Hardware gate is open: Roku app sign-in and manual playback are pending; no
  launch, in-app play, pause, wake or exact item ID has been demonstrated.
- Roku ECP third-party shipping restriction is unresolved.
- Authenticated Jellyfin compatibility is unverified.
- `library_pick` is registered but not yet verified through a live Hermes session,
  against the live Jellyfin server, or from Telegram; `/watch` is not built.
- No TMDB, Chromecast or watcher implementation exists or is planned for the
  hackathon scope.

## Troubleshooting

- Missing settings: set the URL and API-key secret in Hermes, then retry.
- Ambiguous user: set the exact username or GUID; the plugin never picks the first user.
- Authentication failure: check the API key and user permissions.
- Connection failure: check the URL, base path and server reachability from Hermes.
- Secret-scope/configuration failure: check the active Hermes profile and plugin settings.

## Privacy and network use

The implemented tools make HTTP requests only to the configured Jellyfin server,
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
