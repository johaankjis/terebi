"""Tests for hermes_screen.picker.

Two layers: a scripted fake client for ordering/dedup/limits/errors, and the
real ``JellyfinClient`` behind respx for actual field mapping and exact runtime
enforcement. No network, no Jellyfin server, no Roku.
"""

from __future__ import annotations

import math
from typing import Any

import httpx
import pytest
import respx

from hermes_screen.jellyfin import JellyfinClient, JellyfinError
from hermes_screen.picker import MAX_PICKS, pick_titles

BASE = "http://jf.test:8096"
KEY = "s3cr3t-api-key-0123456789abcdef"
USER_ID = "11111111111111111111111111111111"
MIN = 600_000_000  # ticks per minute


def iid(n: int) -> str:
    return f"{n:032x}"


# --- fake client (public JellyfinClient shapes) ----------------------------------------


def rec(n: int, **kw: Any) -> dict[str, Any]:
    """A normalized unwatched Movie record as JellyfinClient.find_items returns it."""
    data: dict[str, Any] = {
        "item_id": iid(n),
        "title": f"Movie {n}",
        "type": "Movie",
        "year": 2010,
        "minutes": 30,
        "genres": [],
        "played": False,
    }
    data.update(kw)
    return data


def _is_num(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def resume_rec(n: int, remaining: int = 20, position_s: int = 600, **kw: Any) -> dict[str, Any]:
    data = rec(n, played=False, resume_seconds=position_s, remaining_minutes=remaining)
    data["minutes"] = (remaining if _is_num(remaining) else 20) + position_s // 60
    data.update(kw)
    return data


def episode_rec(n: int, remaining: int = 25, **kw: Any) -> dict[str, Any]:
    data = resume_rec(
        n,
        remaining=remaining,
        position_s=0,
        type="Episode",
        title=f"Ep {n}",
        series_id=iid(900 + n),
        series_name=f"Show {n}",
        season_number=1,
        episode_number=n,
    )
    data.update(kw)
    return data


def answer(items: list[Any], **kw: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "items": items,
        "scanned": len(items),
        "truncated": False,
        "skipped_unknown_runtime": 0,
        "skipped_malformed": 0,
        "skipped_filtered": 0,
    }
    data.update(kw)
    return data


class FakeClient:
    def __init__(self, resume=None, next_up=None, unwatched=None) -> None:
        self.script = {
            "resume": resume if resume is not None else answer([]),
            "next_up": next_up if next_up is not None else answer([]),
            "unwatched": unwatched if unwatched is not None else answer([]),
        }
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _go(self, name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, kwargs))
        value = self.script[name]
        if isinstance(value, Exception):
            raise value
        return value

    def get_resume_items(self, **kw: Any) -> dict[str, Any]:
        return self._go("resume", kw)

    def get_next_up(self, series_id: str | None = None, **kw: Any) -> dict[str, Any]:
        assert series_id is None
        return self._go("next_up", kw)

    def find_items(self, query: str | None = None, **kw: Any) -> dict[str, Any]:
        assert query is None
        return self._go("unwatched", kw)


def ids(result: dict[str, Any]) -> list[str]:
    return [p["item_id"] for p in result["picks"]]


# --- arguments --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [0, -1, -0.5, math.nan, math.inf, -math.inf, True, False, None, "30", [30], 1441, 1e9],
)
def test_invalid_runtime_limit_is_rejected_before_any_call(bad):
    fake = FakeClient()
    result = pick_titles(fake, bad)
    assert result["ok"] is False
    assert result["reason"] == "invalid_argument"
    assert result["hint"]
    assert fake.calls == []


@pytest.mark.parametrize("bad", [0, -1, 4, True, 2.0, "3", None])
def test_invalid_pick_count_is_rejected(bad):
    fake = FakeClient()
    result = pick_titles(fake, 60, limit=bad)
    assert result["reason"] == "invalid_argument"
    assert fake.calls == []


@pytest.mark.parametrize("ok", [0.001, 0.5, 1, 90, 90.5, 1440, 1440.0])
def test_valid_limits_are_passed_to_the_client_exactly(ok):
    fake = FakeClient()
    result = pick_titles(fake, ok)
    assert result["ok"] is True
    assert result["max_minutes"] == float(ok)
    for _, kwargs in fake.calls:
        assert kwargs["max_minutes"] == float(ok)
        assert isinstance(kwargs["max_minutes"], float)  # never truncated to int


def test_sub_minute_limit_is_not_truncated_to_zero_or_one():
    fake = FakeClient()
    pick_titles(fake, 0.75)
    assert {kw["max_minutes"] for _, kw in fake.calls} == {0.75}


# --- tier order, dedup, limits ----------------------------------------------------------


def test_tiers_are_resume_then_next_up_then_unwatched():
    fake = FakeClient(
        resume=answer([resume_rec(1)]),
        next_up=answer([episode_rec(2)]),
        unwatched=answer([rec(3)]),
    )
    result = pick_titles(fake, 60)
    assert ids(result) == [iid(1), iid(2), iid(3)]
    assert [p["source"] for p in result["picks"]] == ["resume", "next_up", "unwatched"]
    assert result["complete"] is True


def test_at_most_three_compact_picks_and_later_calls_skipped_when_full():
    fake = FakeClient(resume=answer([resume_rec(n) for n in range(1, 8)]))
    result = pick_titles(fake, 60)
    assert len(result["picks"]) == MAX_PICKS == 3
    assert [name for name, _ in fake.calls] == ["resume"]
    assert result["sources"]["next_up"] == {"status": "skipped", "reason": "enough_picks"}
    assert result["sources"]["unwatched"]["status"] == "skipped"
    assert result["complete"] is True


def test_limit_argument_caps_picks():
    fake = FakeClient(unwatched=answer([rec(n) for n in range(1, 10)]))
    assert len(pick_titles(fake, 60, limit=2)["picks"]) == 2
    assert len(pick_titles(fake, 60, limit=1)["picks"]) == 1


def test_every_client_call_is_bounded_and_made_at_most_once():
    fake = FakeClient()
    pick_titles(fake, 60)
    assert [name for name, _ in fake.calls] == ["resume", "next_up", "unwatched"]
    limits = [kw["limit"] for _, kw in fake.calls]
    assert all(isinstance(n, int) and 1 <= n <= 25 for n in limits)
    unwatched = fake.calls[2][1]
    assert unwatched["unwatched_only"] is True
    assert set(unwatched["item_types"]) == {"Movie", "Video"}


def test_duplicate_ids_keep_the_highest_priority_tier():
    shared = iid(7)
    fake = FakeClient(
        resume=answer([resume_rec(7, remaining=12)]),
        next_up=answer([episode_rec(7, item_id=shared), episode_rec(2)]),
        unwatched=answer([rec(7, title="Seven"), rec(3)]),
    )
    result = pick_titles(fake, 60)
    assert ids(result) == [shared, iid(2), iid(3)]
    by_id = {p["item_id"]: p["source"] for p in result["picks"]}
    assert by_id[shared] == "resume"
    assert result["sources"]["next_up"]["duplicates"] == 1
    assert result["sources"]["unwatched"]["duplicates"] == 1


def test_duplicate_ids_inside_one_tier_appear_once():
    fake = FakeClient(unwatched=answer([rec(1, title="Zed"), rec(1, title="Alpha"), rec(2)]))
    result = pick_titles(fake, 60)
    assert ids(result).count(iid(1)) == 1
    assert len(result["picks"]) == 2


def test_series_and_season_records_are_never_picked():
    fake = FakeClient(
        resume=answer([resume_rec(1, type="Series"), resume_rec(2, type="Season")]),
        next_up=answer([episode_rec(3, type="Series")]),
        unwatched=answer([rec(4, type="Series"), rec(5, type="Season"), rec(6, type="Episode")]),
    )
    result = pick_titles(fake, 60)
    assert result["picks"] == []
    assert result["sources"]["resume"]["rejected"] == 2
    assert result["sources"]["unwatched"]["rejected"] == 3


def test_video_and_episode_picks_are_allowed():
    fake = FakeClient(
        resume=answer([resume_rec(1, type="Video"), resume_rec(2, type="Episode")]),
        unwatched=answer([rec(3, type="Video")]),
    )
    result = pick_titles(fake, 60)
    assert [p["type"] for p in result["picks"]] == ["Video", "Episode", "Video"]


# --- ranking and deterministic ties -----------------------------------------------------


def test_resume_closest_to_finished_first_then_furthest_in_then_title_then_id():
    fake = FakeClient(
        resume=answer(
            [
                resume_rec(1, remaining=40),
                resume_rec(2, remaining=5, position_s=300, title="beta"),
                resume_rec(3, remaining=5, position_s=900, title="zzz"),  # further in: first
                resume_rec(5, remaining=5, position_s=300, title="alpha"),  # same title as 4
                resume_rec(4, remaining=5, position_s=300, title="alpha"),  # full tie: id 4 < 5
            ]
        )
    )
    result = pick_titles(fake, 60, limit=3)
    assert ids(result) == [iid(3), iid(4), iid(5)]


def test_next_up_orders_by_series_season_episode():
    def ep(n, series, season, episode):
        return episode_rec(
            n, series_name=series, season_number=season, episode_number=episode, title=f"t{n}"
        )

    fake = FakeClient(
        next_up=answer(
            [
                ep(1, "beta show", 1, 1),
                ep(2, "Alpha Show", 2, 5),
                ep(3, "Alpha Show", 2, 3),
                ep(4, "Alpha Show", 1, 9),
            ]
        )
    )
    result = pick_titles(fake, 60, limit=3)
    assert ids(result) == [iid(4), iid(3), iid(2)]


def test_unwatched_best_fill_first_then_title_then_id():
    fake = FakeClient(
        unwatched=answer(
            [
                rec(1, minutes=30, title="b"),
                rec(2, minutes=55, title="z"),
                rec(3, minutes=30, title="a"),
                rec(5, minutes=30, title="b"),
            ]
        )
    )
    result = pick_titles(fake, 60, limit=3)
    assert ids(result) == [iid(2), iid(3), iid(1)]


@pytest.mark.parametrize("order", [1, -1])
def test_ranking_ignores_input_order(order):
    items = [rec(n, minutes=10 + (n % 3), title=f"T{n % 2}") for n in range(1, 9)]
    fake = FakeClient(unwatched=answer(items[::order]))
    baseline = pick_titles(FakeClient(unwatched=answer(items)), 60)
    assert ids(pick_titles(fake, 60)) == ids(baseline)


def test_same_input_gives_identical_output():
    def build():
        return FakeClient(
            resume=answer([resume_rec(n, remaining=10) for n in range(1, 4)]),
            unwatched=answer([rec(n) for n in range(10, 15)]),
        )

    assert pick_titles(build(), 45) == pick_titles(build(), 45)


# --- runtime evidence --------------------------------------------------------------------


def test_unknown_or_invalid_runtime_can_never_be_picked():
    bad_unwatched = [
        rec(1, minutes=None),
        rec(2, minutes=0),
        rec(3, minutes=-4),
        rec(4, minutes=True),
        rec(5, minutes="30"),
        rec(6, minutes=12.5),
        rec(7),  # control: valid
    ]
    bad_resume = [
        resume_rec(11, remaining=None),
        resume_rec(12, remaining=0),
        resume_rec(13, remaining=True),
        resume_rec(14, remaining="9"),
    ]
    fake = FakeClient(resume=answer(bad_resume), unwatched=answer(bad_unwatched))
    result = pick_titles(fake, 60)
    assert ids(result) == [iid(7)]
    assert result["sources"]["resume"]["rejected"] == 4
    assert result["sources"]["unwatched"]["rejected"] == 6


def test_resume_without_remaining_time_is_not_judged_by_full_runtime():
    # `minutes` fits, but remaining time is unknown: cannot prove the fit.
    record = resume_rec(1, remaining=None)
    record["minutes"] = 5
    assert pick_titles(FakeClient(resume=answer([record])), 60)["picks"] == []


def test_resume_is_judged_by_remaining_not_full_runtime():
    # 100 min film, 70 min watched: 30 min left fits a 45 min window.
    record = resume_rec(1, remaining=30, position_s=70 * 60)
    assert record["minutes"] == 100
    assert ids(pick_titles(FakeClient(resume=answer([record])), 45)) == [iid(1)]


def test_new_items_are_judged_by_full_runtime():
    record = rec(1, minutes=100)
    assert pick_titles(FakeClient(unwatched=answer([record])), 45)["picks"] == []


def test_records_provably_over_the_limit_are_dropped_even_if_client_ignored_it():
    fake = FakeClient(
        unwatched=answer([rec(1, minutes=12), rec(2, minutes=10), rec(3, minutes=11)])
    )
    # shown 11 could be 10.5 (> 10): provably over; shown 10 could be 9.5..10.49 (may fit).
    result = pick_titles(fake, 10)
    assert ids(result) == [iid(2)]


def test_rounded_display_minutes_do_not_reject_a_true_fit():
    # A 9.6 minute film is shown as 10; it fits a 9.7 minute limit.
    fake = FakeClient(unwatched=answer([rec(1, minutes=10)]))
    assert ids(pick_titles(fake, 9.7)) == [iid(1)]


def test_sub_minute_item_shown_as_one_minute_is_kept_for_sub_minute_limit():
    fake = FakeClient(unwatched=answer([rec(1, minutes=1)]))
    assert ids(pick_titles(fake, 0.5)) == [iid(1)]  # true length decided by the client


def test_not_unwatched_or_already_played_are_rejected():
    fake = FakeClient(
        resume=answer([resume_rec(1, played=True), resume_rec(2, resume_seconds=0)]),
        next_up=answer([episode_rec(3, played=True)]),
        unwatched=answer(
            [rec(4, played=True), rec(5, played=None), rec(6, played="false"), rec(7)]
        ),
    )
    assert ids(pick_titles(fake, 60)) == [iid(7)]


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "str",
        42,
        {},
        {"item_id": "", "title": "x", "type": "Movie"},
        {"item_id": 5, "title": "x", "type": "Movie"},
        {"item_id": iid(1), "title": "", "type": "Movie", "minutes": 5, "played": False},
        {"item_id": iid(1), "title": "   ", "type": "Movie", "minutes": 5, "played": False},
        {"item_id": iid(1), "title": "x", "type": None, "minutes": 5, "played": False},
    ],
)
def test_malformed_records_are_rejected_and_counted(bad):
    result = pick_titles(FakeClient(unwatched=answer([bad, rec(9)])), 60)
    assert ids(result) == [iid(9)]
    assert result["sources"]["unwatched"]["rejected"] == 1


# --- evidence-based reasons --------------------------------------------------------------


def test_resume_reason_quotes_returned_position_and_remaining():
    fake = FakeClient(
        resume=answer([resume_rec(1, remaining=6, position_s=9 * 60, title="Sintel")])
    )
    pick = pick_titles(fake, 15)["picks"][0]
    assert pick["why"] == (
        "You're 9 min in on Sintel (Jellyfin has it unfinished), about 6 min left, "
        "within your 15 min."
    )
    assert pick["remaining_minutes"] == 6
    assert pick["minutes"] == 15


def test_resume_reason_with_under_a_minute_position_does_not_invent_minutes():
    fake = FakeClient(resume=answer([resume_rec(1, position_s=40)]))
    assert "just started" in pick_titles(fake, 60)["picks"][0]["why"]


def test_next_up_reason_names_series_and_numbers_from_evidence():
    fake = FakeClient(
        next_up=answer(
            [
                episode_rec(
                    1,
                    remaining=22,
                    title="Pilot",
                    series_name="Show",
                    season_number=2,
                    episode_number=4,
                )
            ]
        )
    )
    pick = pick_titles(fake, 30)["picks"][0]
    assert pick["why"] == (
        "Jellyfin lists Show S2E4: Pilot as your next episode; about 22 min, within your 30 min."
    )
    assert (pick["series"], pick["season"], pick["episode"]) == ("Show", 2, 4)


def test_next_up_without_series_info_falls_back_to_title_only():
    record = episode_rec(1, series_name=None, season_number=None, episode_number=None, title="Solo")
    pick = pick_titles(FakeClient(next_up=answer([record])), 60)["picks"][0]
    assert pick["why"] == (
        "Jellyfin lists Solo as your next episode; about 25 min, within your 60 min."
    )


def test_unwatched_reason_uses_only_returned_genres_and_runtime():
    fake = FakeClient(
        unwatched=answer(
            [
                rec(1, title="Spring", minutes=8, genres=["Sci-Fi", "Short", "Horror", "Extra"]),
                rec(2, title="Plain", minutes=7, genres=[]),
            ]
        )
    )
    first, second = pick_titles(fake, 10.5)["picks"]
    assert first["why"] == (
        "Not watched yet in Jellyfin: Spring, about 8 min, within your 10.5 min. "
        "It's tagged Sci-Fi, Short, Horror."
    )
    assert second["why"] == "Not watched yet in Jellyfin: Plain, about 7 min, within your 10.5 min."


def test_reasons_never_claim_history_beyond_the_tier():
    fake = FakeClient(unwatched=answer([rec(1, genres=["Comedy"])]))
    why = pick_titles(fake, 60)["picks"][0]["why"].lower()
    for invented in ("you finished", "you love", "favorite", "favourite", "you watched"):
        assert invented not in why


def test_server_text_is_sanitised_into_one_bounded_line():
    nasty = "Evil\nTitle\x00\x1b[31m" + "x" * 500
    fake = FakeClient(unwatched=answer([rec(1, title=nasty, genres=["A\nB"])]))
    pick = pick_titles(fake, 60)["picks"][0]
    assert "\n" not in pick["why"] and "\x00" not in pick["why"] and "\x1b" not in pick["why"]
    assert len(pick["title"]) <= 80
    assert pick["why"].count("\n") == 0


def test_pick_shape_is_compact():
    fake = FakeClient(unwatched=answer([rec(1, genres=["Comedy"])]))
    pick = pick_titles(fake, 60)["picks"][0]
    assert set(pick) == {"item_id", "title", "type", "year", "minutes", "source", "why"}


# --- errors, partial and truncated results ------------------------------------------------


def jf_error(reason: str) -> JellyfinError:
    return JellyfinError(reason, f"hint for {reason}")


def test_all_sources_failing_is_an_error_not_an_empty_list():
    fake = FakeClient(
        resume=jf_error("jellyfin_bad_response"),
        next_up=jf_error("jellyfin_server_error"),
        unwatched=jf_error("not_found"),
    )
    result = pick_titles(fake, 60)
    assert result["ok"] is False
    assert result["reason"] == "jellyfin_bad_response"
    assert result["hint"] == "hint for jellyfin_bad_response"
    assert [e["source"] for e in result["errors"]] == ["resume", "next_up", "unwatched"]
    assert "picks" not in result
    assert result["complete"] is False


@pytest.mark.parametrize(
    "reason",
    [
        "jellyfin_unreachable",
        "jellyfin_auth",
        "jellyfin_forbidden",
        "jellyfin_config",
        "jellyfin_user_ambiguous",
        "jellyfin_user_not_found",
        "client_closed",
        "jellyfin_redirect",
    ],
)
def test_server_wide_failure_stops_further_calls_and_propagates(reason):
    fake = FakeClient(resume=jf_error(reason))
    result = pick_titles(fake, 60)
    assert result["ok"] is False and result["reason"] == reason
    assert [name for name, _ in fake.calls] == ["resume"]
    assert result["sources"]["next_up"]["status"] == "not_attempted"
    assert result["sources"]["unwatched"]["status"] == "not_attempted"


def test_endpoint_failure_does_not_block_other_sources_and_is_reported():
    fake = FakeClient(resume=jf_error("jellyfin_bad_response"), unwatched=answer([rec(1)]))
    result = pick_titles(fake, 60)
    assert result["ok"] is True
    assert ids(result) == [iid(1)]
    assert result["complete"] is False
    assert result["errors"] == [
        {
            "source": "resume",
            "reason": "jellyfin_bad_response",
            "hint": "hint for jellyfin_bad_response",
        }
    ]
    assert result["sources"]["resume"]["status"] == "error"
    assert "Partial" in result["note"]


def test_failure_after_good_picks_keeps_them_and_flags_incomplete():
    fake = FakeClient(
        resume=answer([resume_rec(1)]),
        next_up=jf_error("jellyfin_unreachable"),
    )
    result = pick_titles(fake, 60)
    assert result["ok"] is True and ids(result) == [iid(1)]
    assert result["complete"] is False
    assert result["errors"][0]["reason"] == "jellyfin_unreachable"
    assert [name for name, _ in fake.calls] == ["resume", "next_up"]  # unwatched not attempted
    assert result["sources"]["unwatched"]["status"] == "not_attempted"


@pytest.mark.parametrize("payload", [[], "x", {"items": None}, {"items": "no"}, {}])
def test_malformed_client_answer_is_a_bad_response_error(payload):
    fake = FakeClient(resume=payload, next_up=payload, unwatched=payload)
    result = pick_titles(fake, 60)
    assert result["ok"] is False
    assert result["reason"] == "jellyfin_bad_response"
    assert len(result["errors"]) == 3


def test_truncation_is_propagated_even_with_picks():
    fake = FakeClient(unwatched=answer([rec(1)], truncated=True, scanned=250))
    result = pick_titles(fake, 60)
    assert result["truncated"] is True
    assert result["complete"] is True
    assert result["sources"]["unwatched"]["truncated"] is True
    assert result["sources"]["unwatched"]["scanned"] == 250


def test_empty_and_truncated_is_not_reported_as_nothing_exists():
    fake = FakeClient(unwatched=answer([], truncated=True))
    result = pick_titles(fake, 60)
    assert result["ok"] is True and result["picks"] == []
    assert result["truncated"] is True
    assert "limit" in result["note"]


def test_empty_complete_library_says_nothing_fits():
    result = pick_titles(FakeClient(), 12.5)
    assert result["ok"] is True and result["picks"] == []
    assert result["complete"] is True and result["truncated"] is False
    assert "12.5" in result["note"]


def test_client_skip_counters_are_passed_through_when_sane():
    fake = FakeClient(
        unwatched=answer([rec(1)], skipped_unknown_runtime=4, skipped_filtered=2, scanned="x")
    )
    source = pick_titles(fake, 60)["sources"]["unwatched"]
    assert source["skipped_unknown_runtime"] == 4
    assert source["skipped_filtered"] == 2
    assert "scanned" not in source


def test_unexpected_exceptions_are_not_swallowed():
    class Boom(FakeClient):
        def get_resume_items(self, **kw):
            raise RuntimeError("bug")

    with pytest.raises(RuntimeError):
        pick_titles(Boom(), 60)


# --- real JellyfinClient + respx ----------------------------------------------------------


def raw(n: int, **kw: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "Id": iid(n),
        "Name": f"Title {n}",
        "Type": "Movie",
        "ProductionYear": 2010,
        "RunTimeTicks": 30 * MIN,
        "Genres": ["Comedy"],
        "UserData": {"Played": False, "PlaybackPositionTicks": 0},
    }
    data.update(kw)
    return data


def page(items: list[Any]) -> dict[str, Any]:
    return {"Items": items, "TotalRecordCount": len(items), "StartIndex": 0}


@pytest.fixture
def api():
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.get(f"/Users/{USER_ID}").respond(json={"Id": USER_ID, "Name": "Ann"})
        router.get("/UserItems/Resume").respond(json=page([]))
        router.get("/Shows/NextUp").respond(json=page([]))
        router.get("/Items").respond(json=page([]))
        yield router


@pytest.fixture
def jf(api):
    with JellyfinClient(BASE, KEY, USER_ID) as client:
        yield client


def test_real_client_end_to_end_field_mapping(api, jf):
    api.get("/UserItems/Resume").respond(
        json=page(
            [
                raw(
                    1,
                    Name="Sintel",
                    RunTimeTicks=15 * MIN,
                    UserData={"Played": False, "PlaybackPositionTicks": 9 * MIN},
                )
            ]
        )
    )
    api.get("/Shows/NextUp").respond(
        json=page(
            [
                raw(
                    2,
                    Name="Chapter Two",
                    Type="Episode",
                    RunTimeTicks=22 * MIN,
                    SeriesId=iid(50),
                    SeriesName="Big Show",
                    ParentIndexNumber=1,
                    IndexNumber=2,
                )
            ]
        )
    )
    api.get("/Items").respond(
        json=page([raw(3, Name="Spring", RunTimeTicks=8 * MIN, Genres=["Short", "Sci-Fi"])])
    )
    result = pick_titles(jf, 30)
    assert result["ok"] is True and result["complete"] is True
    assert [p["source"] for p in result["picks"]] == ["resume", "next_up", "unwatched"]
    resume, nxt, new = result["picks"]
    assert resume["why"] == (
        "You're 9 min in on Sintel (Jellyfin has it unfinished), about 6 min left, "
        "within your 30 min."
    )
    assert (resume["minutes"], resume["remaining_minutes"]) == (15, 6)
    assert nxt["why"].startswith("Jellyfin lists Big Show S1E2: Chapter Two as your next episode")
    assert (nxt["series"], nxt["season"], nxt["episode"]) == ("Big Show", 1, 2)
    assert new["why"] == (
        "Not watched yet in Jellyfin: Spring, about 8 min, within your 30 min. "
        "It's tagged Short, Sci-Fi."
    )
    assert new["year"] == 2010


def test_real_client_query_parameters(api, jf):
    pick_titles(jf, 42.5)
    seen = {
        "/UserItems/Resume": None,
        "/Shows/NextUp": None,
        "/Items": None,
    }
    for call in api.calls:
        path = call.request.url.path
        if path in seen:
            seen[path] = dict(call.request.url.params)
    assert all(v is not None for v in seen.values())
    assert seen["/UserItems/Resume"]["limit"] == "50"  # client page size, bounded by pages
    items = seen["/Items"]
    assert items["isPlayed"] == "false"
    assert items["includeItemTypes"] == "Movie,Video"
    assert items["userId"] == USER_ID
    total = [c for c in api.calls if c.request.url.path != f"/Users/{USER_ID}"]
    assert len(total) == 3  # one page each: empty library


def test_real_client_exact_boundary_new_items(api, jf):
    api.get("/Items").respond(
        json=page(
            [
                raw(1, Name="Exact", RunTimeTicks=45 * MIN),
                raw(2, Name="One tick over", RunTimeTicks=45 * MIN + 1),
                raw(3, Name="Unknown", RunTimeTicks=None),
                raw(4, Name="Zero", RunTimeTicks=0),
            ]
        )
    )
    result = pick_titles(jf, 45)
    assert [p["title"] for p in result["picks"]] == ["Exact"]
    assert result["sources"]["unwatched"]["skipped_unknown_runtime"] == 2
    assert result["sources"]["unwatched"]["skipped_filtered"] == 1


def test_real_client_sub_minute_limits_are_exact_not_truncated(api, jf):
    # 0.5 min == 30 s. The client shows both of these as "1 minute".
    api.get("/Items").respond(
        json=page(
            [
                raw(1, Name="Thirty seconds", RunTimeTicks=30 * 10_000_000),
                raw(2, Name="Thirty seconds and a tick", RunTimeTicks=30 * 10_000_000 + 1),
                raw(3, Name="Ninety seconds", RunTimeTicks=90 * 10_000_000),
            ]
        )
    )
    result = pick_titles(jf, 0.5)
    assert [p["title"] for p in result["picks"]] == ["Thirty seconds"]
    assert result["picks"][0]["minutes"] == 1


def test_real_client_rounding_does_not_reject_fit_or_accept_overrun(api, jf):
    # Limit 9.7 min = 582 s. 9.6 min (576 s) shows as 10 and fits; 9.8 min (588 s) shows as 10
    # and must not.
    api.get("/Items").respond(
        json=page(
            [
                raw(1, Name="Fits", RunTimeTicks=576 * 10_000_000),
                raw(2, Name="Over", RunTimeTicks=588 * 10_000_000),
            ]
        )
    )
    result = pick_titles(jf, 9.7)
    assert [p["title"] for p in result["picks"]] == ["Fits"]
    assert result["picks"][0]["minutes"] == 10


def test_real_client_resume_uses_remaining_time_exactly(api, jf):
    api.get("/UserItems/Resume").respond(
        json=page(
            [
                # 100 min total, 70 min in: exactly 30 min left -> fits 30
                raw(
                    1,
                    Name="Exact left",
                    RunTimeTicks=100 * MIN,
                    UserData={"Played": False, "PlaybackPositionTicks": 70 * MIN},
                ),
                # one tick more left than the limit -> excluded
                raw(
                    2,
                    Name="Tick too long",
                    RunTimeTicks=100 * MIN + 1,
                    UserData={"Played": False, "PlaybackPositionTicks": 70 * MIN},
                ),
                # full length is long, but only 5 min left
                raw(
                    3,
                    Name="Almost done",
                    RunTimeTicks=200 * MIN,
                    UserData={"Played": False, "PlaybackPositionTicks": 195 * MIN},
                ),
                raw(
                    4,
                    Name="No runtime",
                    RunTimeTicks=None,
                    UserData={"Played": False, "PlaybackPositionTicks": 5 * MIN},
                ),
            ]
        )
    )
    result = pick_titles(jf, 30)
    assert [p["title"] for p in result["picks"]] == ["Almost done", "Exact left"]
    assert [p["remaining_minutes"] for p in result["picks"]] == [5, 30]
    assert result["sources"]["resume"]["skipped_unknown_runtime"] == 1


def test_real_client_series_season_and_played_never_picked(api, jf):
    api.get("/Items").respond(
        json=page(
            [
                raw(1, Name="A Series", Type="Series"),
                raw(2, Name="A Season", Type="Season"),
                raw(3, Name="Seen", UserData={"Played": True, "PlaybackPositionTicks": 0}),
                raw(4, Name="No user data", UserData=None),
                raw(5, Name="Good"),
            ]
        )
    )
    result = pick_titles(jf, 60)
    assert [p["title"] for p in result["picks"]] == ["Good"]


def test_real_client_duplicate_across_resume_and_next_up(api, jf):
    started = raw(
        7,
        Name="Ep Seven",
        Type="Episode",
        SeriesId=iid(50),
        SeriesName="Show",
        ParentIndexNumber=1,
        IndexNumber=7,
        RunTimeTicks=40 * MIN,
        UserData={"Played": False, "PlaybackPositionTicks": 30 * MIN},
    )
    api.get("/UserItems/Resume").respond(json=page([started]))
    api.get("/Shows/NextUp").respond(json=page([started, raw(8, Type="Episode", SeriesId=iid(51))]))
    result = pick_titles(jf, 60)
    assert [p["item_id"] for p in result["picks"]] == [iid(7), iid(8)]
    assert result["picks"][0]["source"] == "resume"
    assert result["sources"]["next_up"]["duplicates"] == 1


def test_real_client_scan_truncation_is_reported(api, jf):
    def too_long_pages(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["startIndex"])
        items = [raw(start + n + 1, RunTimeTicks=600 * MIN) for n in range(50)]  # all too long
        return httpx.Response(200, json={"Items": items, "TotalRecordCount": 10_000})

    api.get("/Items").mock(side_effect=too_long_pages)
    result = pick_titles(jf, 10)
    assert result["ok"] is True and result["picks"] == []
    assert result["truncated"] is True
    assert result["sources"]["unwatched"]["truncated"] is True
    assert result["sources"]["unwatched"]["scanned"] == 250
    assert "limit" in result["note"]


@pytest.mark.parametrize(
    ("status", "reason"),
    [(401, "jellyfin_auth"), (403, "jellyfin_forbidden"), (500, "jellyfin_server_error")],
)
def test_real_client_http_failures_become_structured_errors(api, jf, status, reason):
    api.get("/UserItems/Resume").respond(status)
    result = pick_titles(jf, 60)
    assert result["ok"] is False
    assert result["reason"] == reason
    assert result["hint"]
    assert KEY not in repr(result)


def test_real_client_unreachable_stops_after_first_call(api, jf):
    api.get("/UserItems/Resume").mock(side_effect=httpx.ConnectError("down"))
    result = pick_titles(jf, 60)
    assert result["ok"] is False and result["reason"] == "jellyfin_unreachable"
    assert not [c for c in api.calls if c.request.url.path == "/Items"]
    assert result["sources"]["unwatched"]["status"] == "not_attempted"


def test_real_client_non_global_failure_still_gives_partial_picks(api, jf):
    api.get("/UserItems/Resume").respond(500)
    api.get("/Items").respond(json=page([raw(1, Name="Still here")]))
    result = pick_titles(jf, 60)
    assert result["ok"] is True and result["complete"] is False
    assert [p["title"] for p in result["picks"]] == ["Still here"]
    assert result["errors"][0]["reason"] == "jellyfin_server_error"


def test_real_client_malformed_page_is_an_error_not_no_picks(api, jf):
    api.get("/Items").respond(json={"Items": "nope"})
    result = pick_titles(jf, 60)
    assert result["ok"] is False
    assert result["reason"] == "jellyfin_bad_response"
