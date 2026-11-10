# Scene resolver and player handoff

Base: `8e978d71474029fdc2994a1d3dcd3156ebc52b45` (live Telegram/Cast demo).
The manager feature worktree preserves `/home/node/projects/terebi` on that base.

Every selected scene hands the player this JSON-compatible record:

```json
{
  "item_id": "32 lowercase hexadecimal characters",
  "media_source_id": "32 lowercase hexadecimal characters",
  "start_time_s": 60.0,
  "evidence": {
    "kind": "subtitle",
    "method": "exact",
    "track_index": 2,
    "language": "eng",
    "track_fingerprint": "sha256 of track and source identity/content",
    "cue_indices": [17, 18],
    "cue_start_s": 60.0,
    "cue_end_s": 65.5,
    "excerpt": "A short excerpt from the matching cues."
  }
}
```

IDs refer to one actual item and one media source belonging to it. Seconds are
finite numbers, never booleans, nonnegative and below that source's duration.
The player revalidates this before issuing Cast commands. Evidence does not
authorize a different edition. The resolver never plays a candidate automatically.

Subtitle evidence preserves original cue text, language and start/end times in
the local index; neighboring-cue windows add search context without rewriting
timestamps. Tool results expose only compact matching evidence, not whole tracks.
The index is scoped to the configured server/user/item/source/track and refreshed
when source metadata, track metadata or fetched content changes. No network model
or embedding download is enabled. An injectable local embedding interface may be
tested, but production semantic ranking requires an explicitly approved local model.

For a manual marker, evidence uses `kind: "marker"`, `method: "user_supplied"`,
`marker_id` and `label`; the exact item/source and timestamp are stored locally.
A direct user timestamp uses `kind: "timestamp"`, `method: "user_supplied"`.
Neither represents machine understanding of a visual scene. No caption match must
lead to an honest no-match and a marker/timestamp option. Multiple movie/edition
or scene candidates require user selection, with visible titles and timestamps.

## Module boundaries

- Claude Code owns new subtitle/resolver modules and their fixtures/tests only.
  It exposes `SubtitleSceneResolver(base_url, api_key, user_id=None, store=None)`;
  `editions(item_id)` returns compact source choices; `search(item_id,
  media_source_id, query, language=None, track_index=None, limit=3)` returns
  `{ok, candidates, ...}` with candidates shaped as the handoff above. Errors
  remain `{ok:false,reason,hint}`. A supplied mutable mapping is profile-local
  storage; no files are written inside the plugin. No changes to `jellyfin.py`.
- OpenCode owns `jellyfin.py`, `cast.py`, `playback.py` and their focused tests.
  `get_cast_source(item_id, media_source_id=None)` validates selected-source
  ownership; `manager.play(..., start_time_s=None)` retains ordinary behavior
  without the optional offset. An explicit offset starts playing near that point,
  including seeking/resuming the same edition when already playing or paused.
  Cast LOAD accepts the offset and an explicit SEEK supports existing sessions.
  Success requires fresh exact-media receiver state and measured position within
  a documented tolerance, never just a successful send or sender-side timestamp.
- Manager owns Hermes schemas/registration/handlers, movie ambiguity, saved
  markers, documentation, integration and sequential hardware acceptance. Shared
  files are reconciled by the manager, never edited concurrently by workers.

All network requests have explicit timeouts; Jellyfin credentials remain in
server-side headers. Existing relay expiry/redaction and Cast lifetime fixes stay.
TV power, visual frame analysis and generated scene descriptions are outside scope.

## Runtime scope compatibility

The v0.22.0 tool dispatcher injects `session_id`, not `conversation_id`. Handlers
prefer a trusted `conversation_id` if available and otherwise use the injected
`session_id`. No ID from model arguments participates. Missing host identity fails
closed; a session reset requires a new scene lookup. The actual ToolRegistry
smoke covers the v0.22.0 dispatch path and cross-session rejection.
