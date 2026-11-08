"""Tests for hermes_screen.jellyfin. All HTTP is mocked with respx: no network,
no Jellyfin server and no Roku are ever contacted."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import respx

from hermes_screen.jellyfin import (
    MAX_LIMIT,
    MAX_PAGES,
    PAGE_SIZE,
    JellyfinClient,
    JellyfinError,
)

BASE = "http://jf.test:8096"
KEY = "s3cr3t-api-key-0123456789abcdef"
USER_ID = "11111111111111111111111111111111"
OTHER_USER_ID = "22222222222222222222222222222222"
ITEM = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OTHER_ITEM = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
NOW = datetime(2026, 11, 8, 12, 0, 0, tzinfo=UTC)
MIN = 600_000_000  # ticks per minute


def iid(n: int) -> str:
    return f"{n:032x}"


def item(n: int, **kw: Any) -> dict[str, Any]:
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


def page(items: list[Any], total: int | None = None, start: int = 0) -> dict[str, Any]:
    return {
        "Items": items,
        "TotalRecordCount": len(items) if total is None else total,
        "StartIndex": start,
    }


def stamp(delta_s: float) -> str:
    when = NOW + timedelta(seconds=delta_s)
    return when.strftime("%Y-%m-%dT%H:%M:%S.%f") + "0Z"  # Jellyfin: 7 digits


def session(**kw: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "Id": "sess-1",
        "UserId": USER_ID,
        "UserName": "Ann",
        "Client": "Jellyfin Roku",
        "DeviceId": "roku-living-room",
        "DeviceName": "Living Room (Roku Ultra)",
        "LastPlaybackCheckIn": stamp(-5),
        "IsActive": True,
        "NowPlayingItem": {"Id": ITEM, "Name": "Sintel"},
        "PlayState": {"IsPaused": False, "PositionTicks": 90 * 10_000_000},
    }
    data.update(kw)
    return data


@pytest.fixture
def api():
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.get(f"/Users/{USER_ID}").respond(json={"Id": USER_ID, "Name": "Ann"})
        yield router


@pytest.fixture
def jf(api):
    with JellyfinClient(BASE, KEY, USER_ID) as client:
        yield client


def calls(route: respx.Route) -> list[httpx.Request]:
    return [c.request for c in route.calls]


def q(request: httpx.Request) -> dict[str, str]:
    return dict(request.url.params)


# --- construction and transport ------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "jf.test:8096",
        "ftp://jf.test",
        "http://",
        "http://user:pw@jf.test",
        "http://jf.test?x=1",
        "http://jf.test#frag",
        "http://jf.test:99999",
        "http://jf.test/a b",
        None,
        42,
    ],
)
def test_bad_base_url_is_rejected(url):
    with pytest.raises(JellyfinError) as exc:
        JellyfinClient(url, KEY)
    assert exc.value.reason == "jellyfin_config"


@pytest.mark.parametrize("key", ["", "   ", None, "has space", "new\nline", "x" * 600])
def test_bad_api_key_is_rejected(key):
    with pytest.raises(JellyfinError) as exc:
        JellyfinClient(BASE, key)
    assert exc.value.reason == "jellyfin_config"


def test_bad_user_setting_is_rejected():
    with pytest.raises(JellyfinError):
        JellyfinClient(BASE, KEY, "  ")


def test_repr_hides_key():
    client = JellyfinClient(BASE, KEY)
    assert KEY not in repr(client)
    assert KEY not in str(client)
    client.close()


@pytest.mark.parametrize(
    "base",
    [
        "https://media.test/jellyfin",
        "https://media.test/jellyfin/",
        "https://media.test/a/b///",
    ],
)
def test_subpath_servers_are_joined_safely(base):
    prefix = base.rstrip("/")
    with respx.mock(assert_all_called=False) as router:
        route = router.get(f"{prefix}/System/Info/Public").respond(
            json={"ServerName": "Home", "Version": "10.10.7"}
        )
        with JellyfinClient(base, KEY) as client:
            assert client.server_info()["name"] == "Home"
        assert route.call_count == 1


def test_auth_header_has_token_and_public_info_has_none(api, jf):
    public = api.get("/System/Info/Public").respond(
        json={"ServerName": "Home", "Version": "10.10.7", "Id": "abc"}
    )
    sessions = api.get("/Sessions").respond(json=[])
    assert jf.server_info() == {"name": "Home", "version": "10.10.7", "id": "abc"}
    assert "authorization" not in calls(public)[0].headers  # public call: no key sent

    jf.verify_playback(ITEM, device_id="roku-living-room")
    header = calls(sessions)[0].headers["authorization"]
    assert header.startswith("MediaBrowser ")
    assert f'Token="{KEY}"' in header


def test_token_in_header_is_percent_encoded():
    with respx.mock(base_url=BASE) as router:
        route = router.get("/Sessions").respond(json=[])
        with JellyfinClient(BASE, 'ab"c,d=e') as client:
            client.verify_playback(ITEM, device_id="x")
        header = calls(route)[0].headers["authorization"]
        assert 'Token="ab%22c%2Cd%3De"' in header


def test_every_request_has_explicit_8s_timeouts(api, jf):
    route = api.get("/Items").respond(json=page([item(1)]))
    sessions = api.get("/Sessions").respond(json=[])
    public = api.get("/System/Info/Public").respond(
        json={"ServerName": "Home", "Version": "10"}
    )
    jf.find_items()
    jf.verify_playback(ITEM, device_id="d")
    jf.server_info()
    for r in (route, sessions, public):
        for request in calls(r):
            timeout = request.extensions["timeout"]
            assert timeout == {"connect": 8.0, "read": 8.0, "write": 8.0, "pool": 8.0}


def test_redirects_are_not_followed(api, jf):
    api.get("/Items").respond(302, headers={"Location": "https://elsewhere.test/Items"})
    other = respx.get("https://elsewhere.test/Items").respond(json=page([]))
    with pytest.raises(JellyfinError) as exc:
        jf.find_items()
    assert exc.value.reason == "jellyfin_redirect"
    assert other.call_count == 0  # the key never leaves the configured host


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (400, "jellyfin_bad_request"),
        (401, "jellyfin_auth"),
        (403, "jellyfin_forbidden"),
        (404, "not_found"),
        (500, "jellyfin_server_error"),
        (503, "jellyfin_server_error"),
    ],
)
def test_http_errors_are_structured_and_do_not_leak_key(api, jf, status, reason):
    api.get("/Items").respond(status, text=f"boom {KEY}")
    with pytest.raises(JellyfinError) as exc:
        jf.find_items()
    err = exc.value
    assert err.reason == reason
    assert err.hint
    assert KEY not in str(err) and KEY not in repr(err.to_dict())
    assert err.to_dict() == {"ok": False, "reason": reason, "hint": err.hint}


@pytest.mark.parametrize(
    "boom",
    [
        httpx.ConnectError("refused"),
        httpx.ReadTimeout("slow"),
        httpx.ConnectTimeout("t"),
    ],
)
def test_network_failures_are_unreachable(api, jf, boom):
    api.get("/Items").mock(side_effect=boom)
    with pytest.raises(JellyfinError) as exc:
        jf.find_items()
    assert exc.value.reason == "jellyfin_unreachable"
    assert KEY not in str(exc.value)


@pytest.mark.parametrize(
    "body", [b"<html>nginx</html>", b"", b"\xff\xfe", b'{"Items": ']
)
def test_non_json_is_bad_response(api, jf, body):
    api.get("/Items").respond(200, content=body)
    with pytest.raises(JellyfinError) as exc:
        jf.find_items()
    assert exc.value.reason == "jellyfin_bad_response"


def test_oversized_response_is_rejected(api, jf):
    api.get("/Items").respond(200, content=b"[" + b"0," * (3 * 1024 * 1024) + b"0]")
    with pytest.raises(JellyfinError) as exc:
        jf.find_items()
    assert exc.value.reason == "jellyfin_bad_response"


def test_closed_client_refuses_requests(api):
    client = JellyfinClient(BASE, KEY, USER_ID)
    client.close()
    client.close()  # idempotent
    with pytest.raises(JellyfinError) as exc:
        client.server_info()
    assert exc.value.reason == "client_closed"


def test_context_manager_closes(api):
    with JellyfinClient(BASE, KEY, USER_ID) as client:
        pass
    with pytest.raises(JellyfinError):
        client.server_info()


# --- status -----------------------------------------------------------------------------


def test_status_ok(api, jf):
    api.get("/System/Info/Public").respond(
        json={"ServerName": "Home", "Version": "10.10.7"}
    )
    api.get("/Items/Counts").respond(
        json={"MovieCount": 12, "SeriesCount": 3, "EpisodeCount": 40, "SongCount": 9}
    )
    result = jf.status()
    assert result == {
        "ok": True,
        "server": {"name": "Home", "version": "10.10.7"},
        "user": {"id": USER_ID, "name": "Ann"},
        "counts": {"movies": 12, "series": 3, "episodes": 40},
    }


def test_status_counts_are_best_effort(api, jf):
    api.get("/System/Info/Public").respond(json={"ServerName": "Home", "Version": "10"})
    api.get("/Items/Counts").respond(500)
    result = jf.status()
    assert result["ok"] is True and "counts" not in result


def test_status_counts_ignore_garbage(api, jf):
    api.get("/System/Info/Public").respond(json={"ServerName": "Home", "Version": "10"})
    api.get("/Items/Counts").respond(json={"MovieCount": "12", "SeriesCount": -1})
    assert "counts" not in jf.status()


def test_status_auth_failure_is_data_not_exception(api, jf):
    api.get("/System/Info/Public").respond(json={"ServerName": "Home", "Version": "10"})
    api.get(f"/Users/{USER_ID}").respond(401)
    result = jf.status()
    assert result["ok"] is False and result["reason"] == "jellyfin_auth"
    assert set(result) == {"ok", "reason", "hint"}
    assert KEY not in repr(result)


def test_status_counts_auth_failure_is_reported(api, jf):
    api.get("/System/Info/Public").respond(json={"ServerName": "Home", "Version": "10"})
    api.get("/Items/Counts").respond(403)
    assert jf.status()["reason"] == "jellyfin_forbidden"


def test_status_unreachable(api, jf):
    api.get("/System/Info/Public").mock(side_effect=httpx.ConnectError("no"))
    assert jf.status()["reason"] == "jellyfin_unreachable"


@pytest.mark.parametrize(
    "payload",
    [
        [],
        "nope",
        {},
        {"ServerName": "Home"},
        {"Version": "10"},
        {"ServerName": "", "Version": "10"},
        {"ServerName": 5, "Version": "10"},
    ],
)
def test_status_malformed_server_info(api, jf, payload):
    api.get("/System/Info/Public").respond(json=payload)
    result = jf.status()
    assert result["ok"] is False and result["reason"] == "jellyfin_bad_response"


def test_status_user_ambiguity_is_reported(api):
    api.get("/System/Info/Public").respond(json={"ServerName": "Home", "Version": "10"})
    api.get("/Users").respond(
        json=[{"Id": USER_ID, "Name": "Ann"}, {"Id": OTHER_USER_ID, "Name": "Bob"}]
    )
    with JellyfinClient(BASE, KEY) as client:
        result = client.status()
    assert result["reason"] == "jellyfin_user_ambiguous"
    assert "Ann" in result["hint"] and "Bob" in result["hint"]


# --- user resolution --------------------------------------------------------------------


def test_single_enabled_user_is_resolved_and_cached(api):
    users = api.get("/Users").respond(json=[{"Id": USER_ID, "Name": "Ann"}])
    with JellyfinClient(BASE, KEY) as client:
        assert client.resolve_user() == {"id": USER_ID, "name": "Ann"}
        client.resolve_user()
    assert users.call_count == 1
    assert q(calls(users)[0]) == {"isDisabled": "false"}


def test_ambiguous_users_fail_instead_of_picking_first(api):
    api.get("/Users").respond(
        json=[{"Id": USER_ID, "Name": "Ann"}, {"Id": OTHER_USER_ID, "Name": "Bob"}]
    )
    with JellyfinClient(BASE, KEY) as client, pytest.raises(JellyfinError) as exc:
        client.find_items()
    assert exc.value.reason == "jellyfin_user_ambiguous"


def test_no_users(api):
    api.get("/Users").respond(json=[])
    with JellyfinClient(BASE, KEY) as client, pytest.raises(JellyfinError) as exc:
        client.resolve_user()
    assert exc.value.reason == "jellyfin_user_not_found"


@pytest.mark.parametrize(
    "payload", [{"Items": []}, ["x", 1], [{"Id": "nope", "Name": "A"}]]
)
def test_malformed_user_list(api, payload):
    api.get("/Users").respond(json=payload)
    with JellyfinClient(BASE, KEY) as client, pytest.raises(JellyfinError) as exc:
        client.resolve_user()
    assert exc.value.reason == "jellyfin_bad_response"


def test_user_by_dashed_id_is_normalised_and_verified(api):
    dashed = "11111111-1111-1111-1111-111111111111"
    route = api.get(f"/Users/{USER_ID}").respond(json={"Id": dashed, "Name": "Ann"})
    with JellyfinClient(BASE, KEY, dashed.upper()) as client:
        assert client.resolve_user()["id"] == USER_ID
    assert route.call_count == 1


def test_user_id_mismatch_in_response_is_rejected(api):
    api.get(f"/Users/{USER_ID}").respond(json={"Id": OTHER_USER_ID, "Name": "Bob"})
    with (
        JellyfinClient(BASE, KEY, USER_ID) as client,
        pytest.raises(JellyfinError) as exc,
    ):
        client.resolve_user()
    assert exc.value.reason == "jellyfin_bad_response"


def test_unknown_user_id_is_not_found(api):
    api.get(f"/Users/{USER_ID}").respond(404)
    with (
        JellyfinClient(BASE, KEY, USER_ID) as client,
        pytest.raises(JellyfinError) as exc,
    ):
        client.resolve_user()
    assert exc.value.reason == "not_found"


def test_user_by_name_matches_exactly_ignoring_case_and_accents(api):
    api.get("/Users").respond(
        json=[
            {"Id": USER_ID, "Name": "José"},
            {"Id": OTHER_USER_ID, "Name": "Jose Two"},
        ]
    )
    with JellyfinClient(BASE, KEY, "jose") as client:
        assert client.resolve_user() == {"id": USER_ID, "name": "José"}


def test_user_name_not_found_and_duplicate_names(api):
    api.get("/Users").respond(
        json=[{"Id": USER_ID, "Name": "Ann"}, {"Id": OTHER_USER_ID, "Name": "ann"}]
    )
    with (
        JellyfinClient(BASE, KEY, "zed") as client,
        pytest.raises(JellyfinError) as exc,
    ):
        client.resolve_user()
    assert exc.value.reason == "jellyfin_user_not_found"
    with (
        JellyfinClient(BASE, KEY, "Ann") as client,
        pytest.raises(JellyfinError) as exc,
    ):
        client.resolve_user()
    assert exc.value.reason == "jellyfin_user_ambiguous"


# --- find_items -------------------------------------------------------------------------------


def test_find_items_sends_expected_query_and_shapes_results(api, jf):
    route = api.get("/Items").respond(
        json=page(
            [
                item(
                    1,
                    Name="Sintel",
                    ProductionYear=2010,
                    RunTimeTicks=15 * MIN,
                    Genres=["Animation", "Fantasy", 7],
                )
            ]
        )
    )
    result = jf.find_items(
        "sintel",
        genres=["animation", "Comedy"],
        max_minutes=20,
        unwatched_only=True,
        limit=3,
    )
    params = q(calls(route)[0])
    assert params["userId"] == USER_ID
    assert params["includeItemTypes"] == "Movie,Series"
    assert params["searchTerm"] == "sintel"
    assert params["genres"] == "animation|Comedy"
    assert params["isPlayed"] == "false"
    assert params["recursive"] == "true"
    assert params["startIndex"] == "0" and params["limit"] == str(PAGE_SIZE)
    assert "sortBy" not in params  # relevance order when searching
    assert result["items"] == [
        {
            "item_id": iid(1),
            "title": "Sintel",
            "type": "Movie",
            "year": 2010,
            "minutes": 15,
            "genres": ["Animation", "Fantasy"],
            "played": False,
        }
    ]
    assert result["truncated"] is False and result["scanned"] == 1


def test_find_items_sorts_by_name_without_query(api, jf):
    route = api.get("/Items").respond(json=page([]))
    jf.find_items()
    assert q(calls(route)[0])["sortBy"] == "SortName"
    assert "searchTerm" not in q(calls(route)[0])


def test_runtime_filter_is_strict_even_if_server_ignores_it(api, jf):
    api.get("/Items").respond(
        json=page(
            [
                item(1, RunTimeTicks=45 * MIN),  # exactly on the limit: kept
                item(2, RunTimeTicks=45 * MIN + 1),  # one tick over: dropped
                item(3, RunTimeTicks=None),  # unknown: cannot prove it fits
                item(4),  # 30m: kept
                item(5, RunTimeTicks=0),  # nonsense runtime: unknown
                item(6, RunTimeTicks="1800000000"),  # wrong type: unknown
                item(7, RunTimeTicks=True),  # bool is not an int here
                item(8, RunTimeTicks=-5),
            ]
        )
    )
    result = jf.find_items(max_minutes=45)
    assert [i["item_id"] for i in result["items"]] == [iid(1), iid(4)]
    assert result["skipped_unknown_runtime"] == 5
    assert result["skipped_filtered"] == 1


def test_unknown_runtime_is_kept_when_no_runtime_filter(api, jf):
    api.get("/Items").respond(json=page([item(1, RunTimeTicks=None)]))
    result = jf.find_items()
    assert result["items"][0]["minutes"] is None


def test_server_returning_wrong_types_is_filtered(api, jf):
    api.get("/Items").respond(
        json=page(
            [item(1, Type="Episode"), item(2, Type="Movie"), item(3, Type="Audio")]
        )
    )
    assert [i["item_id"] for i in jf.find_items()["items"]] == [iid(2)]
    api.get("/Items").respond(json=page([item(1, Type="Episode"), item(2)]))
    result = jf.find_items(item_types=["episode"])
    assert [i["item_id"] for i in result["items"]] == [iid(1)]


def test_unwatched_requires_explicit_unplayed(api, jf):
    api.get("/Items").respond(
        json=page(
            [
                item(1, UserData={"Played": True}),
                item(2, UserData=None),
                item(3, UserData={}),
                item(4, UserData={"Played": "false"}),
                item(5, UserData={"Played": False}),
            ]
        )
    )
    assert [i["item_id"] for i in jf.find_items(unwatched_only=True)["items"]] == [
        iid(5)
    ]


def test_genres_are_rechecked_case_insensitively(api, jf):
    api.get("/Items").respond(
        json=page(
            [
                item(1, Genres=["Drama"]),
                item(2, Genres=["COMEDY"]),
                item(3, Genres=None),
            ]
        )
    )
    assert [i["item_id"] for i in jf.find_items(genres=["comedy"])["items"]] == [iid(2)]


def test_runtime_gap_across_pages_is_paged_through(api, jf):
    long_page = page(
        [item(n, RunTimeTicks=200 * MIN) for n in range(1, PAGE_SIZE + 1)], total=80
    )
    short_page = page(
        [item(n) for n in range(PAGE_SIZE + 1, 81)], total=80, start=PAGE_SIZE
    )
    route = api.get("/Items").mock(
        side_effect=lambda request: httpx.Response(
            200, json=long_page if q(request)["startIndex"] == "0" else short_page
        )
    )
    result = jf.find_items(max_minutes=60, limit=5)
    assert [q(r)["startIndex"] for r in calls(route)] == ["0", str(PAGE_SIZE)]
    assert [i["item_id"] for i in result["items"]] == [iid(n) for n in range(51, 56)]
    assert result["scanned"] == 55
    assert result["skipped_filtered"] == 55 - 5
    assert result["truncated"] is True  # 25 more candidates were left unread


def test_scan_is_bounded_and_flagged_truncated(api, jf):
    total = PAGE_SIZE * (MAX_PAGES + 4)
    route = api.get("/Items").mock(
        side_effect=lambda request: httpx.Response(
            200,
            json=page(
                [
                    item(n, RunTimeTicks=300 * MIN)
                    for n in range(
                        int(q(request)["startIndex"]) + 1,
                        int(q(request)["startIndex"]) + PAGE_SIZE + 1,
                    )
                ],
                total=total,
            ),
        )
    )
    result = jf.find_items(max_minutes=10)
    assert route.call_count == MAX_PAGES
    assert result["items"] == [] and result["truncated"] is True
    assert result["scanned"] == PAGE_SIZE * MAX_PAGES


def test_server_ignoring_start_index_cannot_loop(api, jf):
    same = page([item(n) for n in range(1, PAGE_SIZE + 1)], total=500)
    route = api.get("/Items").respond(json=same)
    result = jf.find_items(max_minutes=1)  # nothing fits, so paging continues
    assert route.call_count == 2  # second page added no new ids: stop
    assert result["items"] == []


def test_limit_is_respected_and_reports_more(api, jf):
    api.get("/Items").respond(json=page([item(n) for n in range(1, 11)], total=10))
    result = jf.find_items(limit=3)
    assert len(result["items"]) == 3 and result["truncated"] is True
    api.get("/Items").respond(json=page([item(n) for n in range(1, 4)], total=3))
    assert jf.find_items(limit=3)["truncated"] is False


def test_limit_is_capped(api, jf):
    api.get("/Items").respond(json=page([item(n) for n in range(1, 40)], total=39))
    assert len(jf.find_items(limit=1000)["items"]) == MAX_LIMIT


def test_empty_library(api, jf):
    api.get("/Items").respond(json=page([]))
    assert jf.find_items("zzz") == {
        "items": [],
        "scanned": 0,
        "truncated": False,
        "skipped_unknown_runtime": 0,
        "skipped_malformed": 0,
        "skipped_filtered": 0,
    }


def test_duplicates_and_malformed_items_are_skipped_and_counted(api, jf):
    api.get("/Items").respond(
        json=page(
            [
                item(1),
                item(1),
                "garbage",
                None,
                {"Name": "no id", "Type": "Movie"},
                item(2, Id="not-a-guid"),
                item(3, Name=""),
                item(4, Type=None),
                item(5, ProductionYear="2010", Genres="Comedy"),
            ]
        )
    )
    result = jf.find_items()
    assert [i["item_id"] for i in result["items"]] == [iid(1), iid(5)]
    assert result["skipped_malformed"] == 6
    assert result["items"][1]["year"] is None and result["items"][1]["genres"] == []


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"Items": "nope"},
        {"NoItems": []},
        {"Items": ["x", 5, None]},
        "string",
    ],
)
def test_malformed_item_pages_are_bad_responses(api, jf, payload):
    api.get("/Items").respond(json=payload)
    with pytest.raises(JellyfinError) as exc:
        jf.find_items()
    assert exc.value.reason == "jellyfin_bad_response"


def test_garbage_total_record_count_does_not_break_paging(api, jf):
    api.get("/Items").respond(json={"Items": [item(1)], "TotalRecordCount": "many"})
    assert len(jf.find_items()["items"]) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0},
        {"limit": -1},
        {"limit": True},
        {"limit": 2.5},
        {"max_minutes": 0},
        {"max_minutes": -3},
        {"max_minutes": float("nan")},
        {"max_minutes": float("inf")},
        {"max_minutes": True},
        {"max_minutes": "45"},
        {"max_minutes": 10_000},
        {"item_types": ["Song"]},
        {"item_types": []},
        {"item_types": [5]},
        {"genres": ["a|b"]},
        {"genres": [""]},
        {"genres": ["g"] * 11},
        {"genres": [3]},
    ],
)
def test_invalid_arguments_are_rejected_before_any_request(api, jf, kwargs):
    route = api.get("/Items").respond(json=page([]))
    with pytest.raises(JellyfinError) as exc:
        jf.find_items(**kwargs)
    assert exc.value.reason == "invalid_argument"
    assert route.call_count == 0


def test_invalid_query_text(api, jf):
    with pytest.raises(JellyfinError):
        jf.find_items("x" * 500)
    with pytest.raises(JellyfinError):
        jf.find_items(123)  # type: ignore[arg-type]
    route = api.get("/Items").respond(json=page([]))
    jf.find_items("  \n ")  # whitespace only means "no query"
    assert "searchTerm" not in q(calls(route)[0])


def test_string_arguments_are_accepted_as_single_values(api, jf):
    route = api.get("/Items").respond(json=page([]))
    jf.find_items(item_types="movie", genres="Comedy")
    assert q(calls(route)[0])["includeItemTypes"] == "Movie"
    assert q(calls(route)[0])["genres"] == "Comedy"


# --- get_item ------------------------------------------------------------------------------------


def test_get_item(api, jf):
    route = api.get(f"/Items/{ITEM}").respond(
        json=item(
            int(ITEM, 16),
            Type="Episode",
            SeriesId=iid(9),
            SeriesName="Show",
            ParentIndexNumber=2,
            IndexNumber=4,
        )
    )
    result = jf.get_item(ITEM.upper())
    assert q(calls(route)[0]) == {"userId": USER_ID}
    assert result["type"] == "Episode" and result["item_id"] == ITEM
    assert result["series_id"] == iid(9) and result["season_number"] == 2
    assert result["episode_number"] == 4 and result["series_name"] == "Show"


def test_get_item_not_found_and_invalid(api, jf):
    api.get(f"/Items/{ITEM}").respond(404)
    with pytest.raises(JellyfinError) as exc:
        jf.get_item(ITEM)
    assert exc.value.reason == "not_found"
    for bad in ["", "../Users", "abc", None, f"{ITEM}/Delete", 5]:
        with pytest.raises(JellyfinError) as exc:
            jf.get_item(bad)  # type: ignore[arg-type]
        assert exc.value.reason == "invalid_argument"


def test_get_item_wrong_id_in_response_is_bad_response(api, jf):
    api.get(f"/Items/{ITEM}").respond(json=item(1))
    with pytest.raises(JellyfinError) as exc:
        jf.get_item(ITEM)
    assert exc.value.reason == "jellyfin_bad_response"
    api.get(f"/Items/{ITEM}").respond(json=["x"])
    with pytest.raises(JellyfinError):
        jf.get_item(ITEM)


# --- resume and next up ----------------------------------------------------------------------------


def test_resume_items_are_rechecked(api, jf):
    route = api.get("/UserItems/Resume").respond(
        json=page(
            [
                item(
                    1,
                    UserData={
                        "Played": False,
                        "PlaybackPositionTicks": 9 * 60 * 10_000_000,
                    },
                ),
                item(
                    2, UserData={"Played": True, "PlaybackPositionTicks": 5_000_000_000}
                ),
                item(3, UserData={"Played": False, "PlaybackPositionTicks": 0}),
                item(4, UserData=None),
                item(
                    5, Type="Audio", UserData={"PlaybackPositionTicks": 5_000_000_000}
                ),
            ]
        )
    )
    result = jf.get_resume_items()
    assert q(calls(route)[0])["userId"] == USER_ID
    assert q(calls(route)[0])["mediaTypes"] == "Video"
    assert [i["item_id"] for i in result["items"]] == [iid(1)]
    first = result["items"][0]
    assert first["resume_seconds"] == 540 and first["remaining_minutes"] == 21


def test_resume_runtime_limit_applies_to_remaining_time(api, jf):
    pos = 40 * MIN
    api.get("/UserItems/Resume").respond(
        json=page(
            [
                item(
                    1, RunTimeTicks=90 * MIN, UserData={"PlaybackPositionTicks": pos}
                ),  # 50m left
                item(
                    2, RunTimeTicks=60 * MIN, UserData={"PlaybackPositionTicks": pos}
                ),  # 20m left
                item(3, RunTimeTicks=None, UserData={"PlaybackPositionTicks": pos}),
            ]
        )
    )
    result = jf.get_resume_items(max_minutes=30)
    assert [i["item_id"] for i in result["items"]] == [iid(2)]
    assert result["items"][0]["remaining_minutes"] == 20
    assert result["skipped_unknown_runtime"] == 1


def test_next_up_filters_series_and_played(api, jf):
    series = iid(900)
    route = api.get("/Shows/NextUp").respond(
        json=page(
            [
                item(
                    1,
                    Type="Episode",
                    SeriesId=series,
                    SeriesName="Show",
                    ParentIndexNumber=1,
                    IndexNumber=3,
                ),
                item(2, Type="Episode", SeriesId=iid(901)),
                item(3, Type="Episode", SeriesId=series, UserData={"Played": True}),
                item(4, Type="Movie", SeriesId=series),
                item(5, Type="Episode", SeriesId=None),
            ]
        )
    )
    result = jf.get_next_up(series.upper())
    params = q(calls(route)[0])
    assert params["seriesId"] == series and params["enableRewatching"] == "false"
    assert [i["item_id"] for i in result["items"]] == [iid(1)]
    assert result["items"][0]["episode_number"] == 3
    assert result["items"][0]["remaining_minutes"] == 30


def test_next_up_without_series_and_bad_series_id(api, jf):
    route = api.get("/Shows/NextUp").respond(json=page([item(1, Type="Episode")]))
    assert len(jf.get_next_up()["items"]) == 1
    assert "seriesId" not in q(calls(route)[0])
    with pytest.raises(JellyfinError) as exc:
        jf.get_next_up("../x")
    assert exc.value.reason == "invalid_argument"


def test_resume_and_next_up_surface_auth_errors(api, jf):
    api.get("/UserItems/Resume").respond(401)
    api.get("/Shows/NextUp").respond(500)
    with pytest.raises(JellyfinError) as exc:
        jf.get_resume_items()
    assert exc.value.reason == "jellyfin_auth"
    with pytest.raises(JellyfinError) as exc:
        jf.get_next_up()
    assert exc.value.reason == "jellyfin_server_error"


# --- verify_playback: the evidence rules ---------------------------------------------------------------


def verify(subject: JellyfinClient, api, sessions: Any, **kw: Any) -> dict[str, Any]:
    api.get("/Sessions").respond(json=sessions)
    kw.setdefault("device_id", "roku-living-room")
    kw.setdefault("now", NOW)
    return subject.verify_playback(ITEM, **kw)


def test_verified_when_item_device_user_and_freshness_all_match(api, jf):
    result = verify(jf, api, [session()])
    assert (
        result["ok"] is True and result["verified"] is True and result["reason"] is None
    )
    assert result["playing"] is True and result["paused"] is False
    assert result["position_s"] == 90
    assert result["now_playing"] == {"item_id": ITEM, "title": "Sintel"}
    assert result["session"]["device_name"] == "Living Room (Roku Ultra)"
    assert result["session"]["check_in_age_s"] == 5
    assert result["matched_sessions"] == 1


def test_query_asks_server_for_the_device_only(api, jf):
    route = api.get("/Sessions").respond(json=[session()])
    jf.verify_playback(ITEM.upper(), device_id="roku-living-room", now=NOW)
    assert q(calls(route)[0]) == {"deviceId": "roku-living-room"}


def test_paused_on_the_right_item_is_verified_but_not_playing(api, jf):
    result = verify(
        jf, api, [session(PlayState={"IsPaused": True, "PositionTicks": 0})]
    )
    assert (
        result["verified"] is True
        and result["playing"] is False
        and result["paused"] is True
    )


def test_missing_play_state_is_verified_but_playing_unknown(api, jf):
    result = verify(jf, api, [session(PlayState=None)])
    assert result["verified"] is True and result["playing"] is None
    assert result["position_s"] is None


def test_same_title_different_item_id_is_not_verified(api, jf):
    result = verify(
        jf, api, [session(NowPlayingItem={"Id": OTHER_ITEM, "Name": "Sintel"})]
    )
    assert result["verified"] is False and result["reason"] == "wrong_item"
    assert result["now_playing"] == {"item_id": OTHER_ITEM, "title": "Sintel"}
    assert result["playing"] is None


def test_other_devices_playing_the_item_never_count(api, jf):
    other = session(DeviceId="roku-bedroom", DeviceName="Bedroom (Roku Express)")
    result = verify(jf, api, [other])
    assert result["verified"] is False and result["reason"] == "no_session"


def test_first_matching_session_is_not_special(api, jf):
    """Bedroom plays the item; the target (living room) plays something else."""
    bedroom = session(DeviceId="roku-bedroom", DeviceName="Bedroom (Roku Express)")
    target = session(NowPlayingItem={"Id": OTHER_ITEM, "Name": "Spring"})
    result = verify(jf, api, [bedroom, target])
    assert result["verified"] is False and result["reason"] == "wrong_item"
    result = verify(jf, api, [target, bedroom])
    assert result["reason"] == "wrong_item"


def test_ambiguous_device_name_is_unverified(api):
    a = session(DeviceId="roku-1", DeviceName="Roku Ultra (Roku Ultra)")
    b = session(DeviceId="roku-2", DeviceName="Roku Ultra (Roku Ultra)", Id="sess-2")
    with JellyfinClient(BASE, KEY) as client:
        result = verify(client, api, [a, b], device_id=None, device_name="Roku Ultra")
    assert result["verified"] is False and result["reason"] == "ambiguous_session"
    assert result["matched_sessions"] == 2


def test_device_id_disambiguates_when_names_collide(api):
    a = session(DeviceId="roku-1", DeviceName="Roku (Ultra)", NowPlayingItem=None)
    b = session(DeviceId="roku-2", DeviceName="Roku (Ultra)", Id="sess-2")
    with JellyfinClient(BASE, KEY) as client:
        result = verify(client, api, [a, b], device_id="roku-2", device_name="Roku")
    assert result["verified"] is True


def test_device_name_accepts_full_or_bare_roku_name_only(api):
    with JellyfinClient(BASE, KEY) as client:
        for name in ("Living Room (Roku Ultra)", "living room", "LIVING ROOM"):
            assert verify(client, api, [session()], device_id=None, device_name=name)[
                "verified"
            ]
        for name in ("Living", "Living Room (Roku Express)", "Room", "Roku Ultra"):
            result = verify(client, api, [session()], device_id=None, device_name=name)
            assert result["reason"] == "no_session", name


def test_device_id_must_match_exactly(api, jf):
    result = verify(jf, api, [session(DeviceId="ROKU-LIVING-ROOM")])
    assert result["reason"] == "no_session"


def test_other_client_on_same_device_does_not_count(api, jf):
    result = verify(jf, api, [session(Client="Jellyfin Web")])
    assert result["reason"] == "no_session"
    # explicitly opting out of the client check is allowed
    assert (
        verify(jf, api, [session(Client="Jellyfin Web")], client=None)["verified"]
        is True
    )


def test_identity_is_required(api, jf):
    route = api.get("/Sessions").respond(json=[session()])
    for kwargs in ({}, {"device_id": ""}, {"device_name": "  "}, {"device_id": None}):
        with pytest.raises(JellyfinError) as exc:
            jf.verify_playback(ITEM, **kwargs)
        assert exc.value.reason == "invalid_argument"
    assert route.call_count == 0


@pytest.mark.parametrize("bad", ["", "nope", None, "../Sessions", 7])
def test_invalid_item_id(api, jf, bad):
    with pytest.raises(JellyfinError):
        jf.verify_playback(bad, device_id="x")  # type: ignore[arg-type]


@pytest.mark.parametrize("age", [0, True, -1, float("nan"), "60"])
def test_invalid_max_age(api, jf, age):
    with pytest.raises(JellyfinError):
        jf.verify_playback(ITEM, device_id="x", max_age_seconds=age)  # type: ignore[arg-type]


def test_configured_user_must_match(api, jf):
    result = verify(jf, api, [session(UserId=OTHER_USER_ID, UserName="Bob")])
    assert result["verified"] is False and result["reason"] == "wrong_user"


@pytest.mark.parametrize("user_id", [None, "", "nope", 5])
def test_session_without_a_usable_user_fails_when_user_configured(api, jf, user_id):
    result = verify(jf, api, [session(UserId=user_id)])
    assert result["reason"] == "wrong_user"


def test_user_is_not_checked_when_none_configured(api):
    with JellyfinClient(BASE, KEY) as client:  # no user_id: no /Users lookup either
        result = verify(client, api, [session(UserId=OTHER_USER_ID)])
    assert result["verified"] is True


def test_other_users_session_on_same_device_does_not_cause_ambiguity(api, jf):
    mine = session()
    theirs = session(UserId=OTHER_USER_ID, Id="sess-2")
    assert verify(jf, api, [theirs, mine])["verified"] is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"LastPlaybackCheckIn": stamp(-61)},
        {"LastPlaybackCheckIn": "0001-01-01T00:00:00.0000000Z"},
        {"LastPlaybackCheckIn": None},
        {"LastPlaybackCheckIn": "yesterday"},
        {"LastPlaybackCheckIn": 12345},
        {"LastPlaybackCheckIn": stamp(+3600)},  # from the future
        {"IsActive": False},
    ],
)
def test_stale_or_unusable_timestamps_are_unverified(api, jf, overrides):
    result = verify(jf, api, [session(**overrides)])
    assert result["verified"] is False and result["reason"] == "stale_session"


def test_missing_timestamp_key_is_stale(api, jf):
    data = session()
    del data["LastPlaybackCheckIn"]
    assert verify(jf, api, [data])["reason"] == "stale_session"


def test_freshness_window_edges(api, jf):
    assert (
        verify(jf, api, [session(LastPlaybackCheckIn=stamp(-60))])["verified"] is True
    )
    assert (
        verify(jf, api, [session(LastPlaybackCheckIn=stamp(-61))])["verified"] is False
    )
    assert verify(
        jf, api, [session(LastPlaybackCheckIn=stamp(-90))], max_age_seconds=120
    )["verified"]
    assert verify(jf, api, [session(LastPlaybackCheckIn=stamp(+3))])["verified"] is True


def test_stale_duplicate_of_target_does_not_block_fresh_session(api, jf):
    old = session(Id="old", LastPlaybackCheckIn=stamp(-4000), NowPlayingItem=None)
    assert verify(jf, api, [old, session()])["verified"] is True


def test_stale_session_cannot_verify_even_with_right_item(api, jf):
    result = verify(jf, api, [session(LastPlaybackCheckIn=stamp(-600))])
    assert result["verified"] is False
    assert result["now_playing"] is None  # stale claims are not relayed as evidence


def test_server_date_header_is_the_clock_not_local_time(api, jf):
    """Fixtures are in 2026-11-08; the local clock is irrelevant when Date is sent."""
    api.get("/Sessions").respond(
        json=[session()], headers={"Date": "Sun, 08 Nov 2026 12:00:00 GMT"}
    )
    assert jf.verify_playback(ITEM, device_id="roku-living-room")["verified"] is True
    api.get("/Sessions").respond(
        json=[session()], headers={"Date": "Sun, 08 Nov 2026 13:00:00 GMT"}
    )
    result = jf.verify_playback(ITEM, device_id="roku-living-room")
    assert result["reason"] == "stale_session"


def test_without_date_header_falls_back_to_local_clock(api, jf):
    real_now = datetime.now(UTC)

    def at(delta_s: float) -> str:
        return (real_now + timedelta(seconds=delta_s)).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        ) + "0Z"

    fresh = session(LastPlaybackCheckIn=at(-5))
    api.get("/Sessions").respond(json=[fresh])
    assert jf.verify_playback(ITEM, device_id="roku-living-room")["verified"] is True
    api.get("/Sessions").respond(json=[session(LastPlaybackCheckIn=at(-300))])
    result = jf.verify_playback(ITEM, device_id="roku-living-room")
    assert result["reason"] == "stale_session"


def test_nothing_playing_is_unverified(api, jf):
    result = verify(
        jf, api, [session(NowPlayingItem=None, PlayState={"IsPaused": False})]
    )
    assert result["verified"] is False and result["reason"] == "nothing_playing"
    result = verify(jf, api, [session(NowPlayingItem=None)])
    assert result["session"]["device_name"] == "Living Room (Roku Ultra)"


def test_absent_key_nowplaying_is_unverified(api, jf):
    data = session()
    del data["NowPlayingItem"]
    assert verify(jf, api, [data])["reason"] == "nothing_playing"


@pytest.mark.parametrize(
    "now_playing",
    [{"Name": "Sintel"}, {"Id": "x", "Name": "Sintel"}, {"Id": 5}, "Sintel", [], 7],
)
def test_malformed_now_playing_is_unverified(api, jf, now_playing):
    result = verify(jf, api, [session(NowPlayingItem=now_playing)])
    assert result["verified"] is False and result["reason"] == "malformed_evidence"


@pytest.mark.parametrize("payload", [{"Items": []}, "x", 5, {}])
def test_non_list_sessions_payload_is_unverified(api, jf, payload):
    result = verify(jf, api, payload)
    assert result["verified"] is False and result["reason"] == "malformed_evidence"


def test_any_garbage_session_entry_poisons_the_evidence(api, jf):
    result = verify(jf, api, [session(), "garbage"])
    assert result["verified"] is False and result["reason"] == "malformed_evidence"


def test_no_sessions_at_all(api, jf):
    result = verify(jf, api, [])
    assert result["verified"] is False and result["reason"] == "no_session"
    assert result["session"] is None and result["now_playing"] is None


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        (lambda r: r.get("/Sessions").respond(401), "jellyfin_auth"),
        (lambda r: r.get("/Sessions").respond(500), "jellyfin_server_error"),
        (
            lambda r: r.get("/Sessions").mock(side_effect=httpx.ConnectError("x")),
            "jellyfin_unreachable",
        ),
        (
            lambda r: r.get("/Sessions").mock(side_effect=httpx.ReadTimeout("x")),
            "jellyfin_unreachable",
        ),
        (
            lambda r: r.get("/Sessions").respond(200, content=b"<html>"),
            "jellyfin_bad_response",
        ),
    ],
)
def test_transport_failures_are_never_verified_and_do_not_raise(api, jf, setup, reason):
    setup(api)
    result = jf.verify_playback(ITEM, device_id="roku-living-room", now=NOW)
    assert result["verified"] is False and result["ok"] is False
    assert result["reason"] == reason and result["hint"]
    assert KEY not in repr(result)


def test_user_lookup_failure_during_verify_is_unverified(api):
    api.get(f"/Users/{USER_ID}").respond(401)
    with JellyfinClient(BASE, KEY, USER_ID) as client:
        result = client.verify_playback(ITEM, device_id="x", now=NOW)
    assert result["verified"] is False and result["ok"] is False
    assert result["reason"] == "jellyfin_auth"


def test_scan_of_sessions_is_bounded(api, jf):
    many = [session(DeviceId=f"d{n}", Id=f"s{n}") for n in range(500)]
    target = session(DeviceId="late")
    result = verify(jf, api, many + [target], device_id="late")
    assert result["verified"] is False  # beyond the cap there is no evidence


def test_position_defaults_are_sane(api, jf):
    result = verify(
        jf, api, [session(PlayState={"IsPaused": False, "PositionTicks": -5})]
    )
    assert result["verified"] is True and result["position_s"] is None
    result = verify(jf, api, [session(PlayState={"IsPaused": "no"})])
    assert result["verified"] is True and result["playing"] is None


def test_item_id_comparison_ignores_case_and_dashes(api, jf):
    dashed = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    result = verify(
        jf, api, [session(NowPlayingItem={"Id": dashed.upper(), "Name": "S"})]
    )
    assert result["verified"] is True
