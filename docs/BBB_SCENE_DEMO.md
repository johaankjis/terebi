# Big Buck Bunny saved-description demo

Status: live Telegram paraphrase → Den TV scene playback verified (2026-11-10).
Base: open PR #4 at `3cc3c1e7748dbd043ac98eab201a0adced9e3a78`.
Manager checkout: `/home/node/.t3/worktrees/terebi/feat-bbb-scene-demo`.

Exact target edition: `BigBuckBunny_320x180`, Jellyfin item and media source
`e5d6c471a8a4ea26e00a3694f91bf8d1`. Last known edition fingerprint:
`0566d3557fd06c0d60fbfb9f9808291508c4c072105b8f9e5002e14ac2f5c7ad`.
Revalidate this fingerprint when saving and playing; do not assume a replacement
file has the same timings. The pre-existing 60-second test marker is unrelated
to these three scene actions and must remain intact.

| Saved description (user-supplied) | Start in exact copy | Verification |
|---|---|---|
| Bunny comes out of his burrow. | 00:45 (45 s) | User-supplied for this copy; saved 2026-11-10 |
| The bullies attack the butterfly. | 03:05 (185 s) | User-supplied for this copy; saved 2026-11-10 |
| Bunny starts setting traps. | 04:04 (244 s) | User-supplied for this copy; saved 2026-11-10 |

Marker save (2026-11-10 21:19 UTC, pinned `cb4b69d`, isolated Hermes v0.22.0):
before saving, the only stored marker was the 60-second test marker, so nothing
was duplicated. The three user-supplied markers were saved through
`library_scene_save`; `library_scene_find` then returned exactly four markers
with the 60-second marker intact. No aliases were saved: earlier draft aliases
were not user-supplied, and one mirrored the planned paraphrase test. Evidence:
[bbb-scene-markers-20261110.json](evidence/bbb-scene-markers-20261110.json).

The earlier HTTP 401s came from the temporary acceptance bootstrap, which sent
`X-Emby-Token`. This Jellyfin 12.2.0 server rejects that header and accepts the
`Authorization: MediaBrowser ... Token=` header the plugin already uses. The
agent viewed no media and inferred no times.

After verification, save each description/start through `library_scene_save`
into the existing profile-owned `scene_markers_v1:<scope>` collection. Exact
item/source IDs, edition fingerprint, label, description, optional aliases and
optional end metadata live in the marker record. Do not alter the movie file or
seed production records from fixtures. A second save preserves an unchanged
marker's optional metadata; adding described records preserves old markers.

Live acceptance remains pending:

1. Verify the final plugin SHA and marker records in an isolated Hermes v0.22.0
   Telegram gateway, preserving the working demo checkout.
2. With the media forwarder reachable and Den TV on its Chromecast input, ask the
   user to describe one saved scene using different wording, no label/timestamp.
   Example: “Play the part where Bunny gets up and goes outside.”
3. Correlate tool result item/source to the single-item capability, then receiver
   PLAYING and measured position within the existing three-second-plus-elapsed
   tolerance. Reply with the scene and confirmed position. Verify pause as cleanup.
4. Try a vague request that could match more than one scene and an unsupported action such as “Play the part where a car explodes.”
   Verify requests return choice/no-match and issue no playback command. Do not
   select a candidate in the ambiguous case. Record receiver/tool audit evidence.
5. Release the media relay and confirm port closure before stopping forwarding.

This is saved-description matching, not subtitle-derived or generated scene
understanding. The earlier PR #4 manual-marker success does not establish this
paraphrase demo's live acceptance. One new draft PR will remain unmerged until
the user chooses to merge it.


Implementation review: Claude Code (`claudeAgent`, `claude-opus-5-5`) worked in
`/home/node/.t3/worktrees/terebi/t3-0179a8f5` from the exact PR #4 head. Worker
commit `7737eb222a9b8347b939b3fffda3eddf1fc2b84d` changed only the matcher and its
80 tests; manager reviewed and cherry-picked it as `b2a2573`. Manager wiring
adds 15 registered-tool tests and extends the official-loader/dispatcher smoke
to use a paraphrase, with synthetic timing and a fake receiver. These checks
are separate from the pending three-scene live acceptance.


Automated verification on **`cb4b69d73ec242cf8b76d673f2e8679fce46a8cb`**:

- Full suite: **817 passed**, including 80 pure matcher tests and 15 registered-tool
  description tests. Focused resolver/scene wiring subset: **122 passed**.
- Ruff lint/format and `git diff --check`: passed (50 Python files formatted).
- Official isolated Hermes v0.22.0 doctor: passed, 7 tools and 0 hooks.
- `validate --install-deps`: passed. Existing configurable LAN listener caution
  `bind_all_interfaces` remains visible; no suppression or new dependency.
- Real namespaced loader plus ToolRegistry dispatcher smoke: passed, local saved
  description paraphrase → session-bound choice → fake receiver seek/position →
  pause and cleanup. This is mocked media/receiver evidence, not live Telegram.
- Local logs: `/tmp/terebi-bbb-description-checks-3bltl0zq/{doctor,validate,smoke}.log`.

Live Telegram and Den TV evidence (2026-11-10 21:23–21:25 UTC, pinned `cb4b69d`):

- **Verified:** “Play the part where Bunny gets up and goes outside” matched the
  burrow marker (45 s) as the only candidate. The bot asked for confirmation; the
  user confirmed. Den TV reported PLAYING at 45.0 s, and the user confirmed the
  scene on screen.
- **Device-reported only:** pause. The receiver reported PAUSED at 56.1 s, and
  `tv_pause` verified it. The relay was released afterward. Not separately
  confirmed on screen.
- **Not verified live:** no-match requests that start no playback, and multi-candidate choices.
  Both are covered by unit tests only.

Evidence: [bbb-scene-live-telegram-20261110.json](evidence/bbb-scene-live-telegram-20261110.json). Keep the new PR draft; user owns merging.
