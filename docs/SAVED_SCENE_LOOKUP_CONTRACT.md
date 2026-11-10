# Saved scene description demo handoff

Base PR #4: `3cc3c1e7748dbd043ac98eab201a0adced9e3a78`.
No subtitles, embeddings/model downloads, cloud matching, or frame analysis.
No network or hardware access in the worker. One focused Claude Code task.

Worker owns only NEW `hermes_screen/saved_scene_lookup.py` and
`tests/test_saved_scene_lookup.py`. Manager owns scene_tools.py, schemas.py,
all wiring/data/docs and wiring tests. Preserve other files and marker records.

Pure API:
`lookup_saved_scenes(markers, item_id, media_source_id, query, *, source_fingerprint)`
returns `{ok: true, match: "clear"|"ambiguous"|"none", method:
"local_saved_description", candidates: [unchanged deep-copied marker records],
hint?: str}` or a small `{ok:false,reason,hint}` argument error.

Existing markers stay in profile-owned `scene_markers_v1:<scope>` state. Record:
`{item_id, media_source_id, start_time_s, evidence:{kind:"marker",
method:"user_supplied", marker_id,label,source_fingerprint,description?:str,
aliases?:list[str],end_time_s?:number}}`. New fields are optional. Legacy marker
labels remain usable through the existing exact-label path, but label-only
markers are not invented descriptions. Match only valid described records for
EXACT item/source/fingerprint, before ranking. Never mutate input records/state.
Ignore stale, malformed, wrong-edition, or undescribed records. Respect bounded
strings/list size and finite timestamps (end must follow start if present).

Support short descriptions/paraphrases locally with a small deterministic
word/phrase normalization and conservative scoring. Explain the limits honestly;
this is local lookup of human-verified saved descriptions, not visual analysis.
Avoid choosing on generic words like movie/play/scene/Bunny alone. A clear match
needs distinct supporting action/object evidence and a margin over alternatives;
plausible competitors return ambiguous, and unsupported requests return none.
No fallback to an arbitrary first marker. No token result causes playback here.
Tests must exercise paraphrase clear matches, generic/competing ambiguity,
unmatched descriptions, negation/contradictions where applicable, exact source
isolation, invalid/stale records, deterministic order and input preservation.
Manager converts only results to existing conversation-bound timestamp choices.
