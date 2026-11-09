# Hermes Screen

A Jellyfin-first plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent).
Work in progress for the November 2026 Hermes Agent Plugin Hackathon.

## Implemented today

The only registered tool is **`library_status`**. It checks your configured Jellyfin
server, resolves a user, and returns the server name/version and available library
counts. Failures return a short reason and a hint.

The Jellyfin client also has mocked coverage for library filtering, resume,
Next Up and session evidence. Those methods are **not** exposed as tools and the
deterministic picker module is not yet integrated or registered. Picking titles,
Roku playback/control, Telegram pick/play/pause, `/watch`, YouTube and Friday
voting are planned, not available. Roku ECP shipping restrictions remain
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

Public `config_schema` entries (all read through `ctx.get_config` on every call):

- `jellyfin_url` — string, required.
- `jellyfin_api_key` — secret, env `JELLYFIN_API_KEY`, read only through Hermes's
  secret scope (`agent.secret_scope.get_secret`). Never from `.env` or
  `os.environ`.
- `jellyfin_user` — string, optional (exact case-sensitive username or GUID).

Non-text settings are rejected. There are no shell commands, background
processes, SSDP/Roku requests or third-party service calls at runtime in this
build.

## Security scan state

`hermes plugins doctor . --ci` is clean. `hermes plugins validate . --install-deps`
passes with verdict **caution**, caused by one high-severity finding:

- `context_exfil` at `docs/HARDWARE.md:4`: the scanner matched the verb "output"
  followed shortly by the noun "conversation" in the provenance line.

This is a false positive in intent: the line documents where the probe evidence
came from; it is not an instruction to disclose prior chat history. The match is
incidental to those two words appearing close together. A minimal rewording of
that manager-owned line (changing "conversation" to "thread") makes the scan
report **safe**; see `docs/SUBMISSION.md` for the proposed patch. It is not
applied here because `docs/HARDWARE.md` is manager-owned.

Other scan findings are medium/low (for example, hardcoded LAN IPs in evidence
docs, unpinned development install commands, and `os.environ` mentions in
documentation) and do not change the verdict.

## Source provenance

- Plugin tree verified at `9320c3638d9f7d8579326e1a622a205523b395d1`
  (docs-only after integration review).
- Integration SHA reviewed with zero blocking findings:
  `4362ed1ecdb2a3606695925e24a79b3949063414`.
- Jellyfin client worker result: `c4c6c83e171a646b830b418cda79b6e420ecdf77`.
- Native skeleton worker result: `4ebcb722500fffea9f1af65f909298a1b294d888`.
- Hermes upstream (verified): `v0.22.0` /
  `e06df9c2eae6901f4c88f464e0ae6e753c0428b8`.
- Jellyfin OpenAPI: `12.4.0`, SHA256
  `02a6064916b7e08f1f1d8d7ffc1fb1c7623df0e378729fcd7fd353766868036e`.
- Jellyfin server: `terebi` `12.2.0` at `http://192.168.0.126:8097` (public
  endpoint reachable; authenticated access unverified).
- Roku: model 4200X at `192.168.0.104` (read-only probe evidence only).

## Publication gates (not yet met)

- No catalog PR has been opened and no commit is pinned for publication.
- Hardware gate is open: Roku app sign-in and manual playback are pending; no
  launch, in-app play, pause, wake or exact item ID has been demonstrated.
- Roku ECP third-party shipping restriction is unresolved.
- Authenticated Jellyfin compatibility is unverified.
- The deterministic picker is not integrated or registered as a tool.
- No TMDB, Chromecast or watcher implementation exists or is planned for the
  hackathon scope.

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
