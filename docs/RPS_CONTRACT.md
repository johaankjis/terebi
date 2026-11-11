# Terebi Games v1: session and camera contract

Manager base: `263c82629886bfdf45517e8583b94cffecea9888` (origin/main).
Manager checkout: `/home/node/.t3/worktrees/terebi/feat-hermes-games-rps`.
Only rock-paper-scissors, one player against Hermes. Existing movie/scene tools
remain intact. Manager owns Python service/API, Telegram tool, display, deployment
and live test. One Claude Code worker owns only `games/camera/**` (page, local
recognizer, build/asset manifest and focused JS tests). No shared edited files.

## Hosting and privacy

Single same-origin HTTPS site. Service lives on ZimaOS behind a proxy or a
temporary Cloudflare Quick Tunnel. Local development on localhost is supported.
Static player `/play/` serves `games/camera/dist/index.html`; `/play/<asset>` serves
other files under that dist directory. TV `/display/` is manager-owned. Player
and display fetch the SAME session from `/v1/...`; no separate client scores.
Use ordinary polling, not SSE (Quick Tunnel limitation). No third-party runtime
scripts, model downloads, telemetry, image uploads or audio capture. Build-time
model/WASM downloads must be pinned with provenance/checksums and served locally.
No frames, landmarks, confidence arrays or images in requests or logs. Camera
permission requires an explicit explained user click and `audio:false`.

Manual mirroring is selected: user has no Cast Custom Receiver ID or test-device
registration. Mac Chrome display tab -> Cast -> Den TV (Chromecast Gen 2). iPhone
Safari opens the paired camera page. Fullscreen display should offer a user-click
Fullscreen button and retain readable layout when fullscreen is unavailable.
Frutiger Aero style in code: bright sky, glossy buttons, translucent panels,
high-contrast large countdown and scores; reduced-motion support.

## Wire API (frozen before delegation)

JSON UTF-8, errors `{ok:false,reason,hint}` (400/401/404/409/410/413/429).
Fetch uses `cache:'no-store'`, bounded request timeouts, and same-origin URLs.
All session endpoints require `Authorization: Bearer <player_token>`; display
GET accepts its separate read-only token. Never put bearer tokens in query paths.
Do not log tokens. Static links deliver secrets in URL fragments; remove fragments
using history.replaceState after reading. A session expires after 30 minutes;
one-use pairing expires after 3 minutes. Only one player can redeem a pairing.

- Manager-only `POST /v1/sessions`, admin Bearer token, `{request_key:<stable
  opaque string>}`: idempotently returns session/pair/display URLs. Worker does
  not create sessions. Telegram creates and returns these links.
- Player arrives at `/play/#pair=<256-bit token>`. `POST /v1/pair` body
  `{pair_token:<token>}` -> `{ok:true,session_id,player_token,state}`. Persist
  session_id/player_token in sessionStorage for reloads; no repeated pairing.
- `GET /v1/sessions/{session_id}` -> `{ok:true,state:<below>}`. Poll every 400ms
  while visible, with no overlapping requests and conservative error backoff.
- `POST /v1/sessions/{session_id}/next` body `{round_id}`: starts the first round
  from `ready`, or allocates the next round from `next_round`. Returns state.
  Only these states accept it. Double/stale requests return 409, never two rounds.
- `POST /v1/sessions/{session_id}/move` body **only** `{round_id,move}` with move
  exactly `rock|paper|scissors`: submits camera classification. Tap fallback uses
  `/tap` with the SAME body; result metadata distinguishes camera vs tap.
- `POST /v1/sessions/{session_id}/retry` body `{round_id}`: allowed only in an
  unscored `countdown` after its deadline. Keeps logical round number, score and
  LOCKED Hermes move, assigns a fresh round_id, then starts another countdown.
  Old attempt IDs are stale. Retry click is not a shutter; inference is automatic
  at the next countdown end. No-hand/unclear classification sends NO move; player
  page shows retry prompt. Retry API does not require images/confidence.

State object (all fields present):
```
{session_id, revision, server_time_ms, expires_at_ms,
 phase: 'waiting_for_player'|'ready'|'countdown'|'reveal'|'score'|'next_round',
 round_id: string|null, round_number: integer,
 countdown_ends_at_ms: number|null, accept_until_ms: number|null,
 hermes_commitment: string|null,
 result: null|{round_id,player_move,hermes_move,outcome:'player'|'hermes'|'tie',
              input:'camera'|'tap',nonce:string},
 score:{player:integer,hermes:integer,ties:integer,rounds:integer}}
```
Time values are Unix epoch milliseconds. Derive countdown from server_time_ms
and countdown_ends_at_ms with a local monotonic clock anchor; periodically
resynchronize. Do not trust device wall-clock alone. Countdown is 3 seconds.
Move acceptance lasts 10 seconds after deadline; expired attempts must retry.
Do not resubmit automatically across round_id changes or after a successful move.

Transitions:
- Creation -> waiting_for_player (round_id null).
- Pairing -> ready (round 1 ID allocated, Hermes move chosen and locked).
- Next -> countdown; at deadline, UI shows Shoot and classifies automatically.
  Server remains countdown until a valid submission or retry; it never guesses.
- Valid move -> reveal, score updated atomically ONCE. Reveal lasts 1.5 seconds,
  then score for 1.5 seconds, then next_round. Both clients observe these states.
- Next from next_round allocates a fresh ID/number, locks a new Hermes move,
  starts countdown. Retry never changes the locked move or logical round number.

Only the server selects/scores. Commitment is SHA256 of
`session_id + ':' + round_number + ':' + hermes_move + ':' + nonce` (UTF-8).
Nonce is random, hidden with move until reveal, unchanged by retry. Neither
camera nor display receives Hermes move/nonce before submission. Transition and
submission locks serialize simultaneous duplicate requests. Client never sends
score or Hermes move. Duplicate/stale/early/late submissions are rejected.

## Camera page obligations

Explain on-device video use before permission; preview, hand guide and Stop camera
button always visible while active. Stop every MediaStreamTrack on Stop, pagehide,
visibility hidden, fatal capture error and session expiration. Recover safely from
permission denial, absent camera, busy camera, model failure and resume; no silent
permission re-request. Safari playsInline/muted video; trusted HTTPS required.
Use local on-device gesture model, e.g. MediaPipe GestureRecognizer with
Closed_Fist/Open_Palm/Victory. Bound confidence and require several stable recent
frames at countdown end. No hand/unclear -> retry prompt with score untouched.
Ignore stale inference promises/results for old rounds and cameras. Stop also
cancels pending automatic submission. Tap controls are clearly labelled fallback,
work without camera, and send via /tap only after countdown; never call it a
camera round. Next round button drives /next. Pair once, play repeatedly.

Worker tests: gesture mapping/stability/no hand, automatic countdown timing with
server clock offset, no stale/duplicate sends, Stop/leave track release, permission
and missing-camera failures, pairing reuse/expiry, and tap vs camera separation.
Use mocks honestly; real iPhone Safari/Den TV tests remain manager/user acceptance.
