# Terebi Games v1: player camera page (`/play/`)

Vanilla HTML/CSS/ES-module page for one-player rock-paper-scissors against Hermes,
following `docs/RPS_CONTRACT.md` (manager-owned). The server owns phases, the
locked Hermes move and the score. This page only:

- pairs once from `/play/#pair=TOKEN` (`POST /v1/pair`), strips the fragment, and
  keeps `{session_id, player_token}` in `sessionStorage` (a hash of the redeemed pair
  token is kept so reopening the same link does not POST again);
- polls `GET /v1/sessions/{id}` every 400 ms with no overlap, a 4 s timeout and
  exponential backoff (cap 5 s); stops on 401/404/410 and on expiry;
- derives the countdown from `server_time_ms` + a `performance.now()` anchor (lowest
  round-trip of the last 8 samples), never from the phone wall clock;
- at the shared countdown end (+450 ms settle) decides once per `round_id` from the
  frames in `[end-400 ms, end+450 ms]` and sends `{round_id, move}` to `/move`;
- on no hand / low confidence / unstable, shows a Retry prompt and sends nothing;
- `Retry` → `POST /retry {round_id}`; `Next round`/`Start round` → `POST /next {round_id}`;
- labelled tap fallback → `POST /tap {round_id, move}`, enabled only from Shoot until
  `accept_until_ms`, with or without the camera.

Nothing but the move string leaves the phone: no frames, landmarks, confidence,
images, audio, telemetry or third-party requests.

## Build

```bash
cd games/camera
npm ci && npm run build   # -> dist/index.html + relative assets (~30 MB)
npm test                  # node:test, no browser, mocked media
```

The build verifies sha256 of every vendored MediaPipe file against
`assets.manifest.json`, downloads the pinned gesture model once (verified size and
sha256, cached in `.cache/`), and fails on any mismatch. For an offline build set
`TEREBI_GESTURE_MODEL=/path/to/gesture_recognizer.task` (still checksum-verified).
`dist/`, `.cache/` and `node_modules/` are git-ignored.

## Serving notes for the manager

- Serve `dist/` at `/play/` (the page uses only `./` relative URLs) on the same
  origin as `/v1/...`. HTTPS is required for the camera on iPhone Safari.
- MIME types: `.js` → `text/javascript`, `.wasm` → `application/wasm`, `.task` →
  `application/octet-stream`, `.css` → `text/css`.
- If you add a CSP: `script-src 'self' 'wasm-unsafe-eval'`, `connect-src 'self'`,
  `media-src 'self' blob:`, `worker-src 'self' blob:`.
  MediaPipe loads `vendor/wasm/vision_wasm_*_internal.js` via a same-origin
  `<script>` tag.
- Files: `index.html`, `styles.css`, `main.js`, `lib/*.js`, `vendor/vision_bundle.js`,
  `vendor/wasm/vision_wasm_internal.{js,wasm}`,
  `vendor/wasm/vision_wasm_nosimd_internal.{js,wasm}`,
  `models/gesture_recognizer.task`, `vendor/NOTICE.txt`, `build-manifest.json`.

## Asset provenance

| Asset | Pin | Source | License |
|---|---|---|---|
| `@mediapipe/tasks-vision` | 0.10.35, lockfile sha512 integrity, per-file sha256 in manifest | npm registry | Apache-2.0 |
| `gesture_recognizer.task` | float16 v1, 8,373,440 bytes, sha256 `97952348…2b0482` | `storage.googleapis.com/mediapipe-models/...` | **UNVERIFIED** (model card text extracted; no explicit license grant found; see manifest) |

Why 0.10.35 rather than the newest version: `@mediapipe/tasks-vision` 1.0.0 and later
(checked 1.0.0 and 1.2.2 on 2026-11-11) contain a usage logger that POSTs to
`odml.pa.googleapis.com/v1/log`. 0.10.35 has no such endpoint, which keeps the
no-telemetry rule.

## Known limits

- Tested only with mocked `getUserMedia`, mocked MediaPipe and fake timers. The real
  iPhone Safari camera, the real model accuracy/frame rate and the Den TV mirror are
  not tested here. That acceptance belongs to the manager and the user.
- MediaPipe uses the CPU delegate for predictability on iOS. Frame rate on older
  iPhones may be low (~8–15 fps); the decision needs only 3 confident frames.
- iOS Safari: needs HTTPS. A denied permission is remembered per site and must be
  changed in Safari's aA › Website Settings menu, so the page never re-prompts on its
  own. Background tabs lose the camera, so the page stops it when hidden.
- Gesture labels are the MediaPipe canned set. `Victory` (two fingers) is scissors.
  Other gestures count as unclear.


Temporary practice: camera start now shows landmarks, category/confidence and a
three-shape checklist before enabling camera rounds. No-hand, low-confidence,
loading stage, inference/model error and stale predictions have separate local
status. Practice sends no moves. After practice, the existing Shoot window is
shown as local sample counts; Retry remains mandatory for uncertain decisions.
See `docs/GAMES_RPS.md` for real-iPhone acceptance and deployment steps.
