# Hermes Screen

A Jellyfin-first plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent).
Work in progress for the November 2026 Hermes Agent Plugin Hackathon.

## Implemented today

Seven tools are registered:

- **`library_status`** checks your configured Jellyfin server, resolves a user, and
  returns the server name/version and available library counts.
- **`library_pick`** (`max_minutes`, optional `limit` 1 to 3, default 3) picks up to
  three watchable items from your Jellyfin library, in this order: unfinished items
  to resume, Next Up episodes, then never-watched movies/videos. Resume and Next Up
  items must fit in their *remaining* time and unwatched items in their full runtime,
  strictly within `max_minutes`; items with unknown runtime are never picked. Each
  pick carries a one-line reason drawn only from Jellyfin's watch state and metadata.
  It only reads the library: it does **not** start anything on the TV.
- **`tv_play`** (`item_id`, optional `media_source_id`, `start_time_s`) validates that the exact Jellyfin item is a directly
  playable local MP4/M4V file (H.264 video up to 1080p, AAC/MP3 or no audio), mints
  an expiring single-item LAN capability URL (`/cast/<token>/video.mp4`), launches
  the Chromecast Default Media Receiver (`CC1AD845`) at `chromecast_host`, and waits
  until the receiver reports a fresh `PLAYING` status for that exact capability URL.
  If that exact item is already `PAUSED` on the receiver with a valid capability,
  calling `tv_play` with the same `item_id` resumes the session.
- **`tv_pause`** (no arguments) pauses the active Hermes Screen media session on the
  configured Chromecast and verifies that the receiver transitions to `PAUSED` on
  the same capability URL and media session.

### Play rock-paper-scissors with Hermes

Say “Let's play rock-paper-scissors.” Hermes returns an expiring phone pairing
link and a display link. Open the camera page in iPhone Safari; mirror the display
from Mac Chrome to Den TV. Hold a fist, open palm, or V through the shared
countdown and the phone submits the recognized move automatically. Images stay
on the phone. Retry unclear gestures without changing the score; tap buttons are
a separately labelled fallback.

This optional service runs separately on ZimaOS and requires trusted HTTPS.
Configure `games_service_url` plus the Hermes secret `TEREBI_GAMES_API_KEY`.
See [deployment, pairing and mirroring instructions](docs/GAMES_RPS.md).
The prototype includes local camera/round tests; real iPhone Safari, Den TV display
and three-camera-round acceptance are still pending. Manual Chrome mirroring is
the selected TV path; automatic Custom Receiver launching is not configured.

### Describe a saved scene

Save a scene description with a timestamp verified against your exact Jellyfin
edition, then ask for it in your own words. For example, a saved description
“Bunny wakes up and comes out of his burrow” can match “Play the part where the
rabbit gets up and goes outside.” Hermes looks up local descriptions and aliases,
then uses the existing exact-source timestamp playback path. It reports the saved
scene and the receiver-confirmed start position.

Use `library_scene_save` with `item_id`, `media_source_id`, `label`, verified
`start_time_s`, and `description`. Optional `aliases` teach additional phrasings;
optional `end_time_s` is metadata and does not stop playback. Records stay in
profile-local marker state, separately from the movie file. Existing label-only
markers remain available and are not silently treated as scene descriptions.

For requests in the user's own words, Hermes calls `library_scene_find` with
`description`, rather than the subtitle `query` parameter. A clear match returns
one candidate; ambiguous results require a user choice. An unmatched description
offers an explicit timestamp and starts nothing. Lookup itself never starts
playback. Choices are edition- and session-bound and expire after 15 minutes.
Changed scene records or editions require a fresh lookup before playback.

Matching uses a small local phrase/synonym vocabulary and saved aliases. It has no
embedding model, subtitle indexing, or video/frame analysis in this path. Some
paraphrases will not match; it does not understand arbitrary visual scenes.
The planned three-scene Big Buck Bunny demo is **not yet verified live**: its
exact-copy action-start timestamps are still awaiting inspection or user input.
See [demo record status](docs/BBB_SCENE_DEMO.md).

### Play a scene from your edition

Ask Hermes: “Find the line ‘keep the lamp burning’ in Lighthouse,” then choose
one of the returned timestamps and ask to play it. `library_scene_find` resolves
movie and edition choices, searches that source's text subtitle track, and shows
caption evidence with original timestamps. Multiple matches require your choice.
Exact and approximate lexical matches are labelled; semantic ranking is disabled
until a local embedding model is approved. It cannot recognize an uncaptioned
visual scene.

For those scenes, supply a timestamp or save a manual marker: “Save one-minute
test scene at 01:00 in BigBuckBunny_320x180.” `library_scene_save` stores the marker
for the selected edition locally. Later ask: “Play one-minute test scene from
BigBuckBunny_320x180.” `tv_scene_play` consumes the selected candidate, starts or
seeks the exact source, and confirms the receiver is PLAYING near its timestamp.
`tv_pause` confirms pause afterward. Ordinary play without a timestamp keeps its
existing resume behavior; an explicit timestamp seeks and starts playing.

A subtitle index refreshes when its source, track or fetched text changes. Subtitle
tracks and indexes stay in local profile state; only matching excerpts are returned
in chat and may be seen by your model provider. Saved markers are user evidence,
not generated scene descriptions. Changed editions invalidate saved markers.
Pending scene choices expire after 15 minutes and belong to the requesting
conversation (or trusted Hermes session on v0.22.0; resetting the session requires
a fresh lookup). Playback rechecks the edition and caption evidence before acting.

The offset must be finite, nonnegative, and below the selected source's runtime.
The receiver's measured position must be within 3 seconds before the requested
point or 3 seconds plus elapsed playback after it. A loaded movie at the wrong
position is reported as unverified. Unsupported video formats still require a
separate transcoding solution; this slice adds none.

Failures return a short reason and a hint. A failed Jellyfin lookup is reported as
an error or a partial result, never as "nothing to watch".

The Jellyfin client also implements library search and Roku `/Sessions` playback
verification (`verify_playback`); those methods are **not** exposed as tools yet.
`library_status`, `library_pick`, `tv_play`, `tv_pause`, `JellyfinClient.get_cast_source`,
authenticated `HEAD`/byte-range streaming, and `JellyfinClient.verify_playback`
against an active Roku 3 (`192.168.0.104`) playback session have been verified
live against the Jellyfin `12.2.0` server (`terebi`) and the user's Chromecast
Gen 2 (`192.168.0.134`) in the isolated Hermes `v0.22.0` runtime.
The base Telegram pick/play/pause flow is verified. Programmatic Roku control,
TV/CEC wake, `/watch`, YouTube,
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
  `tv_pause`), and live Jellyfin 12.2.0 + Chromecast Gen 2 `tv_play` / `tv_pause`
  acceptance passed.
- The installed ZimaOS Hermes is **v0.16.0**, below this plugin's declared
  minimum; testing uses a separate v0.22.0 runtime without upgrading that
  installation.
- Jellyfin requests follow the upstream **12.4.0 OpenAPI** and have been verified
  live against **Jellyfin 12.2.0** (`terebi`) for `library_status`,
  `library_pick(max_minutes=20)`, `tv_play`, `tv_pause`, `get_cast_source`,
  authenticated `HEAD`/`Range` streaming, and Roku 3 `/Sessions` + `verify_playback`.
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

Official Hermes v0.22.0 doctor (`7 tool(s), 0 hook(s)`), validate, mocked loader
smoke (`tests/hermes_smoke.py`), and live Jellyfin 12.2.0 + Chromecast Gen 2
`tv_play` / `tv_pause` acceptance pass on the integrated tree; **722 automated tests**
and Ruff pass. `hermes plugins validate --install-deps` passes with a visible
`security scan — caution` (`bind_all_interfaces` on `playback.py:77`,
`plugin.yaml:50`, `relay.py:158`, `relay.py:166`) because containerized setups can
configure `cast_relay_bind` as `0.0.0.0:8765`. Details are in
[integration evidence](docs/INTEGRATION.md). Catalog rules distinguish a
validation failure from a caution finding requiring review.

## Publication gates (not yet met)

- No catalog PR has been opened and no commit is pinned for publication.
- Live `tv_play` and `tv_pause` through the integrated relay passed on Chromecast
  Gen 2 (`192.168.0.134`) from the isolated Hermes `v0.22.0` runtime via the
  temporary ZimaOS host forwarder (`192.168.0.126:8765` -> `172.23.0.2:8765`),
  while the installed ZimaOS Hermes container remains on `v0.16.0` (below
  `requires_hermes: ">=0.22.0"`).
- Roku 3 programmatic control remains gated on Roku's third-party ECP restriction
  (and live `/Sessions` confirms `SupportsMediaControl: false` on `Jellyfin Roku` `3.2.4`).
- TV/CEC wake is out of scope and unverified.
- `library_pick`, `tv_play`, and `tv_pause` are verified from Telegram on the base
  commit. Scene marker playback through Telegram is verified at 60.0 seconds, followed
  by receiver-confirmed pause at 73.1 seconds;
  `/watch` is not built.

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


### Direct Chromecast game launch (registered Custom Receiver)

Configure `games_receiver_app_id` with a Google Cast Custom Receiver ID and use
the existing `chromecast_host`. Deploy the game service's `/receiver/` page and
register that trusted HTTPS URL in Google's Console. Unpublished tests require
registering the Chromecast as a test device. See [setup and acceptance steps](docs/GAMES_CAST.md).

Hermes launches the game and sends only the session's read-only display capability.
It reports the TV ready only after the receiver acknowledges rendering the same
session. The iPhone pairing link is still returned in Telegram. Failed or
unconfigured launches retain the manual Chrome display link. Starting a game
replaces the current Chromecast app; TV wake and HDMI switching are separately
tested device behavior, not implied by receiver readiness.
