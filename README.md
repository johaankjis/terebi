# Hermes Screen

A Jellyfin-first plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent).
Work in progress for the November 2026 Hermes Agent Plugin Hackathon.

## Implemented today

Four tools are registered:

- **`library_status`** checks your configured Jellyfin server, resolves a user, and
  returns the server name/version and available library counts.
- **`library_pick`** (`max_minutes`, optional `limit` 1 to 3, default 3) picks up to
  three watchable items from your Jellyfin library, in this order: unfinished items
  to resume, Next Up episodes, then never-watched movies/videos. Resume and Next Up
  items must fit in their *remaining* time and unwatched items in their full runtime,
  strictly within `max_minutes`; items with unknown runtime are never picked. Each
  pick carries a one-line reason drawn only from Jellyfin's watch state and metadata.
  It only reads the library: it does **not** start anything on the TV.
- **`tv_play`** (`item_id`) validates that the exact Jellyfin item is a directly
  playable local MP4/M4V file (H.264 video up to 1080p, AAC/MP3 or no audio), mints
  an expiring single-item LAN capability URL (`/cast/<token>/video.mp4`), launches
  the Chromecast Default Media Receiver (`CC1AD845`) at `chromecast_host`, and waits
  until the receiver reports a fresh `PLAYING` status for that exact capability URL.
  If that exact item is already `PAUSED` on the receiver with a valid capability,
  calling `tv_play` with the same `item_id` resumes the session.
- **`tv_pause`** (no arguments) pauses the active Hermes Screen media session on the
  configured Chromecast and verifies that the receiver transitions to `PAUSED` on
  the same capability URL and media session.

Failures return a short reason and a hint. A failed Jellyfin lookup is reported as
an error or a partial result, never as "nothing to watch".

The Jellyfin client also implements library search and Roku `/Sessions` playback
verification (`verify_playback`); those methods are **not** exposed as tools yet.
`library_status`, `library_pick`, `JellyfinClient.get_cast_source`, authenticated
`HEAD`/byte-range streaming, and `JellyfinClient.verify_playback` against an active
Roku 3 (`192.168.0.104`) playback session have been verified against the live
Jellyfin `12.2.0` server (`terebi`). Direct Google Cast play and pause were verified
on the user's Chromecast Gen 2 (`192.168.0.134`) in the pre-integration hardware
proof; live `tv_play` / `tv_pause` through the integrated relay awaits the Chromecast
being powered on and the ZimaOS host forwarder (`192.168.0.126:8765`) being active.
Programmatic Roku control, TV/CEC wake, Telegram pick/play/pause, `/watch`, YouTube,
and Friday voting are not included in this slice.

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
server must have exactly one enabled user. For Chromecast playback (`tv_play` /
`tv_pause`), also set `chromecast_host`, `cast_media_base_url`, and
`cast_relay_bind`. Settings and secrets are read through Hermes on every tool call;
the plugin does not read `.env` files.

Roku settings are not part of the public configuration because Roku control is not
implemented.

## Version compatibility

- Declared Hermes floor: `requires_hermes: ">=0.22.0"` (in both `plugin.yaml` and,
  later, the catalog entry).
- The compatible source floor was checked against released Hermes **v0.22.0**
  (`e06df9c2eae6901f4c88f464e0ae6e753c0428b8`): official doctor, isolated
  validate, mocked tool smoke (`library_status`, `library_pick`, `tv_play`,
  `tv_pause`), and live Jellyfin 12.2.0 preflight passed.
- The installed ZimaOS Hermes is **v0.16.0**, below this plugin's declared
  minimum; testing uses a separate v0.22.0 runtime without upgrading that
  installation.
- Jellyfin requests follow the upstream **12.4.0 OpenAPI** and have been verified
  live against **Jellyfin 12.2.0** (`terebi`) for `library_status`,
  `library_pick(max_minutes=20)`, `get_cast_source`, authenticated `HEAD`/`Range`
  streaming, and Roku 3 `/Sessions` + `verify_playback`.
- Python 3.11+; production dependencies are `httpx>=0.27,<1` and
  `pychromecast>=14,<15`.

See [integration evidence](docs/INTEGRATION.md) for exact commands and revisions.

## Supported configuration and secrets

Public `config_schema` entries (settings via `ctx.get_config`, secrets via
`agent.secret_scope.get_secret`, read on every call):

- `jellyfin_url` — string, required.
- `jellyfin_api_key` — secret, env `JELLYFIN_API_KEY`, read only through Hermes's
  secret scope (`agent.secret_scope.get_secret`). Never from `.env` or
  `os.environ`.
- `jellyfin_user` — string, optional (exact case-sensitive username or GUID).
- `chromecast_host` — string, required for `tv_play` / `tv_pause` (Chromecast LAN IP
  or hostname, e.g. `192.168.0.134`).
- `cast_media_base_url` — string, required for `tv_play` / `tv_pause` (LAN `http://host:port`
  URL the Chromecast fetches from, e.g. `http://192.168.0.126:8765`; never loopback
  or `0.0.0.0`).
- `cast_relay_bind` — string, required for `tv_play` / `tv_pause` (local `IP:port`
  for the temporary media relay listener, e.g. `192.168.0.126:8765` on host or
  `0.0.0.0:8765` inside a bridge-networked container with port `8765` published).

Non-text settings are rejected.

## Validation

Official Hermes v0.22.0 doctor (`4 tool(s), 0 hook(s)`), validate, mocked loader
smoke (`tests/hermes_smoke.py`), and live Jellyfin 12.2.0 preflight pass on the
integrated tree; **552 automated tests** and Ruff pass. `hermes plugins validate --install-deps`
passes with a visible `security scan — caution` (`bind_all_interfaces` on
`playback.py:77`, `plugin.yaml:50`, `relay.py:158`, `relay.py:166`) because
containerized setups can configure `cast_relay_bind` as `0.0.0.0:8765`. Details are
in [integration evidence](docs/INTEGRATION.md). Catalog rules distinguish a
validation failure from a caution finding requiring review.

## Publication gates (not yet met)

- No catalog PR has been opened and no commit is pinned for publication.
- Live `tv_play` and `tv_pause` through the integrated relay on the Chromecast Gen 2
  (`192.168.0.134`) remain to be run once the Chromecast is powered on and the
  temporary ZimaOS host forwarder (`192.168.0.126:8765` -> `172.23.0.2:8765`) is
  started (the pre-integration direct Cast proof on `192.168.0.134` and the live
  Jellyfin `12.2.0` preflight have both passed).
- Roku 3 programmatic control remains gated on Roku's third-party ECP restriction
  (and live `/Sessions` confirms `SupportsMediaControl: false` on `Jellyfin Roku` `3.2.4`).
- TV/CEC wake is out of scope and unverified.
- `library_pick` is verified against live Jellyfin 12.2.0 in the isolated Hermes
  v0.22.0 runtime, but not yet from Telegram; `/watch` is not built.

## Troubleshooting

- Missing settings: set `jellyfin_url`, `JELLYFIN_API_KEY`, and (for Chromecast)
  `chromecast_host`, `cast_media_base_url`, and `cast_relay_bind` in Hermes, then retry.
- Ambiguous user: set the exact username or GUID; the plugin never picks the first user.
- Authentication failure: check the API key and user permissions.
- Connection failure: check the Jellyfin URL, Chromecast IP, and LAN reachability.
- Chromecast stays `IDLE` on `tv_play`: verify `cast_media_base_url` uses the host's
  LAN IP reachable from the Chromecast and that `cast_relay_bind` port is forwarded
  to the Hermes runtime.

## Privacy and network use

- `library_status` and `library_pick` make HTTP requests only to the configured
  Jellyfin server with explicit 8-second timeouts (`follow_redirects=False`).
- `tv_play` and `tv_pause` connect directly to the configured `chromecast_host` on
  TCP port `8009` (no mDNS broadcast discovery is required when an IP is given) and
  run a local `ThreadingHTTPServer` bound to `cast_relay_bind` while a capability is
  active.
- `JELLYFIN_API_KEY` is never placed in capability URLs or sent to the Chromecast;
  the relay mints a single 256-bit random capability token (`/cast/<token>/video.mp4`)
  with a bounded TTL (15 minutes to 4 hours, `duration_s + 900s`), forwards `GET`/`HEAD`
  and byte-range requests to Jellyfin's static stream endpoint with `Authorization` in
  the upstream header only, redacts capability paths from logs, and revokes the
  capability + closes the listener on expiry or plugin unload (`ctx.on_unload`).
- Server/user names and library data returned in chat may be seen by your model provider.

## Contributing

Read [AGENTS.md](AGENTS.md), [SOUL.md](SOUL.md) and [the plan](docs/PLAN.md).
All automated HTTP and Cast tests use mocks/fakes; live hardware verification is
recorded in [docs/HARDWARE.md](docs/HARDWARE.md).

## License

MIT
