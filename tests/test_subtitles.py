"""Pure subtitle parsing and caption search (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_screen import subtitles as subs
from hermes_screen.subtitles import (
    Cue,
    SubtitleParseError,
    excerpt,
    find_exact,
    find_lexical,
    normalize_text,
    parse_srt,
    parse_subtitles,
    parse_webvtt,
    plain_text,
    time_windows,
)

FIXTURES = Path(__file__).parent / "fixtures" / "scenes"


def srt_bytes() -> bytes:
    return (FIXTURES / "lighthouse.en.srt").read_bytes()


def vtt_bytes() -> bytes:
    return (FIXTURES / "lighthouse.en.vtt").read_bytes()


# --- parsing --------------------------------------------------------------------------


def test_srt_fixture_keeps_original_text_times_and_indices() -> None:
    data = srt_bytes()
    assert data.startswith(b"\xef\xbb\xbf")  # BOM fixture
    cues = parse_srt(data)
    assert [c.index for c in cues] == list(range(9))
    first = cues[0]
    assert (first.start_ms, first.end_ms) == (1250, 3900)
    assert first.text == "<i>The storm came in from the west.</i>"  # original kept
    assert first.plain == "The storm came in from the west."
    # timing settings after the arrow are ignored; multiline text preserved
    assert cues[1].text == "Keep the lamp burning,\nno matter what happens."
    assert cues[2].plain == "Did you hear that?"  # {\an8} override removed for display
    assert cues[6].start_ms == 12 * 60_000 + 34_567
    assert cues[6].start_s == 754.567 and cues[6].end_s == 756.001
    assert cues[7].plain == "Captain & crew, abandon ship."
    assert cues[8].start_ms == 3_723_004  # hours parsed, ms exact


def test_webvtt_fixture_parses_notes_styles_ids_settings_and_tags() -> None:
    cues = parse_webvtt(vtt_bytes())
    assert len(cues) == 8
    assert all("note" not in c.plain.lower() for c in cues)
    assert (cues[0].start_ms, cues[0].end_ms) == (1250, 3900)
    assert cues[1].plain == "Keep the lamp burning, no matter what happens."
    assert cues[1].text.startswith("<v Mara>")
    assert cues[2].plain == "Did you hear that?"
    assert cues[3].plain == "It's only the wind."  # timestamp tag and entity handled
    assert cues[6].start_ms == 754_567
    assert cues[7].start_ms == 3_723_004


def test_sniffing_and_format_mismatch() -> None:
    assert len(parse_subtitles(vtt_bytes())) == 8
    assert len(parse_subtitles(srt_bytes())) == 9
    with pytest.raises(SubtitleParseError):
        parse_subtitles(vtt_bytes(), "srt")
    with pytest.raises(SubtitleParseError):
        parse_subtitles(srt_bytes(), "vtt")  # no WEBVTT header
    with pytest.raises(SubtitleParseError):
        parse_subtitles(srt_bytes(), "ass")


def test_crlf_and_cr_line_endings() -> None:
    text = srt_bytes().decode("utf-8-sig")
    assert len(parse_srt(text.replace("\n", "\r\n"))) == 9
    assert len(parse_srt(text.replace("\n", "\r"))) == 9


def test_malformed_srt_is_refused_not_half_parsed() -> None:
    with pytest.raises(SubtitleParseError) as err:
        parse_srt((FIXTURES / "malformed.srt").read_text())
    assert err.value.reason == "subtitle_malformed"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "\n\n\n",
        "just some words\nwith no timing",
        "1\n00:00:01,000 --> 00:00:02,000\n\n",  # cue without text only
        "<html><body>Error</body></html>",
        '{"error": "nope"}',
    ],
)
def test_garbage_never_yields_cues(text: str) -> None:
    with pytest.raises(SubtitleParseError):
        parse_subtitles(text)


def test_two_digit_milliseconds_rejected() -> None:
    bad = "1\n00:00:01,00 --> 00:00:02,000\nA\n\n2\n00:00:03,000 --> 00:00:04,000\nB\n"
    cues_or_err: list[Cue] | None
    try:
        cues_or_err = parse_srt(bad)
    except SubtitleParseError:
        cues_or_err = None
    # One bad block in two is tolerated by the absolute allowance; the bad cue is dropped.
    assert cues_or_err is not None and [c.plain for c in cues_or_err] == ["B"]


def test_continuation_block_joins_previous_cue() -> None:
    text = "1\n00:00:01,000 --> 00:00:02,000\nFirst part\n\nsecond paragraph\n"
    cues = parse_srt(text)
    assert len(cues) == 1 and cues[0].text == "First part\n\nsecond paragraph"


def test_nul_and_non_utf8_refused() -> None:
    with pytest.raises(SubtitleParseError) as err:
        parse_srt(b"1\n00:00:01,000 --> 00:00:02,000\n\xff\xfe bad\n")
    assert err.value.reason == "subtitle_encoding"
    with pytest.raises(SubtitleParseError):
        parse_srt("1\n00:00:01,000 --> 00:00:02,000\nA\x00B\n")


def test_size_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SubtitleParseError) as err:
        parse_srt("x" * (subs.MAX_SUBTITLE_CHARS + 1))
    assert err.value.reason == "subtitle_too_large"
    monkeypatch.setattr(subs, "MAX_CUES", 3)
    many = "".join(
        f"{i + 1}\n00:00:{i:02d},000 --> 00:00:{i:02d},500\nline {i}\n\n" for i in range(5)
    )
    with pytest.raises(SubtitleParseError) as err:
        parse_srt(many)
    assert err.value.reason == "subtitle_too_large"


def test_overlong_cue_is_dropped_as_malformed() -> None:
    long_line = "y" * (subs.MAX_CUE_CHARS + 1)
    text = (
        f"1\n00:00:01,000 --> 00:00:02,000\n{long_line}\n\n2\n00:00:03,000 --> 00:00:04,000\nok\n"
    )
    assert [c.plain for c in parse_srt(text)] == ["ok"]


# --- text helpers -------------------------------------------------------------------------


def test_normalize_text() -> None:
    assert normalize_text("It's ONLY the wind!") == "its only the wind"
    assert normalize_text("Café au lait, s’il vous plaît.") == "cafe au lait sil vous plait"
    assert normalize_text("- Where is   the key?") == "where is the key"
    assert plain_text("<b>Hi</b> &amp; {\\i1}bye") == "Hi & bye"


# --- search ---------------------------------------------------------------------------------


def _sorted(cues: list[Cue]) -> list[Cue]:
    return sorted(cues, key=lambda c: (c.start_ms, c.index))


def test_exact_search_single_cue_with_punctuation_and_case() -> None:
    cues = _sorted(parse_srt(srt_bytes()))
    hits = find_exact(cues, "its only the WIND")
    assert len(hits) == 1
    assert [cues[p].index for p in hits[0].positions] == [3]
    assert hits[0].method == "exact"


def test_exact_search_spans_neighboring_cues_with_original_timestamps() -> None:
    cues = _sorted(parse_srt(srt_bytes()))
    hits = find_exact(cues, "in the blue tin by the old stove")
    assert len(hits) == 1
    matched = [cues[p] for p in hits[0].positions]
    assert [c.index for c in matched] == [4, 5]
    assert matched[0].start_ms == 66_000 and matched[-1].end_ms == 70_000


def test_duplicate_phrase_gives_every_occurrence() -> None:
    cues = _sorted(parse_srt(srt_bytes()))
    hits = find_exact(cues, "keep the lamp burning")
    assert [[cues[p].index for p in h.positions] for h in hits] == [[1], [6]]


def test_exact_needs_word_boundaries() -> None:
    cues = _sorted(parse_srt(srt_bytes()))
    assert find_exact(cues, "amp burn") == []
    assert find_exact(cues, "the") != []


def test_window_never_joins_across_long_gaps() -> None:
    cues = _sorted(parse_srt(srt_bytes()))
    # cue 1 ends at 7.5s, cue 2 starts at 60s: not one window
    assert find_exact(cues, "no matter what happens did you hear that") == []
    for window in time_windows(cues):
        for a, b in zip(window, window[1:], strict=False):
            assert cues[b].start_ms - cues[a].end_ms <= subs.WINDOW_MAX_GAP_MS


def test_lexical_is_weaker_and_labelled() -> None:
    cues = _sorted(parse_srt(srt_bytes()))
    assert find_exact(cues, "where did the key go blue tin") == []
    hits = find_lexical(cues, "where did the key go blue tin")
    assert hits and hits[0].method == "lexical" and 0.6 <= hits[0].score < 1
    assert 4 in [cues[p].index for p in hits[0].positions]
    assert find_lexical(cues, "the") == []  # no content words
    assert find_lexical(cues, "spaceship laser") == []


@pytest.mark.parametrize("query", ["", "   ", "?!", "x" * 201, " ".join(["w"] * 40)])
def test_bad_queries_raise(query: str) -> None:
    cues = parse_srt(srt_bytes())
    with pytest.raises(ValueError):
        find_exact(cues, query)


def test_excerpt_is_short_and_centered() -> None:
    long_text = "word " * 100 + "needle here " + "tail " * 100
    cue = Cue(index=0, start_ms=0, end_ms=1, text=long_text.strip())
    ex = excerpt([cue], "needle here")
    assert len(ex) <= subs.EXCERPT_CHARS + 2 and "needle here" in ex
    assert ex.startswith("…") and ex.endswith("…")
