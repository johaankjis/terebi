# Fresh-device setup

One path from a fresh Hermes installation and your own Chromecast to everything
Hermes Screen does today: Jellyfin movies, saved scenes, YouTube, and the
rock-paper-scissors game. Placeholders look like `<LIKE_THIS>` — never paste real
credentials into chat, files or the Google Console beyond what each step asks for.

**Verification legend**

- **[Hardware]** — verified by this project on real devices: Jellyfin 12.2.0,
  Chromecast Gen 2 (firmware 1.56), iPhone Safari, Telegram gateway.
- **[Mocked/browser]** — verified in automated tests or a desktop browser only.
  Expect the first run on your devices to be the real test.

Everything is configured through Hermes: settings via `config_schema`, secrets
via Hermes secret settings (the plugin reads them with
`agent.secret_scope.get_secret` on every call and never reads `.env` files).

---

## Part 1 — Install the plugin

You need: a Hermes Agent installation (`>=0.22.0`; check with `hermes --version`),
Python 3.11+, and git.

1. Clone the repo and check out the pinned commit:

   ```sh
   git clone https://github.com/johaankjis/terebi.git
   cd terebi
   git checkout <PUBLISHED_40_CHAR_SHA>
   ```

2. Point Hermes at the checkout directory (native directory plugin: `plugin.yaml`
   and `__init__.py` are at the repo root):

   ```sh
   hermes plugins add /path/to/terebi
   hermes plugins doctor /path/to/terebi --ci
   ```

   Doctor should report the manifest and **12 tool(s), 0 hook(s)**:
   `library_status`, `library_pick`, `tv_play`, `tv_pause`,
   `library_scene_find`, `library_scene_save`, `tv_scene_play`,
   `tv_game_start`, `tv_game_stop`, `tv_youtube_play`, `tv_youtube_pause`,
   `library_youtube_search`.

3. Run the test suite once (optional but recommended):

   ```sh
   pip install -e '.[dev]'
   pytest -q              # ~900 tests
   ruff check .
   ```

Installing by catalog name (`hermes plugins install hermes-screen`) becomes
available **after** the catalog entry is accepted; until then the git checkout
above is the only path.

**Smoke test:** `hermes plugins doctor /path/to/terebi --ci` exits 0.
**Troubleshooting:** doctor reports a Hermes-version mismatch → your Hermes is
below `0.22.0`; upgrade Hermes. Tool count differs → you checked out a branch or
an older commit; re-run `git checkout <PUBLISHED_40_CHAR_SHA>`.

## Part 2 — Jellyfin movies on your Chromecast

You need: your Jellyfin server URL, an API key (Jellyfin Dashboard → API Keys),
the LAN IP of your Chromecast, and the LAN IP of the machine running Hermes.

In Hermes plugin settings (placeholders everywhere):

| Setting | Example placeholder | Meaning |
|---|---|---|
| `jellyfin_url` | `http://<JELLYFIN_LAN_IP>:8096` | Your Jellyfin server, including any base path |
| `jellyfin_api_key` | secret | Jellyfin API key — Hermes secret settings only |
| `jellyfin_user` | `<JELLYFIN_USERNAME>` | Optional; exact username or GUID. Omit only if the server has exactly one enabled user |
| `chromecast_host` | `<CHROMECAST_LAN_IP>` | The Chromecast that plays (port 8009, direct connection, no discovery) |
| `cast_media_base_url` | `http://<HERMES_HOST_LAN_IP>:8765` | `http://IP:port` the **Chromecast** can reach; no path, no loopback |
| `cast_relay_bind` | `0.0.0.0:8765` or `<HERMES_HOST_IP>:8765` | Where the temporary media link listens |

**Docker port forwarding, explained.** While something plays, the plugin serves
the movie to the Chromecast from a short-lived local HTTP listener (an expiring
random capability URL — the Jellyfin key is never sent to the TV). If Hermes
runs in a bridge-networked Docker container, that listener is inside the
container: set `cast_relay_bind: 0.0.0.0:8765` and publish the port
(`-p 8765:8765`), then point `cast_media_base_url` at the **host's LAN IP**. If
Hermes runs on the host directly, use the host IP in both settings. The
Chromecast must be able to reach `cast_media_base_url` — test with:
`curl -I http://<HERMES_HOST_LAN_IP>:8765/` from any LAN device (connection
refused with nothing playing is expected).

**Smoke test [Hardware]**: in Telegram (or any Hermes surface), say
**"What can I watch?"** — you get library-backed picks — then **"Play the first
one on the TV."** The tool replies only after the receiver reports `PLAYING` for
that exact item; confirm on screen. Then say **"pause"** and confirm the pause.

**Troubleshooting:** Chromecast stays `IDLE`/`app_opened` → the TV cannot reach
`cast_media_base_url` (wrong host IP or unpublished container port). Ambiguous
user error → set exact `jellyfin_user`. Items report "unsupported format" →
this plugin plays local MP4/M4V (H.264, AAC/MP3) only; it never transcodes.

## Part 3 — Saved scenes on your own editions

Save a timestamp against your exact edition, then ask in your own words:

1. **"Save a scene at 3:05 in <MOVIE_NAME> called bullies attack."**
   `library_scene_save` records label, description and verified timestamp
   locally (profile state, never inside the movie file).
2. **"Play the part where the bully attacks."** `library_scene_find` matches
   saved descriptions/aliases with a small local phrase vocabulary, then
   `tv_scene_play` starts (or seeks) the exact source and confirms the
   receiver's measured position near the timestamp.
3. Ambiguous matches ask you to choose; choices are session-bound and expire in
   15 minutes. No match → nothing plays; offer a timestamp.

Subtitle search ("Find the line 'keep the lamp burning' in <MOVIE_NAME>") uses
your edition's own subtitle tracks when present.

**Smoke test [Hardware]**: save one marker on your own movie, play it back with
a paraphrase, confirm the TV seeks to the right moment, then **"pause"**.
**Troubleshooting:** "unmatched" → save an `alias` phrasing you actually use;
paraphrase matching is intentionally small and local, not a semantic model.

## Part 4 — YouTube on the TV

Direct links need no key: **"Play https://youtu.be/<VIDEO_ID> on TV."**
`tv_youtube_play` launches YouTube on the configured Chromecast and reports
success only after fresh receiver evidence shows the exact video `PLAYING`.
`app_opened` is a distinct, honest result — the app opened but playback was not
confirmed (check the TV for ads, sign-in, or region blocks). **"pause"** pauses
the verified video/session only.

Optional title search: enable **YouTube Data API v3** in your Google Cloud
project, create an API key restricted to that API, and store it as
`YOUTUBE_API_KEY` in Hermes secret settings. Then **"Search YouTube for
<A_TITLE>."** returns up to five titles/channels to choose from; a choice plays.
Without the key, direct links still work.

**Smoke test [Hardware]**: link play + on-screen confirm + pause; if the key is
configured, one title search and selection.
**Troubleshooting:** `unavailable` → the video is private/region-blocked;
playlists and timestamp offsets are not supported. Search errors → key
restriction/quota; direct links never need the key.

## Part 5 — The rock-paper-scissors game service

This is a **standalone Docker Compose service** you run on your own always-on
Linux host (NAS, mini PC). It serves the phone camera page, the TV display and a
small game API. Camera frames never leave the phone.

You need: Docker + Docker Compose on the host, and a **trusted HTTPS origin**
for the service (the phone camera requires a secure context). The stock deploy
uses a Cloudflare Quick Tunnel — no account, random hostname that changes on
restart. Your own domain + reverse proxy works too.

1. Download the repo at `<PUBLISHED_40_CHAR_SHA>` and upload it to the host as
   `/DATA/AppData/terebi-games/source.tar.gz` (any path works), then in the
   host's terminal:

   ```sh
   mkdir -p /DATA/AppData/terebi-games/src
   cd /DATA/AppData/terebi-games/src
   tar -xzf ../source.tar.gz
   sh games/deploy/host.sh build     # builds the image; needs internet (pinned npm/Python bases)
   sh games/deploy/host.sh init      # creates private/game.json with a random admin token; never printed
   sh games/deploy/host.sh start     # starts games + tunnel containers
   sh games/deploy/host.sh status    # shows the tunnel's public hostname
   ```

2. Give the service its public origin (restarts only the game container):

   ```sh
   sh games/deploy/host.sh set-url https://<YOUR_TUNNEL_HOSTNAME>.trycloudflare.com
   ```

   If the tunnel restarts with a new hostname, repeat `set-url` (and update your
   receiver URL in Part 6).

3. In Hermes: set `games_service_url` to that HTTPS origin and put the game's
   admin token (from `private/game.json` on the host — read it there, never send
   it in chat) into the `TEREBI_GAMES_API_KEY` **secret** in Hermes secret
   settings.

**Optional background music.** The game is silent by default and fully playable
without audio. To add your own track: place an MP3 at
`games/display/music.mp3` in your deployed source tree before (or after) step 1,
then rebuild (`sh games/deploy/host.sh build` and `up -d --no-deps games`).
Use audio you own or that is licensed for this use — nothing is bundled with
the plugin. Removing the file and rebuilding returns the game to silent.

**Play [Hardware]**: in Telegram say **"Let's play rock-paper-scissors."** You
get a single-use phone pairing link (valid 3 minutes) plus a display path.
Open the pairing link in iPhone Safari, allow **Camera** (microphone is never
requested), complete **practice** (rock / paper / scissors checkmarks), then
**"Practice complete — use camera in rounds"**, and **Start round** — reveal
your gesture on **Shoot** and hold it briefly. Unclear results offer **Retry**
without changing the score; the on-screen **Tap-to-play** panel is an explicitly
labelled fallback recorded as tap rounds. Say **"Stop the game"** in the same
conversation when done: links are revoked, the phone releases the camera and the
TV receiver exits.

**Smoke test [Hardware]**: one full practice + one camera round + one stop, with
the TV showing Waiting → Ready → reveal → Game ended.
**Troubleshooting:** pairing page won't load → the tunnel hostname changed;
re-run `set-url`. "not_configured" from game tools → `games_service_url` or the
`TEREBI_GAMES_API_KEY` secret is missing. Camera blocked → Safari website
settings must explicitly allow camera for the pairing origin.

## Part 6 — Your own Custom Receiver (optional; manual mirroring without it)

By default the game returns a **manual display link** you open in desktop Chrome
and cast to the TV (Chrome → Cast → Cast tab). To launch the game directly on
the Chromecast instead, register your own receiver with Google:

1. Register at `https://cast.google.com/publish/` (one-time US$5 fee, your
   Google account).
2. **Devices → Add New Device**: your Chromecast's serial number (the console
   can display it on the TV). Wait ~15 minutes, then power-cycle the Chromecast.
3. **Applications → Add New Application → Custom Receiver**, name it, and set
   the URL to `https://<YOUR_TUNNEL_HOSTNAME>/receiver/` — no tokens, no query.
   Leave relay casting and audio-only unchecked. Keep it **unpublished**
   (registered-device testing only). Copy the eight-character Application ID.
4. In Hermes, set `games_receiver_app_id` to that ID (keep `chromecast_host`
   from Part 2). When a game starts, the receiver is launched with only the
   session's read-only display capability, and the tool reports the TV as ready
   only after the receiver acknowledges rendering **that** session
   (`tv_verified: true`). Launch failure keeps the manual link as fallback.

The receiver page loads Google's CAF v3 SDK from `www.gstatic.com`; everything
else comes from your game origin. TV power-on and HDMI input switching are
device behavior the plugin does not control — switch the TV input if needed.

**Smoke test [Hardware]**: start a game with the receiver configured; the bot
reply should include `tv_verified: true` / receiver render evidence, and the TV
should show the game without any Mac involved. Restart the tunnel → update the
Console URL and `set-url`.
**Troubleshooting:** `app_opened`-style results or no render acknowledgement →
wrong URL in the Console, tunnel hostname changed, or the Chromecast is not
registered as a test device for your account. Manual mirroring always remains
available as the fallback.

---

## What runs where (disclosure summary)

- **Network calls:** your Jellyfin server (HTTP/HTTPS, explicit timeouts), the
  configured Chromecast (TCP 8009, Cast protocol), YouTube on the TV (served by
  YouTube itself), `www.gstatic.com` (CAF SDK, receiver only), your game service
  origin (game pages/API), and — only if you configure it — the YouTube Data
  API. Optional exposure via a Cloudflare Quick Tunnel for the phone/receiver
  HTTPS requirement. No telemetry; nothing reports usage anywhere.
- **Listeners/background:** the temporary movie relay binds only while
  something plays and is revoked on expiry/unload; the game service runs as its
  own two-container Compose project (loopback-published port + tunnel).
- **Local data:** scene markers, subtitle indexes and game session records stay
  in Hermes's per-profile plugin state and the game service's private config;
  nothing syncs anywhere.
- **Setup downloads:** the game image build pulls pinned base images and the
  npm runtime/model packages with checksum validation; the camera WASM/model
  assets are built at image build time from those pinned sources, never
  committed. No audio is bundled; background music is only what a user
  optionally provides at their own deployment (license responsibility is the
  user's).
- **Credentials:** only via Hermes (`config_schema` + secrets). The game admin
  token is generated on the host and read there; movie links use short-lived
  random capability tokens; game pairing is one-use with expiring capabilities.

See [SUBMISSION.md](SUBMISSION.md) for the exact verified-vs-mocked evidence
per feature and the catalog entry draft.
