# End a game from Telegram

Say “Stop the game” or “Exit rock-paper-scissors” in the Hermes conversation that
started the game. `tv_game_stop` takes no arguments. The caller identity is injected
by Hermes; the model cannot supply another session or device to stop.

## Session authority and link revocation

Start stores the caller's exact session ID, viewer capability and configured Cast
address/app in profile-owned `ctx.state` (bounded to 64 caller records). The admin
key stays in Hermes secret scope. Start and stop are serialized with a bounded lock.

Stop calls `POST /v1/sessions/{exact_id}/end` with the admin header and the caller's
hashed request key. The service validates ownership and ends only that ID. Pairing
is revoked; player/viewer reads and actions return HTTP 410 `session_ended`.
No extra score is recorded. Ended sessions remain bounded expiry tombstones for
safe retries, evicted under capacity pressure. Starting again gets a fresh ID and
new credentials; an old end request cannot end that newer session.

The phone's existing terminal-error path stops every video track and inference,
clears saved pairing and shows **Game ended**. New pairing fragments reload a reused
phone tab through normal startup, without automatically turning the camera on.
The display stops polling/animation and pauses the soundtrack on revocation.

## Receiver ownership and closure evidence

Reuse the existing direct-IP GameCastTransport/PyChromecastSession adapter. Start
normally disconnects its sender, so stop makes a bounded connection using the same
adapter. No discovery, media STOP, application launch, or generic platform STOP.

The custom namespace receives the same four-field envelope as the launch, with
`type: END_SESSION`, exact `session_id`, read-only `display_token`, and fresh
`request_id`. No pairing or admin credential crosses Cast. The receiver compares
its current session and capability, then makes a bounded same-origin read to verify
the service has already revoked that session (410 ended/expired or 404 missing).
A read-only capability cannot end a live game. After the asynchronous check it
checks its generation again: a newer SHOW_SESSION wins. Only then does it stop
its own renderer/music and call CAF `context.stop()`.

SESSION_ENDING is not success evidence. The sender requests fresh platform status
and requires the artwork receiver **E8C28D3C** before returning `tv_verified: true`
with `receiver_backdrop`. If another app or newer game is present, it is left alone
and reported as such. If the service ended but closure cannot be verified, return
`ok: false`, `reason: game_ended_tv_unverified`, `game_ended: true`. Retrying an
unverified close is safe; a completed stop returns already_ended and does not touch
current TV playback. An API outage never authorizes stopping a receiver.

## Checks and live acceptance

Automated: 943 Python tests; 73 camera tests; 27 display/receiver tests; camera asset
checksum build; Ruff; Hermes v0.22.0 doctor (12 tools/0 hooks), catalog validation,
and official dispatcher start -> stop -> repeat smoke. The optional browser
fixture checks Game ended, an ended synthetic video track, stopped inference,
cleared storage and fresh pairing. These are not physical iPhone or TV results.

The practice button was confirmed working by the user on real iPhone Safari.
The new stop feature is UNVERIFIED LIVE until the matching backend/receiver build
is deployed and the isolated @terebitvbot loads this commit. No merge authorized.

1. Keep the tunnel running; deploy the provided source archive with the usual
   `games/deploy/host.sh build` and recreate only the games container. Old sessions
   expire on container restart. The manager reloads the same plugin source in the
   isolated gateway; the production bot is untouched.
2. Send /new once, then ask for rock-paper-scissors. Pair the iPhone and start a
   camera round with Mac mirroring off. Keep this Telegram conversation for stop.
3. Send “Stop the game”. Record bot game_ended and receiver evidence, the user's
   observation of rotating artwork, music silence and iPhone camera indicator off.
4. Send the stop again: it must leave TV playback alone. Start a fresh game and
   pair its new link. Record new-session/pairing evidence separately.

Existing catalog cautions stay visible: LAN media relay all-interface bind,
generated MediaPipe loader proc_access, and tunnel compose service.
