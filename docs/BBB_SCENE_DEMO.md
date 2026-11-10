# Big Buck Bunny saved-description demo

Status: implementation complete; scene data and live acceptance blocked.
Base: open PR #4 at `3cc3c1e7748dbd043ac98eab201a0adced9e3a78`.
Manager checkout: `/home/node/.t3/worktrees/terebi/feat-bbb-scene-demo`.

Exact target edition: `BigBuckBunny_320x180`, Jellyfin item and media source
`e5d6c471a8a4ea26e00a3694f91bf8d1`. Last known edition fingerprint:
`0566d3557fd06c0d60fbfb9f9808291508c4c072105b8f9e5002e14ac2f5c7ad`.
Revalidate this fingerprint when saving and playing; do not assume a replacement
file has the same timings. The pre-existing 60-second test marker is unrelated
to these three scene actions and must remain intact.

| Candidate description | Start in exact copy | Verification |
|---|---|---|
| Bunny wakes up and comes out of his burrow | Pending | Not verified |
| The bullies attack the butterfly | Pending | Not verified |
| Bunny sets traps for the bullies | Pending | Not verified |

Manager inspection attempt: authenticated metadata request to the configured
Jellyfin returned HTTP 401, including after extracting the expected key format.
The private delivery file was removed. No media was downloaded, no scene action
was viewed, and no timestamps were guessed from another edition or test fixture.
The user has been asked for the three action-start times in this exact copy.
If a candidate is unclear, replace it only with a clearly verified moment and
record the replacement here. All times in unit tests are synthetic fixtures.

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
4. Try “Play the scene with the bullies” (ambiguous across the butterfly/trap
   scenes) and an unsupported action such as “Play the part where a car explodes.”
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
