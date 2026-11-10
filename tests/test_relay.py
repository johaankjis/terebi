"""MediaRelay: a real local listener on 127.0.0.1, upstream Jellyfin mocked by respx.

The test client uses http.client (not httpx), so respx only intercepts the
relay's own upstream requests. No LAN, Chromecast or Jellyfin is contacted.
"""

from __future__ import annotations

import http.client
import socket
import threading
import time

import httpx
import pytest
import respx

from hermes_screen.relay import (
    MAX_STREAMS,
    MAX_TTL_S,
    MIN_TTL_S,
    MediaRelay,
    RelayError,
    parse_bind,
    redact,
    ttl_for,
)

KEY = "relay-secret-key-ABC123"
AUTH = f'MediaBrowser Client="Hermes Screen", Token="{KEY}"'
ITEM = "e5d6c471a8a4ea26e00a3694f91bf8d1"
UPSTREAM = f"http://jf.test:8096/Videos/{ITEM}/stream?static=true&mediaSourceId={ITEM}"
BODY = bytes(range(256)) * 400  # 102400 bytes


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def relay(clock):
    r = MediaRelay(clock=clock)
    yield r
    r.close()


def mint(relay: MediaRelay, ttl: float = 600.0, item: str = ITEM, upstream: str = UPSTREAM):
    cap = relay.mint(
        bind=("127.0.0.1", 0),
        advertised_base="http://192.0.2.10:8765",
        item_id=item,
        upstream_url=upstream,
        auth_header=AUTH,
        ttl_s=ttl,
    )
    return cap


def local_path(cap) -> str:
    return cap.media_url.removeprefix("http://192.0.2.10:8765")


def request(relay, method, path, headers=None, read=True):
    host, port = relay.server_address
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request(method, path, headers=headers or {})
    resp = conn.getresponse()
    body = resp.read() if read else b""
    conn.close()
    return resp, body


def upstream_ok(router, body=BODY):
    def respond(request: httpx.Request) -> httpx.Response:
        rng = request.headers.get("Range")
        if rng is None:
            return httpx.Response(200, headers={"Content-Type": "video/mp4"}, content=body)
        spec = rng.removeprefix("bytes=")
        start_s, end_s = spec.split("-")
        if start_s == "":
            start, end = len(body) - int(end_s), len(body) - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else len(body) - 1
        part = body[start : end + 1]
        return httpx.Response(
            206,
            headers={
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes {start}-{end}/{len(body)}",
                "Set-Cookie": "jf=1",
                "Server": "Kestrel",
                "ETag": '"abc"',
            },
            content=part,
        )

    route = router.route(url=UPSTREAM).mock(side_effect=respond)
    return route


def test_capability_url_shape_and_no_secrets_in_repr(relay):
    cap = mint(relay)
    path = local_path(cap)
    assert path.startswith("/cast/") and path.endswith("/video.mp4")
    assert len(cap.token) == 43 and cap.token in cap.media_url
    assert cap.media_url.startswith("http://192.0.2.10:8765/cast/")
    text = repr(cap)
    assert cap.token not in text and KEY not in text and "jf.test" not in text


def test_full_get_streams_exact_bytes_with_key_only_upstream(relay):
    with respx.mock(assert_all_called=True) as router:
        route = upstream_ok(router)
        cap = mint(relay)
        resp, body = request(relay, "GET", local_path(cap))
    assert resp.status == 200 and body == BODY
    assert resp.getheader("Content-Type") == "video/mp4"
    assert resp.getheader("Accept-Ranges") == "bytes"
    assert resp.getheader("Content-Length") == str(len(BODY))
    upstream = route.calls[0].request
    assert str(upstream.url) == UPSTREAM
    assert upstream.headers["Authorization"] == AUTH
    assert upstream.headers["Accept-Encoding"] == "identity"
    assert "Range" not in upstream.headers
    all_headers = " ".join(f"{k}: {v}" for k, v in resp.getheaders())
    assert KEY not in all_headers and "jf.test" not in all_headers


@pytest.mark.parametrize(
    ("given", "forwarded", "start", "end"),
    [
        ("bytes=0-", "bytes=0-", 0, len(BODY) - 1),
        ("bytes=100-199", "bytes=100-199", 100, 199),
        ("bytes=0100-0199", "bytes=100-199", 100, 199),
        ("bytes=-1000", "bytes=-1000", len(BODY) - 1000, len(BODY) - 1),  # MP4 tail (moov)
    ],
)
def test_single_ranges_are_normalized_and_return_206(relay, given, forwarded, start, end):
    with respx.mock() as router:
        route = upstream_ok(router)
        cap = mint(relay)
        resp, body = request(relay, "GET", local_path(cap), {"Range": given})
    assert route.calls[0].request.headers["Range"] == forwarded
    assert resp.status == 206 and body == BODY[start : end + 1]
    assert resp.getheader("Content-Range") == f"bytes {start}-{end}/{len(BODY)}"
    assert resp.getheader("ETag") == '"abc"'
    assert resp.getheader("Set-Cookie") is None
    assert "Kestrel" not in (resp.getheader("Server") or "")


def test_head_is_forwarded_as_head_without_body(relay):
    with respx.mock() as router:
        route = router.head(UPSTREAM).respond(
            200, headers={"Content-Length": "64657027", "Content-Type": "video/mp4"}
        )
        cap = mint(relay)
        resp, body = request(relay, "HEAD", local_path(cap))
    assert route.calls[0].request.method == "HEAD"
    assert resp.status == 200 and body == b""
    assert resp.getheader("Content-Length") == "64657027"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.replace("/video.mp4", "/other.mp4"),
        lambda p: p + "?x=1",
        lambda p: p + "/",
        lambda p: "/cast/" + "A" * 43 + "/video.mp4",
        lambda p: p.replace("/cast/", "/cast/../"),
        lambda p: "/",
        lambda p: "/cast/",
        lambda p: "/Videos/" + ITEM + "/stream?static=true",
        lambda p: "//evil.test" + p,
        lambda p: p.upper(),
    ],
)
def test_bad_paths_and_unknown_tokens_are_404_without_upstream(relay, mutate):
    with respx.mock(assert_all_called=False) as router:
        route = upstream_ok(router)
        cap = mint(relay)
        resp, body = request(relay, "GET", mutate(local_path(cap)))
    assert resp.status == 404 and body == b""
    assert not route.called


@pytest.mark.parametrize(
    "rng",
    [
        "bytes=0-1,5-6",
        "bytes=10-5",
        "bytes=-0",
        "bytes=abc",
        "items=0-1",
        "bytes=" + "9" * 16 + "-",
        "bytes 0-1",
        "",
    ],
)
def test_malformed_or_multi_ranges_are_416_without_upstream(relay, rng):
    with respx.mock(assert_all_called=False) as router:
        route = upstream_ok(router)
        cap = mint(relay)
        resp, _ = request(relay, "GET", local_path(cap), {"Range": rng})
    assert resp.status == 416
    assert not route.called


def test_two_range_headers_are_416(relay):
    with respx.mock(assert_all_called=False) as router:
        route = upstream_ok(router)
        cap = mint(relay)
        host, port = relay.server_address
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.putrequest("GET", local_path(cap))
        conn.putheader("Range", "bytes=0-1")
        conn.putheader("Range", "bytes=2-3")
        conn.endheaders()
        resp = conn.getresponse()
        resp.read()
        conn.close()
    assert resp.status == 416 and not route.called


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "OPTIONS", "PROPFIND"])
def test_other_methods_are_refused(relay, method):
    with respx.mock(assert_all_called=False) as router:
        route = upstream_ok(router)
        cap = mint(relay)
        resp, body = request(relay, method, local_path(cap))
    assert resp.status == 501
    assert not route.called
    assert cap.token.encode() not in body and KEY.encode() not in body


@pytest.mark.parametrize(
    ("status", "headers", "expected"),
    [
        (302, {"Location": "http://evil.test/steal"}, 502),
        (307, {"Location": "/Videos/x"}, 502),
        (401, {}, 502),
        (403, {}, 502),
        (500, {}, 502),
        (404, {}, 404),
        (416, {"Content-Range": "bytes */102400"}, 416),
    ],
)
def test_upstream_errors_and_redirects_are_not_forwarded(relay, status, headers, expected):
    with respx.mock(assert_all_called=False) as router:
        route = router.get(UPSTREAM).respond(status, headers=headers, content=f"err {KEY}".encode())
        evil = router.get("http://evil.test/steal").respond(200)
        cap = mint(relay)
        resp, body = request(relay, "GET", local_path(cap))
    assert resp.status == expected and body == b""
    assert route.call_count == 1 and not evil.called
    assert resp.getheader("Location") is None
    if expected == 416:
        assert resp.getheader("Content-Range") == "bytes */102400"


def test_upstream_unreachable_is_502(relay):
    with respx.mock() as router:
        router.get(UPSTREAM).mock(side_effect=httpx.ConnectError("boom " + KEY))
        cap = mint(relay)
        resp, body = request(relay, "GET", local_path(cap))
    assert resp.status == 502 and body == b""


def test_expiry_revokes_token_and_releases_port(relay, clock):
    with respx.mock(assert_all_called=False) as router:
        route = upstream_ok(router)
        cap = mint(relay, ttl=600)
        path = local_path(cap)
        assert request(relay, "GET", path)[0].status == 200
        address = relay.server_address
        clock.now += 599
        assert relay.current() is cap
        clock.now += 2
        # A request after the deadline is refused even before the timer fires.
        resp, _ = request(relay, "GET", path)
        assert resp.status == 404
        calls_before = route.call_count
        assert relay.current() is None
    assert cap.revoked and cap.auth_header == ""
    assert not relay.running and relay.server_address is None
    with pytest.raises(OSError):
        socket.create_connection(address, timeout=1).close()
    assert route.call_count == calls_before


def test_timer_expiry_stops_listener_without_any_call():
    relay = MediaRelay()
    try:
        cap = mint(relay, ttl=0.3)
        address = relay.server_address
        deadline = time.monotonic() + 5
        while relay.running and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not relay.running and cap.revoked
        with pytest.raises(OSError):
            socket.create_connection(address, timeout=1).close()
    finally:
        relay.close()


def test_new_capability_revokes_previous_one(relay):
    with respx.mock(assert_all_called=False) as router:
        upstream_ok(router)
        other_upstream = UPSTREAM.replace(ITEM, "c" * 32)
        other = router.get(other_upstream).respond(200, content=b"other")
        first = mint(relay)
        second = mint(relay, item="c" * 32, upstream=other_upstream)
        assert first.revoked and first.token != second.token
        assert request(relay, "GET", local_path(first))[0].status == 404
        resp, body = request(relay, "GET", local_path(second))
    assert resp.status == 200 and body == b"other" and other.call_count == 1
    assert relay.current() is second


class SlowStream(httpx.SyncByteStream):
    def __init__(self, started: threading.Event) -> None:
        self.started = started
        self.closed = threading.Event()

    def __iter__(self):
        for _ in range(2000):
            self.started.set()
            if self.closed.is_set():
                return
            yield b"x" * 65536
            time.sleep(0.02)

    def close(self) -> None:
        self.closed.set()


def test_revoke_cuts_active_stream_and_releases_resources(relay):
    started = threading.Event()
    stream = SlowStream(started)
    with respx.mock() as router:
        router.get(UPSTREAM).mock(return_value=httpx.Response(200, stream=stream))
        cap = mint(relay)
        host, port = relay.server_address
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", local_path(cap))
        resp = conn.getresponse()
        assert resp.status == 200
        resp.read(65536)
        assert started.wait(2)
        t0 = time.monotonic()
        relay.revoke()
        received = 0
        try:
            while chunk := resp.read(65536):
                received += len(chunk)
        except (OSError, http.client.HTTPException):
            pass
        conn.close()
    assert time.monotonic() - t0 < 3
    assert received < 2000 * 65536
    assert stream.closed.wait(2)
    assert not relay.running


def test_concurrent_streams_are_bounded(relay):
    streams = [SlowStream(threading.Event()) for _ in range(MAX_STREAMS)]
    queue = list(streams)
    with respx.mock() as router:
        router.get(UPSTREAM).mock(
            side_effect=lambda request: httpx.Response(200, stream=queue.pop())
        )
        cap = mint(relay)
        host, port = relay.server_address
        held = []
        for _ in range(MAX_STREAMS):
            conn = http.client.HTTPConnection(host, port, timeout=5)
            conn.request("GET", local_path(cap))
            assert conn.getresponse().status == 200
            held.append(conn)
        resp, _ = request(relay, "GET", local_path(cap))
        assert resp.status == 503
        relay.revoke()
        for conn in held:
            conn.close()


def test_nothing_is_logged(relay, capfd, caplog):
    caplog.set_level("DEBUG")
    with respx.mock() as router:
        upstream_ok(router)
        cap = mint(relay)
        request(relay, "GET", local_path(cap))
        request(relay, "GET", local_path(cap) + "x")
        request(relay, "BREW", local_path(cap))
        host, port = relay.server_address
        raw = socket.create_connection((host, port), timeout=2)
        raw.sendall(b"GARBAGE " + cap.token.encode() + b"\r\n\r\n")
        raw.recv(1024)
        raw.close()
    out, err = capfd.readouterr()
    logged = out + err + caplog.text
    assert cap.token not in logged and KEY not in logged


def test_close_releases_port_for_rebind():
    relay = MediaRelay()
    cap = mint(relay)
    address = relay.server_address
    relay.close()
    assert cap.revoked and not relay.running
    again = MediaRelay()
    try:
        again.mint(
            bind=address,
            advertised_base="http://192.0.2.10:8765",
            item_id=ITEM,
            upstream_url=UPSTREAM,
            auth_header=AUTH,
            ttl_s=60,
        )
        assert again.server_address == address
    finally:
        again.close()


def test_bind_failure_is_structured():
    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    try:
        relay = MediaRelay()
        with pytest.raises(RelayError) as exc:
            relay.mint(
                bind=holder.getsockname(),
                advertised_base="http://192.0.2.10:8765",
                item_id=ITEM,
                upstream_url=UPSTREAM,
                auth_header=AUTH,
                ttl_s=60,
            )
        assert exc.value.reason == "relay_bind_failed"
        assert relay.current() is None and not relay.running
    finally:
        holder.close()


def test_ttl_bounds():
    assert ttl_for(None) == 3600
    assert ttl_for(0) == 3600
    assert ttl_for(60) == 960 and ttl_for(1) >= MIN_TTL_S
    assert ttl_for(596.459) == pytest.approx(596.459 + 900)
    assert ttl_for(10 * 3600) == MAX_TTL_S


@pytest.mark.parametrize(
    ("text", "expected"),
    [("0.0.0.0:8765", ("0.0.0.0", 8765)), ("[::]:9000", ("::", 9000))],
)
def test_parse_bind_ok(text, expected):
    assert parse_bind(text) == expected


@pytest.mark.parametrize(
    "text", ["", "8765", "0.0.0.0", "localhost:8765", "0.0.0.0:80", "0.0.0.0:70000", "1.2.3:x"]
)
def test_parse_bind_rejects(text):
    with pytest.raises(RelayError) as exc:
        parse_bind(text)
    assert exc.value.reason == "cast_config"


def test_redact():
    assert redact("GET /cast/abcDEF_-123/video.mp4 x") == "GET /cast/<redacted>/video.mp4 x"
