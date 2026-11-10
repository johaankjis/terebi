"""Pure local lookup of saved scene descriptions; fixtures only, no I/O."""

from __future__ import annotations

import copy
import math

import pytest

from hermes_screen import saved_scene_lookup as lookup_module
from hermes_screen.saved_scene_lookup import lookup_saved_scenes

ITEM = "e5d6c471a8a4ea26e00a3694f91bf8d1"
OTHER_ITEM = "11111111111111111111111111111111"
SOURCE = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
OTHER_SOURCE = "0f9e8d7c6b5a49382716f5e4d3c2b1a0"
FP = "sha256:edition-one"


def marker(
    marker_id: str,
    start: float,
    description: str | None = None,
    *,
    aliases: list | None = None,
    end: float | None = None,
    item_id: str = ITEM,
    source: str = SOURCE,
    fingerprint: str = FP,
    label: str | None = None,
) -> dict:
    evidence = {
        "kind": "marker",
        "method": "user_supplied",
        "marker_id": marker_id,
        "label": label or f"label {marker_id}",
        "source_fingerprint": fingerprint,
    }
    if description is not None:
        evidence["description"] = description
    if aliases is not None:
        evidence["aliases"] = aliases
    if end is not None:
        evidence["end_time_s"] = end
    return {
        "item_id": item_id,
        "media_source_id": source,
        "start_time_s": start,
        "evidence": evidence,
    }


WAKE = marker("wake", 62.0, "Bunny wakes up and emerges from his burrow", end=95.5)
BUTTERFLY = marker("butterfly", 310.0, "The bullies attack a butterfly")
TRAPS = marker("traps", 420.0, "Bunny sets traps for the bullies", aliases=["revenge prep"])
DEMO = [WAKE, BUTTERFLY, TRAPS]


def lookup(markers, query, *, item=ITEM, source=SOURCE, fingerprint=FP):
    return lookup_saved_scenes(markers, item, source, query, source_fingerprint=fingerprint)


def ids(result) -> list[str]:
    return [c["evidence"]["marker_id"] for c in result["candidates"]]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("the rabbit gets up and goes outside", "wake"),
        ("Bunny waking and coming out of his hole", "wake"),
        ("the little thugs hurt the insect", "butterfly"),
        ("when the bad guys pick on the butterfly", "butterfly"),
        ("he builds snares to catch them", "traps"),
        ("Bunny setting traps", "traps"),
        ("the butterfly", "butterfly"),
    ],
)
def test_paraphrases_resolve_to_one_clear_record(query, expected):
    result = lookup(DEMO, query)
    assert result["ok"] is True
    assert result["match"] == "clear"
    assert result["method"] == "local_saved_description"
    assert ids(result) == [expected]
    assert "hint" not in result


def test_clear_candidate_is_an_unchanged_deep_copy():
    result = lookup(DEMO, "the rabbit gets up and goes outside")
    assert result["candidates"] == [WAKE]
    assert result["candidates"][0] is not WAKE
    assert result["candidates"][0]["evidence"] is not WAKE["evidence"]


def test_aliases_teach_new_phrasings():
    record = marker("carrot", 50.0, "Bunny finds a carrot", aliases=["the veggie snack bit"])
    result = lookup([record, BUTTERFLY], "bunny eats the veggie snack")
    assert result["match"] == "clear"
    assert ids(result) == ["carrot"]


def test_alias_only_record_is_described():
    record = marker("alias", 12.0, aliases=["sunrise over the meadow"])
    assert ids(lookup([record], "the dawn meadow")) == ["alias"]


@pytest.mark.parametrize("query", ["the bunny scene", "Big Buck Bunny", "the part with the hero"])
def test_protagonist_alone_is_ambiguous_never_first_record(query):
    result = lookup(DEMO, query)
    assert result["match"] == "ambiguous"
    assert ids(result) == ["wake", "traps"]
    assert "describe" in result["hint"]


@pytest.mark.parametrize("query", ["play the scene", "the movie", "jump to that part please"])
def test_generic_request_returns_none(query):
    result = lookup(DEMO, query)
    assert result["match"] == "none"
    assert result["candidates"] == []
    assert "generic" in result["hint"]


def test_shared_object_is_ambiguous():
    result = lookup(DEMO, "the bullies")
    assert result["match"] == "ambiguous"
    assert ids(result) == ["butterfly", "traps"]


def test_overlapping_descriptions_are_ambiguous_in_stable_order():
    first = marker("snare-a", 400.0, "Bunny builds a snare from a vine")
    second = marker("snare-b", 200.0, "Bunny builds traps in the clearing")
    result = lookup([first, second], "he builds traps")
    assert result["match"] == "ambiguous"
    assert ids(result) == ["snare-b", "snare-a"]  # equal score: earlier start first
    assert lookup([second, first], "he builds traps") == result


def test_extra_distinguishing_concept_breaks_the_tie():
    first = marker("snare-a", 400.0, "Bunny builds a snare from a vine")
    second = marker("snare-b", 200.0, "Bunny builds traps in the clearing")
    result = lookup([first, second], "he builds a trap with a vine")
    assert result["match"] == "clear"
    assert ids(result) == ["snare-a"]


def test_identical_descriptions_never_pick_first():
    a = marker("a", 10.0, "Bunny smells a flower")
    b = marker("b", 20.0, "Bunny smells a flower")
    result = lookup([a, b], "he sniffs the flower")
    assert result["match"] == "ambiguous"
    assert ids(result) == ["a", "b"]


def test_partial_literal_match_is_not_clear():
    record = marker("car", 10.0, "A red car drives past")
    result = lookup([record], "the red truck explodes loudly")
    assert result["match"] == "ambiguous"
    assert ids(result) == ["car"]
    assert "Confirm" in result["hint"]


@pytest.mark.parametrize(
    "query", ["the car explodes", "the spaceship lands", "bunny falls asleep at night"]
)
def test_unsupported_request_returns_none(query):
    result = lookup(DEMO, query)
    assert result == {
        "ok": True,
        "match": "none",
        "method": "local_saved_description",
        "candidates": [],
        "hint": result["hint"],
    }


def test_negated_concept_excludes_matching_record():
    result = lookup(DEMO, "the bullies but not the butterfly")
    assert result["match"] == "clear"
    assert ids(result) == ["traps"]
    result = lookup(DEMO, "the bullies without the butterfly")
    assert ids(result) == ["traps"]


def test_negated_action_excludes_contradicting_record():
    result = lookup(DEMO, "the bullies don't attack anything")
    # traps record has bullies but no attack: only the bully object remains.
    assert result["match"] == "clear"
    assert ids(result) == ["traps"]
    assert lookup([BUTTERFLY], "the bullies don't attack the insect")["match"] == "none"


def test_antonym_contradiction_excludes_record():
    sleeping = marker("sleep", 5.0, "Bunny sleeps in his burrow")
    assert ids(lookup([WAKE, sleeping], "bunny naps in the hole")) == ["sleep"]
    assert ids(lookup([WAKE, sleeping], "bunny wakes in the hole")) == ["wake"]


def test_negated_description_contradicts_positive_request():
    calm = marker("calm", 5.0, "The bullies watch the butterfly but do not attack")
    result = lookup([calm, BUTTERFLY], "the thugs hurt the butterfly")
    assert ids(result) == ["butterfly"]


def test_exact_edition_isolation():
    other_source = marker("o-src", 1.0, "Bunny sets traps", source=OTHER_SOURCE)
    other_item = marker("o-item", 1.0, "Bunny sets traps", item_id=OTHER_ITEM)
    stale = marker("stale", 1.0, "Bunny sets traps", fingerprint="sha256:old")
    records = [other_source, other_item, stale, TRAPS]
    result = lookup(records, "he sets traps")
    assert result["match"] == "clear"
    assert ids(result) == ["traps"]
    assert ids(lookup(records, "he sets traps", source=OTHER_SOURCE)) == ["o-src"]
    assert ids(lookup(records, "he sets traps", item=OTHER_ITEM)) == ["o-item"]
    assert ids(lookup(records, "he sets traps", fingerprint="sha256:old")) == ["stale"]
    assert lookup(records, "he sets traps", fingerprint="sha256:new")["match"] == "none"


def test_scope_ids_are_exact_not_normalized():
    upper = marker("upper", 1.0, "Bunny sets traps", item_id=ITEM.upper())
    assert lookup([upper], "he sets traps")["match"] == "none"


def test_label_only_markers_are_not_descriptions():
    legacy = marker("legacy", 5.0, label="bunny sets traps")
    result = lookup([legacy], "bunny sets traps")
    assert result["match"] == "none"
    assert "No saved scene descriptions" in result["hint"]
    # A described record's label is not matched either.
    labelled = marker("lab", 5.0, "The bullies attack a butterfly", label="sunrise")
    assert lookup([labelled], "the sunrise")["match"] == "none"


def _malformed() -> list:
    def edit(fn):
        record = copy.deepcopy(TRAPS)
        fn(record)
        return record

    return [
        None,
        "traps",
        [TRAPS],
        edit(lambda r: r.pop("evidence")),
        edit(lambda r: r.update(evidence="x")),
        edit(lambda r: r["evidence"].update(kind="subtitle")),
        edit(lambda r: r["evidence"].update(method="model_guess")),
        edit(lambda r: r["evidence"].pop("marker_id")),
        edit(lambda r: r["evidence"].update(marker_id="")),
        edit(lambda r: r["evidence"].update(marker_id="x" * 200)),
        edit(lambda r: r["evidence"].pop("label")),
        edit(lambda r: r["evidence"].update(label="x" * 81)),
        edit(lambda r: r.pop("start_time_s")),
        edit(lambda r: r.update(start_time_s=True)),
        edit(lambda r: r.update(start_time_s="10")),
        edit(lambda r: r.update(start_time_s=-1)),
        edit(lambda r: r.update(start_time_s=math.nan)),
        edit(lambda r: r.update(start_time_s=math.inf)),
        edit(lambda r: r.update(start_time_s=10**400)),
        edit(lambda r: r.update(start_time_s=lookup_module.MAX_TIME_S + 1)),
        edit(lambda r: r["evidence"].update(end_time_s=420.0)),
        edit(lambda r: r["evidence"].update(end_time_s=100.0)),
        edit(lambda r: r["evidence"].update(end_time_s=math.nan)),
        edit(lambda r: r["evidence"].update(end_time_s=False)),
        edit(lambda r: r["evidence"].update(description=42)),
        edit(lambda r: r["evidence"].update(description="   ")),
        edit(lambda r: r["evidence"].update(description="traps " * 100)),
        edit(lambda r: r["evidence"].update(aliases="traps")),
        edit(lambda r: r["evidence"].update(aliases=["traps"] * 9)),
        edit(lambda r: r["evidence"].update(aliases=["ok", 7])),
        edit(lambda r: r["evidence"].update(aliases=["ok", ""])),
        edit(lambda r: r["evidence"].update(aliases=["x" * 121])),
    ]


@pytest.mark.parametrize("bad", _malformed())
def test_malformed_records_are_ignored(bad):
    result = lookup([bad], "he sets traps")
    assert result["ok"] is True
    assert result["match"] == "none"
    # And they never block a valid neighbour.
    assert ids(lookup([bad, BUTTERFLY], "the thugs hurt the insect")) == ["butterfly"]


def test_valid_end_time_and_empty_aliases_list_are_accepted():
    record = marker("ok", 10, "Bunny sets traps", aliases=[], end=10.5)
    assert ids(lookup([record], "he sets traps")) == ["ok"]


@pytest.mark.parametrize(
    ("args", "reason"),
    [
        (("not a list", ITEM, SOURCE, "traps", FP), "invalid_markers"),
        (([TRAPS] * 101, ITEM, SOURCE, "traps", FP), "invalid_markers"),
        ((DEMO, "", SOURCE, "traps", FP), "invalid_scope"),
        ((DEMO, ITEM + " ", SOURCE, "traps", FP), "invalid_scope"),
        ((DEMO, ITEM, None, "traps", FP), "invalid_scope"),
        ((DEMO, ITEM, SOURCE, "traps", ""), "invalid_scope"),
        ((DEMO, ITEM, SOURCE, "traps", "x" * 129), "invalid_scope"),
        ((DEMO, ITEM, SOURCE, "", FP), "invalid_query"),
        ((DEMO, ITEM, SOURCE, "   ", FP), "invalid_query"),
        ((DEMO, ITEM, SOURCE, None, FP), "invalid_query"),
        ((DEMO, ITEM, SOURCE, "x" * 201, FP), "invalid_query"),
    ],
)
def test_invalid_arguments_are_small_errors(args, reason):
    markers, item, source, query, fingerprint = args
    result = lookup_saved_scenes(markers, item, source, query, source_fingerprint=fingerprint)
    assert set(result) == {"ok", "reason", "hint"}
    assert result["ok"] is False
    assert result["reason"] == reason


def test_tuple_of_markers_is_accepted():
    assert ids(lookup(tuple(DEMO), "he sets traps")) == ["traps"]


def test_candidates_are_capped():
    records = [marker(f"m{i:02d}", float(i), "The bullies attack") for i in range(20)]
    result = lookup(records, "the bullies attack")
    assert result["match"] == "ambiguous"
    assert ids(result) == [f"m{i:02d}" for i in range(lookup_module.MAX_CANDIDATES)]


def test_inputs_are_never_mutated_and_results_are_deterministic():
    records = copy.deepcopy(DEMO) + [marker("legacy", 5.0), None, {"item_id": ITEM}]
    before = copy.deepcopy(records)
    queries = ["the bullies", "he builds snares", "the bunny scene", "nothing here"]
    first = [lookup(records, q) for q in queries]
    for result in first:
        for candidate in result["candidates"]:
            candidate["evidence"]["label"] = "changed by caller"
            candidate["start_time_s"] = -1
    assert records == before
    assert [lookup(records, q) for q in queries] != first  # first was edited by caller
    assert [lookup(records, q) for q in queries] == [lookup(records, q) for q in queries]
    assert records == before


def test_no_description_in_edition_hint():
    result = lookup([], "the bullies")
    assert result["match"] == "none"
    assert "No saved scene descriptions" in result["hint"]


def test_lexicon_surface_forms_map_to_one_concept():
    seen: dict[str, str] = {}
    for concept, (_category, words, phrases) in lookup_module._LEXICON.items():
        for word in words:
            for form in lookup_module._inflections(word):
                assert seen.setdefault(form, concept) == concept, form
        for phrase in phrases:
            head, *rest = phrase.split()
            for form in lookup_module._inflections(head):
                key = " ".join((form, *rest))
                assert seen.setdefault(key, concept) == concept, key
