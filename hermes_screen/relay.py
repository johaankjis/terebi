"""Expiring, item-scoped LAN media relay for the Chromecast.

The Default Media Receiver fetches media over plain HTTP and cannot send the
Jellyfin API key, so this relay serves exactly one validated Jellyfin item at a
random capability URL::

    <advertised base>/cast/<43-char random token>/video.mp4

Security model (see docs/DECISIONS.md once the manager records it):

* The token is 256 bits from :mod:`secrets` and is the only credential: anyone
  on the LAN who learns the URL can fetch that one item until it expires. There
  is no source-IP allowlist because receiver traffic can arrive through a host
  port-forwarding proxy (observed 2026-11-10).
* Only ``GET``/``HEAD`` of that exact path, with no query, and at most one
  single-range ``Range`` header. Everything else is 404/416/501 with an empty
  body; no listing, upload, redirect or general proxying.
* The upstream URL is fixed when the capability is minted (the Jellyfin static
  stream of the selected item) and the API key is sent only there, only in the
  ``Authorization`` header. Upstream redirects are never followed or forwarded.
* Hard expiry: lookups compare against a monotonic deadline, active streams
  check it per chunk, and a timer revokes the capability, closes active streams
  and stops the listener so the port is released. Minting a new capability
  revokes the previous one. ``close()`` does the same on unload.
* Nothing is logged: request and error logging of the HTTP server is disabled
  because request lines contain the token.
* Bounded resources: connection and stream counts, socket and upstream
  timeouts, 64 KiB chunks streamed straight through (never buffered or stored).
"""

from __future__ import annotations

import hmac
import ipaddress
import re
import secrets
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx

__all__ = [
    "MAX_TTL_S",
    "MIN_TTL_S",
    "Capability",
    "MediaRelay",
    "RelayError",
    "redact",
    "ttl_for",
]

TOKEN_BYTES = 32  # 256-bit capability
MIN_TTL_S = 15 * 60
MAX_TTL_S = 4 * 60 * 60
TTL_MARGIN_S = 15 * 60  # pauses, buffering and the receiver's tail fetches
UNKNOWN_RUNTIME_TTL_S = 60 * 60
MAX_CONNECTIONS = 8
MAX_STREAMS = 4
CLIENT_SOCKET_TIMEOUT_S = 30.0
UPSTREAM_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)
CHUNK_BYTES = 64 * 1024
STOP_JOIN_TIMEOUT_S = 3.0

_PATH_RE = re.compile(r"^/cast/([A-Za-z0-9_-]{43})/video\.mp4$")
_RANGE_RE = re.compile(r"^bytes=(?:(\d{1,15})-(\d{0,15})|-(\d{1,15}))$")
_CONTENT_RANGE_RE = re.compile(r"^bytes (?:\d{1,15}-\d{1,15}|\*)/(?:\d{1,15}|\*)$")
_DIGITS_RE = re.compile(r"^\d{1,15}$")
_ETAG_RE = re.compile(r'^(?:W/)?"[\x21\x23-\x7e]{1,128}"$')
_HTTP_DATE_RE = re.compile(r"^[A-Za-z]{3}, \d{2} [A-Za-z]{3} \d{4} \d{2}:\d{2}:\d{2} GMT$")
_TOKEN_TEXT_RE = re.compile(r"/cast/[A-Za-z0-9_-]+")


def redact(text: str) -> str:
    """Replace any capability path in ``text`` with a placeholder."""
    return _TOKEN_TEXT_RE.sub("/cast/<redacted>", text)


def ttl_for(duration_s: float | None) -> float:
    """Capability lifetime for an item: runtime plus margin, within fixed bounds."""
    if duration_s is None or duration_s <= 0:
        return float(UNKNOWN_RUNTIME_TTL_S)
    return float(min(max(duration_s + TTL_MARGIN_S, MIN_TTL_S), MAX_TTL_S))


class RelayError(Exception):
    """A relay failure with a stable reason and a human hint (no secrets)."""

    def __init__(self, reason: str, hint: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.hint = hint


@dataclass(eq=False)
class Capability:
    """One minted, item-scoped capability. Its secrets never appear in ``repr``."""

    token: str = field(repr=False)
    item_id: str
    media_url: str = field(repr=False)
    upstream_url: str = field(repr=False)
    auth_header: str = field(repr=False)
    expires_at: float
    ttl_s: float
    revoked: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _sockets: set[Any] = field(default_factory=set, repr=False)
    _responses: set[Any] = field(default_factory=set, repr=False)

    def valid(self, now: float) -> bool:
        return not self.revoked and now < self.expires_at

    def _attach(self, sock: Any, response: Any) -> bool:
        with self._lock:
            if self.revoked:
                return False
            self._sockets.add(sock)
            self._responses.add(response)
            return True

    def _detach(self, sock: Any, response: Any) -> None:
        with self._lock:
            self._sockets.discard(sock)
            self._responses.discard(response)

    def revoke(self) -> None:
        """Invalidate the token and cut every active stream of this capability."""
        with self._lock:
            self.revoked = True
            self.auth_header = ""
            sockets, responses = list(self._sockets), list(self._responses)
            self._sockets.clear()
            self._responses.clear()
        for sock in sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for response in responses:
            try:
                response.close()
            except Exception:
                pass


def parse_bind(value: str) -> tuple[str, int]:
    """Parse ``host:port`` (IPv6 as ``[::]:port``); host must be an IP literal."""
    text = value.strip()
    match = re.fullmatch(r"\[([0-9A-Fa-f:.]+)\]:(\d{1,5})|([0-9.]+):(\d{1,5})", text)
    if not match:
        raise RelayError(
            "cast_config",
            "Set cast_relay_bind to an IP and port, like 0.0.0.0:8765.",
        )
    host = match.group(1) or match.group(3)
    port = int(match.group(2) or match.group(4))
    try:
        ipaddress.ip_address(host)
    except ValueError:
        raise RelayError(
            "cast_config", "cast_relay_bind must use an IP address, like 0.0.0.0:8765."
        ) from None
    if not 1024 <= port <= 65535:
        raise RelayError("cast_config", "cast_relay_bind port must be between 1024 and 65535.")
    return host, port


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True
    request_queue_size = MAX_CONNECTIONS

    def __init__(self, address: tuple[str, int], relay: MediaRelay) -> None:
        self.address_family = socket.AF_INET6 if ":" in address[0] else socket.AF_INET
        self.relay = relay
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(address, _Handler)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)  # over the connection cap: drop
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            self.shutdown_request(request)

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Silence the default traceback print: it can contain the request line."""


class _Handler(BaseHTTPRequestHandler):
    server: _Server
    server_version = "HermesScreenRelay"
    sys_version = ""
    protocol_version = "HTTP/1.0"
    timeout = CLIENT_SOCKET_TIMEOUT_S

    def log_message(self, format: str, *args: Any) -> None:
        """Never log: request lines carry the capability token."""

    def do_GET(self) -> None:
        self.server.relay._serve(self, head=False)

    def do_HEAD(self) -> None:
        self.server.relay._serve(self, head=True)

    def empty(self, status: int, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()


class MediaRelay:
    """One relay listener holding at most one live capability.

    Owned by a single plugin context (one per Hermes profile registration); there
    is no module-level state. All public methods are thread-safe.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._clock = clock
        self._transport = transport
        self._lock = threading.RLock()
        self._cap: Capability | None = None
        self._server: _Server | None = None
        self._thread: threading.Thread | None = None
        self._http: httpx.Client | None = None
        self._timer: threading.Timer | None = None
        self._bind: tuple[str, int] | None = None
        self._streams = threading.BoundedSemaphore(MAX_STREAMS)

    # -- lifecycle ----------------------------------------------------------------

    @property
    def running(self) -> bool:
        with self._lock:
            return self._server is not None

    @property
    def server_address(self) -> tuple[str, int] | None:
        """The actual bound ``(host, port)`` (useful when binding port 0 in tests)."""
        with self._lock:
            return self._server.server_address[:2] if self._server else None

    def current(self) -> Capability | None:
        """The live capability, or ``None`` if there is none or it expired."""
        with self._lock:
            cap = self._cap
            if cap is not None and not cap.valid(self._clock()):
                self._expire_locked(cap)
                return None
            return cap

    def mint(
        self,
        *,
        bind: tuple[str, int],
        advertised_base: str,
        item_id: str,
        upstream_url: str,
        auth_header: str,
        ttl_s: float,
    ) -> Capability:
        """Start (or reuse) the listener and mint a new capability for one item.

        Any previous capability is revoked first (its streams are cut). Raises
        :class:`RelayError` if the listener cannot bind.
        """
        ttl_s = float(min(max(ttl_s, 1.0), MAX_TTL_S))
        with self._lock:
            self._revoke_locked()
            if self._server is not None and self._bind != bind:
                self._stop_locked()
            if self._server is None:
                self._start_locked(bind)
            token = secrets.token_urlsafe(TOKEN_BYTES)
            cap = Capability(
                token=token,
                item_id=item_id,
                media_url=f"{advertised_base.rstrip('/')}/cast/{token}/video.mp4",
                upstream_url=upstream_url,
                auth_header=auth_header,
                expires_at=self._clock() + ttl_s,
                ttl_s=ttl_s,
            )
            self._cap = cap
            timer = threading.Timer(ttl_s, self._on_timer, args=(cap,))
            timer.daemon = True
            self._timer = timer
            timer.start()
            return cap

    def revoke(self) -> None:
        """Revoke the live capability and stop the listener (port released)."""
        with self._lock:
            self._revoke_locked()
            self._stop_locked()

    close = revoke

    def _on_timer(self, cap: Capability) -> None:
        with self._lock:
            if self._cap is cap:
                self._expire_locked(cap)

    def _expire_locked(self, cap: Capability) -> None:
        if self._cap is cap:
            self._revoke_locked()
            self._stop_locked()

    def _revoke_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        cap, self._cap = self._cap, None
        if cap is not None:
            cap.revoke()

    def _start_locked(self, bind: tuple[str, int]) -> None:
        try:
            server = _Server(bind, self)
        except OSError:
            raise RelayError(
                "relay_bind_failed",
                "Could not open the Chromecast media port. Check cast_relay_bind and that "
                "nothing else uses that port.",
            ) from None
        self._http = httpx.Client(
            timeout=UPSTREAM_TIMEOUT,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=MAX_STREAMS, max_keepalive_connections=0),
            transport=self._transport,
        )
        thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.2},
            name="hermes-screen-relay",
            daemon=True,
        )
        self._server, self._thread, self._bind = server, thread, bind
        thread.start()

    def _stop_locked(self) -> None:
        server, thread, http = self._server, self._thread, self._http
        self._server = self._thread = self._http = None
        self._bind = None
        if server is not None:
            # shutdown() waits for serve_forever to exit, which happens on a
            # different thread; never called from a handler thread.
            if threading.current_thread() is not thread:
                server.shutdown()
            server.server_close()
        if thread is not None and threading.current_thread() is not thread:
            thread.join(STOP_JOIN_TIMEOUT_S)
        if http is not None:
            http.close()

    # -- request handling -------------------------------------------------------------

    def _lookup(self, token: str) -> tuple[Capability, httpx.Client] | None:
        with self._lock:
            cap, http = self._cap, self._http
            if cap is None or http is None or not cap.valid(self._clock()):
                return None
            if not hmac.compare_digest(cap.token.encode(), token.encode()):
                return None
            return cap, http

    def _serve(self, handler: _Handler, *, head: bool) -> None:
        match = _PATH_RE.match(handler.path)
        found = self._lookup(match.group(1)) if match else None
        if found is None:
            handler.empty(404)
            return
        cap, http = found
        ranges = handler.headers.get_all("Range") or []
        range_value: str | None = None
        if ranges:
            range_value = _normalize_range(ranges)
            if range_value is None:
                handler.empty(416)
                return
        if not self._streams.acquire(blocking=False):
            handler.empty(503, {"Retry-After": "2"})
            return
        try:
            self._proxy(handler, cap, http, head=head, range_value=range_value)
        finally:
            self._streams.release()

    def _proxy(
        self,
        handler: _Handler,
        cap: Capability,
        http: httpx.Client,
        *,
        head: bool,
        range_value: str | None,
    ) -> None:
        auth = cap.auth_header
        if not auth:
            handler.empty(404)
            return
        headers = {
            "Authorization": auth,
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "User-Agent": "HermesScreen-Relay",
        }
        if range_value is not None:
            headers["Range"] = range_value
        try:
            request = http.build_request(
                "HEAD" if head else "GET", cap.upstream_url, headers=headers
            )
            response = http.send(request, stream=True)
        except Exception:
            handler.empty(502)
            return
        if not cap._attach(handler.connection, response):
            response.close()
            handler.empty(404)
            return
        try:
            status = response.status_code
            if status == 404:
                handler.empty(404)
                return
            if status == 416:
                extra = {}
                content_range = response.headers.get("Content-Range", "")
                if _CONTENT_RANGE_RE.match(content_range):
                    extra["Content-Range"] = content_range
                handler.empty(416, extra)
                return
            if status not in (200, 206):
                handler.empty(502)  # redirects, auth failures, server errors: never forwarded
                return
            handler.send_response(status)
            for name, value in _forward_headers(response.headers, status).items():
                handler.send_header(name, value)
            handler.end_headers()
            if head:
                return
            for chunk in response.iter_raw(CHUNK_BYTES):
                if not cap.valid(self._clock()):
                    break
                handler.wfile.write(chunk)
        except Exception:
            pass  # client went away, upstream failed, or the capability was revoked
        finally:
            cap._detach(handler.connection, response)
            try:
                response.close()
            except Exception:
                pass
            handler.close_connection = True


def _normalize_range(values: list[str]) -> str | None:
    """Return a normalized single byte range, or ``None`` if invalid or multiple."""
    if len(values) != 1:
        return None
    match = _RANGE_RE.match(values[0].strip())
    if not match:
        return None
    start, end, suffix = match.groups()
    if suffix is not None:
        if int(suffix) == 0:
            return None
        return f"bytes=-{int(suffix)}"
    if end:
        if int(end) < int(start):
            return None
        return f"bytes={int(start)}-{int(end)}"
    return f"bytes={int(start)}-"


def _forward_headers(upstream: httpx.Headers, status: int) -> dict[str, str]:
    """Whitelisted, validated response headers; no cookies, locations or server info."""
    out = {"Content-Type": "video/mp4", "Accept-Ranges": "bytes"}
    length = upstream.get("Content-Length", "")
    if _DIGITS_RE.match(length):
        out["Content-Length"] = length
    content_range = upstream.get("Content-Range", "")
    if status == 206 and _CONTENT_RANGE_RE.match(content_range):
        out["Content-Range"] = content_range
    etag = upstream.get("ETag", "")
    if _ETAG_RE.match(etag):
        out["ETag"] = etag
    modified = upstream.get("Last-Modified", "")
    if _HTTP_DATE_RE.match(modified):
        out["Last-Modified"] = modified
    out["Cache-Control"] = "no-store"
    out["X-Content-Type-Options"] = "nosniff"
    out["Connection"] = "close"
    return out
