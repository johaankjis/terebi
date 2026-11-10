"""Text subtitle parsing and caption search for scene lookup.

Pure functions only: no network, no files, no global state. The resolver in
``scene_search.py`` fetches a track from Jellyfin and hands the text here.

What this module promises:

* SubRip (``.srt``) and WebVTT (``.vtt``) are parsed into :class:`Cue` objects
  that keep the **original** payload text and the original start/end times in
  whole milliseconds. Each cue's ``index`` is its 0-based position in the file,
  so it is stable for the same content.
* Malformed input is rejected rather than half-parsed: an unparseable timing
  line, an end before its start, or too much junk raises
  :class:`SubtitleParseError`. A track that parses to zero cues is an error, never
  an empty "match nothing" index.
* Every size is bounded (characters, cues, cue length, time range, query).
* Search is lexical. ``exact`` means the normalized query phrase occurs, at
  word boundaries, inside one cue or a short run of neighboring cues.
  ``lexical`` means most of the query's content words occur in such a window;
  it is a weaker hint and is labelled as such. Neither describes what is on
  screen: a caption match is evidence of dialogue, not of a visual scene.
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "MAX_CUES",
    "MAX_CUE_CHARS",
    "MAX_QUERY_CHARS",
    "MAX_SUBTITLE_CHARS",
    "Cue",
    "Match",
    "SubtitleParseError",
    "excerpt",
    "find_exact",
    "find_lexical",
    "normalize_text",
    "parse_srt",
    "parse_subtitles",
    "parse_webvtt",
    "plain_text",
    "query_tokens",
    "time_windows",
]

# --- limits ----------------------------------------------------------------------

MAX_SUBTITLE_CHARS = 2_000_000  # a feature film is typically 50-150 kB of SRT
MAX_CUES = 20_000
MAX_CUE_CHARS = 1_000  # payload of one cue, original text
MAX_TIME_MS = 48 * 3600 * 1000  # nothing we play is longer than two days
MAX_QUERY_CHARS = 200
MAX_QUERY_TOKENS = 32
MAX_MALFORMED_ABS = 2  # junk blocks tolerated before the whole track is refused...
MAX_MALFORMED_RATIO = 0.02  # ...or this share of blocks, whichever is larger

WINDOW_CUES = 3  # a phrase may span at most this many neighboring cues
WINDOW_MAX_GAP_MS = 5_000  # neighbors further apart than this are not one window
LEXICAL_MIN_TOKENS = 2
LEXICAL_MIN_SCORE = 0.6
EXCERPT_CHARS = 200


class SubtitleParseError(ValueError):
    """The subtitle text is not usable. ``reason`` is a stable machine string."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True, slots=True)
class Cue:
    """One caption cue with its original text and times (milliseconds)."""

    index: int
    start_ms: int
    end_ms: int
    text: str  # original payload (tags and line breaks preserved)

    @property
    def start_s(self) -> float:
        return self.start_ms / 1000

    @property
    def end_s(self) -> float:
        return self.end_ms / 1000

    @property
    def plain(self) -> str:
        return plain_text(self.text)


@dataclass(frozen=True, slots=True)
class Match:
    """A run of time-ordered cues (positions into the searched sequence)."""

    positions: tuple[int, ...]
    method: str  # "exact" or "lexical"
    score: float  # 1.0 for exact; share of query content words for lexical


# --- text helpers ------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^<>\n]{0,200}>")
_ASS_OVERRIDE_RE = re.compile(r"\{\\[^{}\n]{0,200}\}")
_APOSTROPHES = str.maketrans("", "", "'’ʼ`´")
_NON_WORD_RE = re.compile(r"[\W_]+", re.UNICODE)


def plain_text(raw: str) -> str:
    """Caption payload with markup removed and whitespace collapsed (for display)."""
    text = _ASS_OVERRIDE_RE.sub("", raw)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = text.replace("‎", "").replace("‏", "")  # &lrm; / &rlm;
    return " ".join(text.split())


def normalize_text(text: str) -> str:
    """Case, accent and punctuation insensitive form used for matching.

    Apostrophes are dropped (``don't`` == ``dont``); every other non-word
    character becomes a space.
    """
    folded = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = folded.translate(_APOSTROPHES)
    return " ".join(_NON_WORD_RE.sub(" ", folded).split())


_STOPWORDS = frozenset(
    "a an and are as at be but by do for from he her him his i if in is it its me my "
    "no not of on or our she so that the their them they this to up us was we were "
    "what when where who why will with you your".split()
)


def query_tokens(query: str) -> list[str]:
    """Normalized query tokens (bounded); raises ``ValueError`` if unusable."""
    if not isinstance(query, str):
        raise ValueError("query must be text")
    if len(query) > MAX_QUERY_CHARS:
        raise ValueError("query too long")
    tokens = normalize_text(query).split()
    if not tokens:
        raise ValueError("query has no words")
    if len(tokens) > MAX_QUERY_TOKENS:
        raise ValueError("query has too many words")
    return tokens


# --- parsing -------------------------------------------------------------------------

_SRT_TIME = r"(\d{1,3}):([0-5]\d):([0-5]\d)[,.](\d{3})"
_SRT_TIMING_RE = re.compile(rf"^\s*{_SRT_TIME}\s*-->\s*{_SRT_TIME}(?:\s+[^\n]*)?\s*$")
_VTT_TIME = r"(?:(\d{1,3}):)?([0-5]\d):([0-5]\d)\.(\d{3})"
_VTT_TIMING_RE = re.compile(rf"^\s*{_VTT_TIME}[ \t]+-->[ \t]+{_VTT_TIME}(?:[ \t]+[^\n]*)?$")
_VTT_HEADER_RE = re.compile(r"^WEBVTT(?:[ \t][^\n]*)?$")


def _ms(h: str | None, m: str, s: str, frac: str) -> int:
    return ((int(h or 0) * 60 + int(m)) * 60 + int(s)) * 1000 + int(frac)


def _prepare(data: str | bytes) -> str:
    if isinstance(data, bytes):
        if len(data) > MAX_SUBTITLE_CHARS * 4:
            raise SubtitleParseError("subtitle_too_large", "subtitle data is too large")
        try:
            data = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise SubtitleParseError("subtitle_encoding", "subtitle is not UTF-8") from None
    if not isinstance(data, str):
        raise SubtitleParseError("subtitle_unparseable", "subtitle data is not text")
    if len(data) > MAX_SUBTITLE_CHARS:
        raise SubtitleParseError("subtitle_too_large", "subtitle data is too large")
    if data.startswith("﻿"):
        data = data[1:]
    if "\x00" in data:
        raise SubtitleParseError("subtitle_unparseable", "subtitle contains NUL bytes")
    return data.replace("\r\n", "\n").replace("\r", "\n")


def _blocks(text: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.split("\n"):
        if line.strip():
            current.append(line.rstrip())
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _check_malformed(malformed: int, total: int) -> None:
    allowed = max(MAX_MALFORMED_ABS, int(total * MAX_MALFORMED_RATIO))
    if malformed > allowed:
        raise SubtitleParseError(
            "subtitle_malformed", f"{malformed} of {total} subtitle blocks are malformed"
        )


def _make_cue(index: int, start: int, end: int, lines: list[str]) -> Cue | None:
    if end < start or start > MAX_TIME_MS or end > MAX_TIME_MS:
        return None
    payload = "\n".join(lines)
    if len(payload) > MAX_CUE_CHARS:
        return None
    return Cue(index=index, start_ms=start, end_ms=end, text=payload)


def _finish(cues: list[Cue], malformed: int, total: int) -> list[Cue]:
    _check_malformed(malformed, total)
    if not cues:
        raise SubtitleParseError("subtitle_empty", "subtitle has no usable cues")
    return cues


def parse_srt(data: str | bytes) -> list[Cue]:
    """Parse SubRip text. Raises :class:`SubtitleParseError` when unusable."""
    blocks = _blocks(_prepare(data))
    cues: list[Cue] = []
    malformed = 0
    for block in blocks:
        timing_at = next((i for i, line in enumerate(block) if "-->" in line), None)
        if timing_at is None:
            # A blank line inside a cue's text: continuation of the previous cue.
            if cues and not any(line.strip().isdigit() for line in block[:1]):
                prev = cues[-1]
                merged = _make_cue(prev.index, prev.start_ms, prev.end_ms, [prev.text, "", *block])
                if merged is not None:
                    cues[-1] = merged
                    continue
            malformed += 1
            continue
        # Before the timing line at most one numeric counter is allowed.
        prefix = block[:timing_at]
        if len(prefix) > 1 or (prefix and not prefix[0].strip().isdigit()):
            malformed += 1
            continue
        found = _SRT_TIMING_RE.match(block[timing_at])
        if not found:
            malformed += 1
            continue
        g = found.groups()
        lines = block[timing_at + 1 :]
        if any("-->" in line for line in lines):
            malformed += 1  # two timing lines in one block: missing separator
            continue
        cue = _make_cue(len(cues), _ms(*g[0:4]), _ms(*g[4:8]), lines)
        if cue is None:
            malformed += 1
            continue
        if len(cues) >= MAX_CUES:
            raise SubtitleParseError("subtitle_too_large", "subtitle has too many cues")
        if cue.text.strip():
            cues.append(cue)
    return _finish(cues, malformed, len(blocks))


def parse_webvtt(data: str | bytes) -> list[Cue]:
    """Parse WebVTT text. Raises :class:`SubtitleParseError` when unusable."""
    text = _prepare(data)
    blocks = _blocks(text)
    if not blocks or not _VTT_HEADER_RE.match(blocks[0][0]):
        raise SubtitleParseError("subtitle_unparseable", "WebVTT header is missing")
    if any("-->" in line for line in blocks[0][1:]):
        raise SubtitleParseError("subtitle_malformed", "WebVTT header block is malformed")
    cues: list[Cue] = []
    malformed = 0
    body = blocks[1:]
    for block in body:
        first = block[0]
        if first.startswith(("NOTE", "STYLE", "REGION")) and "-->" not in first:
            continue
        timing_at = next((i for i, line in enumerate(block) if "-->" in line), None)
        if timing_at is None or timing_at > 1:
            malformed += 1
            continue
        found = _VTT_TIMING_RE.match(block[timing_at])
        if not found:
            malformed += 1
            continue
        g = found.groups()
        lines = block[timing_at + 1 :]
        if any("-->" in line for line in lines):
            malformed += 1
            continue
        cue = _make_cue(len(cues), _ms(*g[0:4]), _ms(*g[4:8]), lines)
        if cue is None:
            malformed += 1
            continue
        if len(cues) >= MAX_CUES:
            raise SubtitleParseError("subtitle_too_large", "subtitle has too many cues")
        if cue.text.strip():
            cues.append(cue)
    return _finish(cues, malformed, len(body))


def parse_subtitles(data: str | bytes, fmt: str | None = None) -> list[Cue]:
    """Parse ``fmt`` (``"srt"`` or ``"vtt"``), or sniff it when ``None``."""
    text = _prepare(data)
    looks_vtt = text.lstrip("\n").startswith("WEBVTT")
    if fmt is None:
        fmt = "vtt" if looks_vtt else "srt"
    if fmt == "vtt":
        return parse_webvtt(text)
    if fmt == "srt":
        if looks_vtt:
            raise SubtitleParseError("subtitle_unparseable", "expected SubRip, got WebVTT")
        return parse_srt(text)
    raise SubtitleParseError("subtitle_unsupported", "only SubRip and WebVTT are supported")


# --- search ------------------------------------------------------------------------------


def time_windows(cues: Sequence[Cue], max_cues: int = WINDOW_CUES) -> list[tuple[int, ...]]:
    """Every run of up to ``max_cues`` time-ordered neighbors (positions).

    ``cues`` must already be sorted by start time. A run stops at a gap longer
    than :data:`WINDOW_MAX_GAP_MS`, so phrases never join across a scene pause.
    """
    windows: list[tuple[int, ...]] = []
    for start in range(len(cues)):
        run = [start]
        windows.append((start,))
        for nxt in range(start + 1, min(len(cues), start + max_cues)):
            if cues[nxt].start_ms - cues[run[-1]].end_ms > WINDOW_MAX_GAP_MS:
                break
            run.append(nxt)
            windows.append(tuple(run))
    return windows


def _span_contains(outer: tuple[int, ...], inner: tuple[int, ...]) -> bool:
    return outer != inner and outer[0] <= inner[0] and inner[-1] <= outer[-1]


def find_exact(
    cues: Sequence[Cue], query: str, *, norm_texts: Sequence[str] | None = None
) -> list[Match]:
    """Smallest neighbor runs whose text contains the normalized query phrase."""
    phrase = " " + " ".join(query_tokens(query)) + " "
    norms = list(norm_texts) if norm_texts is not None else [normalize_text(c.text) for c in cues]
    hits: list[tuple[int, ...]] = []
    for window in time_windows(cues):
        if hits and hits[-1][0] == window[0]:
            continue  # this start already matched with a smaller window
        joined = " " + " ".join(norms[p] for p in window if norms[p]) + " "
        if phrase in joined:
            hits.append(window)
    minimal = [h for h in hits if not any(_span_contains(h, o) for o in hits)]
    return [Match(positions=h, method="exact", score=1.0) for h in minimal]


def find_lexical(
    cues: Sequence[Cue], query: str, *, norm_texts: Sequence[str] | None = None
) -> list[Match]:
    """Windows containing most of the query's content words (weaker than exact).

    Needs at least :data:`LEXICAL_MIN_TOKENS` content words in the query and a
    share of at least :data:`LEXICAL_MIN_SCORE` present. Overlapping windows are
    collapsed to the best, smallest one. Results are best first.
    """
    tokens = [t for t in dict.fromkeys(query_tokens(query)) if t not in _STOPWORDS]
    if len(tokens) < LEXICAL_MIN_TOKENS:
        return []
    norms = list(norm_texts) if norm_texts is not None else [normalize_text(c.text) for c in cues]
    words = [set(n.split()) for n in norms]
    scored: list[tuple[float, tuple[int, ...]]] = []
    for window in time_windows(cues):
        present: set[str] = set().union(*(words[p] for p in window))
        hit = sum(1 for t in tokens if t in present)
        if hit >= LEXICAL_MIN_TOKENS and hit / len(tokens) >= LEXICAL_MIN_SCORE:
            scored.append((hit / len(tokens), window))
    scored.sort(key=lambda sw: (-sw[0], len(sw[1]), sw[1][0]))
    taken: list[Match] = []
    used: set[int] = set()
    for score, window in scored:
        if used.intersection(window):
            continue
        used.update(window)
        taken.append(Match(positions=window, method="lexical", score=round(score, 3)))
    return taken


def excerpt(cues: Sequence[Cue], query: str | None = None, limit: int = EXCERPT_CHARS) -> str:
    """Short display excerpt of the given cues, centered on the query if possible."""
    text = " ".join(p for p in (c.plain for c in cues) if p)
    if len(text) <= limit:
        return text
    at = 0
    if query:
        words = [re.escape(w) for w in query.split() if w.strip()][:8]
        if words:
            found = re.search(r"\W+".join(words), text, re.IGNORECASE)
            if found:
                at = max(0, found.start() - limit // 4)
    start = min(at, len(text) - limit)
    piece = text[start : start + limit].strip()
    return ("…" if start > 0 else "") + piece + ("…" if start + limit < len(text) else "")
