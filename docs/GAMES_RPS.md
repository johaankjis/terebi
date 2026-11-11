# Terebi Games v1: rock-paper-scissors

Ask Hermes “Let's play rock-paper-scissors.” It returns a three-minute, single-use
pairing link for your phone and a read-only display link for Mac Chrome. One
ZimaOS service owns the countdown, moves and score. Camera frames and landmarks
stay on the phone. No shutter button: hold rock, an open palm, or a V for scissors
at the end of the countdown. An unclear gesture offers Retry without scoring.
Tap-to-play is an explicitly labelled fallback and recorded as a tap round.

The interface uses CSS sky gradients, translucent panels and glossy buttons.
The TV display has a large countdown, moves, result and running score. Optional
Fullscreen requires a click. A session lasts 30 minutes; service restart ends it.
Only the three moves and round IDs are submitted. Score updates are serialized
and happen once per accepted round. Hermes's salted commitment is published
before the player submits; move and nonce are revealed afterward. Retry replaces
the attempt ID while keeping the same logical round and locked Hermes move.

## Chosen TV path and first live gate

Manual Mac Chrome tab mirroring to **Den TV, Chromecast Gen 2, 192.168.0.134**.
The user has no Custom Web Receiver app ID or registered test device. Google
requires both for unpublished Custom Receiver testing; the default media receiver
cannot load an arbitrary interactive HTML page. No Custom Receiver is shipped.

**Not yet verified:** Den TV showing this game and one live shared-state update.
This is the FIRST hardware gate after deployment: open the display link on the
Mac, mirror it, then pair the phone and confirm the TV changes from Waiting to
Ready. Remaining camera/three-round acceptance stays pending until this passes.

## Hosting choice and exposure

T3's probes found Caddy on host HTTP port 80; host TLS port 443 refused connection.
There is no HTTPS proxy config in this repository. The internal Caddy/host config
has not been inspected: this T3 container has no host shell or Docker socket.
User can provide the output of `docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'`
and `ss -lnt` in the ZimaOS terminal. Do not include environment variables/secrets.

The proposed prototype uses a Cloudflare Quick Tunnel: no account or domain,
random trusted `https://....trycloudflare.com` hostname, changes on each tunnel
restart, no uptime guarantee. It exposes only this game container's static pages,
local model/WASM assets and game API. Session creation needs the admin secret;
pairing is one-use/three-minutes and player/display tokens expire after 30 minutes.
The URL is public, not an access-control boundary. Cloudflare terminates HTTPS and
can see game requests/tokens, but camera images never leave the phone. It does not
expose Jellyfin, the ZimaOS dashboard, movie media or the Docker socket. No SSE:
clients poll with bounded timeouts. Stop the tunnel after testing.

## Run on ZimaOS (host-side commands)

T3 prepares and checks the source, camera assets and source archive. **T3 cannot
run these Docker commands on your host.** Download the source archive linked in
T3 and use ZimaOS Files to upload it as:
`/DATA/AppData/terebi-games-rps/source.tar.gz`.
Use a new dedicated directory; keep existing Terebi/movie deployments intact.

Run in the **ZimaOS web terminal** (Docker access required):

```sh
mkdir -p /DATA/AppData/terebi-games-rps/src
cd /DATA/AppData/terebi-games-rps/src
tar -xzf ../source.tar.gz
sh games/deploy/host.sh build
sh games/deploy/host.sh init
sh games/deploy/host.sh start
sh games/deploy/host.sh status
```

Build fetches the pinned npm runtime/model with checksum validation. Node/Python
base images and Cloudflare's utility image require Internet access. No account
is needed for Quick Tunnel. Config is generated with a random admin secret;
`init` preserves it on repeats, and does not print it. The service runs as UID
10001 with a read-only filesystem and no Linux capabilities. Only localhost
port 8766 is published on the host. Two containers join their own compose network.
Docker image build/run itself is **not verified from T3** (no Docker executable or
socket); direct Python/Node execution is checked here. Image tags can be pinned to
pulled digests after the host records them for the acceptance run.

Find the `https://....trycloudflare.com` hostname in tunnel status, then run:

```sh
sh games/deploy/host.sh set-url https://YOUR-HOSTNAME.trycloudflare.com
```

This restarts only the new game container. It invalidates any old sessions. Give
T3 that public hostname and the non-secret status output. Do not send game admin
keys in chat. If the tunnel restarts with a different hostname, repeat `set-url`.

## Hermes / Telegram configuration (T3 isolated test runtime)

Use official Hermes >=0.22.0. Configure `games_service_url` to the HTTPS origin
(or its reachable private service origin), and `TEREBI_GAMES_API_KEY` via Hermes's
secret scope to the generated `admin_token` in the private game config. Supply
any key to T3 only using the private secret card when requested. Keep the existing
production movie bot untouched; acceptance uses the isolated @terebitvbot gateway
and a final-SHA-pinned plugin copy. Do not run competing Telegram pollers.

The new `tv_game_start` tool takes no arguments and is scoped to the host-injected
Hermes conversation/session ID. Repeated calls reuse that active game. It returns
links; it does not claim automatic TV launch or verified TV state.

## Pair and mirror (after the manager confirms the bot is ready)

1. On Telegram say **“Let's play rock-paper-scissors.”**
2. On the Mac, open the display link in **Chrome**. Chrome menu → **Cast, save,
   and share → Cast…** → Sources **Cast tab** → **Den TV**. The Mac and Chromecast
   must be on the same LAN. Click the page's **Fullscreen** button (or use Chrome
   fullscreen if unavailable). Keep that tab active for the TV display.
3. On iPhone open the pairing link in **Safari** within three minutes. Confirm the
   TV changes **Waiting → Ready**. This establishes the first TV/state-update gate.
4. Read the camera explanation and tap **Start camera**. Allow **Camera** access.
   Microphone is never requested. Keep one hand fully in the preview and use good
   lighting. If denied, change Safari's **aA → Website Settings → Camera → Allow**,
   then explicitly press Start camera again. No camera permission is re-requested
   silently. Backgrounding Safari or leaving the page stops its camera.
5. Tap **Start round**. Hold the gesture through **3, 2, 1, Shoot**. At countdown end
   the phone automatically recognizes and sends a stable move. Use **Next round**
   to continue. If unclear/no hand, follow the prompt and press **Retry**; the
   shared countdown restarts with unchanged score and Hermes move.
6. For a temporary camera problem, use the clearly labelled **Tap-to-play** panel;
   evidence must call these tap rounds, not camera rounds.

Pairing once lasts across rounds/reloads in the same Safari tab. Expired sessions
require a new Telegram game. Display tokens cannot play moves. Stop/retry/next are
controlled only by the paired device.

## Acceptance evidence to capture

- Exact source SHA, Docker image IDs and public HTTPS origin; isolated gateway
  registration and Telegram response; actual iPhone model/iOS/Safari version.
- Den TV mirror shows Waiting → Ready from the SAME session's phone pairing.
- Three completed **camera** rounds with no shutter press. Correlate TV and phone
  states; exactly one `round_scored` event per round and total rounds 1, 2, 3.
- Remove the hand for a countdown: retry prompt, no score increment. Retry keeps
  Hermes commitment and logical round, changes attempt ID; then score only once.
- Tap **Stop camera**: preview stops, all tracks end and iPhone camera indicator
  turns off. No further automatic move can be sent. Re-start is explicit.
- Keep denied permission/missing camera/leave-page mock coverage distinct from
  any real device observation. Tap fallback must be labelled separately.

On the host, sanitized game events are available with:

```sh
sh games/deploy/host.sh evidence
```

Events contain session/attempt hashes, phases, round numbers, accepted moves and
scores; no bearer token, images or landmarks. Docker log rotation bounds storage.
Before sharing other outputs, omit game links/tokens and the private config.
After testing, release the camera and stop the tunnel/service:

```sh
sh games/deploy/host.sh stop
```

Private config remains for a repeat; active sessions are memory-only and expire
on shutdown. This prototype adds no trivia, voice, charades, Roku or multiplayer.


## Current verification checkpoint

Exact tested source: **`aee89f97acdcf8b7cd23efb1f1d32895c4a7767c`**.

- **852 Python tests passed**, including the complete existing movie/scene suite,
  RPS scoring combinations, concurrent submissions, retry invariants, expiry,
  capability roles, HTTP privacy/input boundaries and native Hermes game links.
- **59 JS tests passed**, mocked camera/recognizer/timers. Camera assets build with
  checksum verification; no real camera, iPhone accuracy or release observation
  is claimed from these tests. A three-round API simulation is also a unit test.
- Ruff lint/format, diff check, shell syntax, display JS syntax, compose YAML and
  local-only host port assertions pass. Docker build/run remains host-side pending.
- Official isolated Hermes v0.22.0 doctor passed (8 tools, 0 hooks); validation and
  real-loader/ToolRegistry dispatcher smoke passed. Cautions remain visible for
  configurable LAN bind, tunnel service, and generated MediaPipe WASM loader
  `/proc` helpers discovered in built/vendor dependencies. No scan suppression.
- The initial smoke command exposed an accidental extra positional argument in
  the test harness; it was fixed and the smoke rerun passed. An initial dependency
  preparation retry message cleared on the stable-source validation rerun.
- Logs: `/tmp/terebi-rps-final-f6wz5fx5/` (validation/smoke),
  `/tmp/terebi-rps-checks-cumx0bpr/doctor.log`.

The selected TV path is manual Mac Chrome mirroring, not yet verified on Den TV.
ZimaOS deployment, Telegram game start, trusted-HTTPS iPhone Safari capture,
three real camera rounds, missed-hand retry, and physical Stop-camera indicator
acceptance remain pending. No game-state update on the TV is claimed yet.
A temporary T3 LAN display-only spike can use the existing host port 8765 forwarder
for the first Waiting → Ready proof; camera acceptance requires the HTTPS host.

The pinned model binary is downloaded at build time; no model binary is committed.
The model card text was extracted, but contained no explicit license grant; its
manifest retains that provenance limitation for redistribution review.


Draft PR: https://github.com/johaankjis/terebi/pull/6 (leave unmerged).
The existing host:8765 → T3 forwarder returned HTTP 200 for the temporary game
`/health` probe on 2026-11-11. This proves LAN reachability only. The display-only
proof has a 20-minute lifetime and requires user mirroring/TV confirmation; it
cannot establish trusted-HTTPS camera acceptance or ZimaOS deployment.
