"""Small same-origin game server, behind trusted HTTPS. Never accepts camera data."""

from __future__ import annotations

import argparse
import hmac
import json
import mimetypes
import os
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .state import GameError, GameStore

ROOT = Path(__file__).resolve().parent


def public_origin(value: str) -> str:
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        and not (parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1"})
    ) or (
        not parts.netloc
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in {"", "/"}
    ):
        raise ValueError("Use a trusted HTTPS origin, or localhost for development.")
    return value.rstrip("/")


class GameServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = True
    request_queue_size = 32

    def __init__(
        self, address: tuple, config: dict, *, store: GameStore | None = None, root: Path = ROOT
    ):
        self.admin_token = config["admin_token"]
        if not isinstance(self.admin_token, str) or len(self.admin_token) < 32:
            raise ValueError("Generate an admin token with games.service init.")
        self.public_url = public_origin(config["public_url"]) if config.get("public_url") else ""
        self.store, self.root = (
            store or GameStore(audit=lambda row: print(json.dumps(row), flush=True)),
            root,
        )
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(address, Handler)

    def get_request(self):
        sock, addr = super().get_request()
        sock.settimeout(5)
        return sock, addr

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        pass  # Do not print request data, bearer links, or credentials.


class Handler(BaseHTTPRequestHandler):
    server: GameServer

    def log_message(self, *args):
        pass

    def _headers(self, status: int, mime: str, size: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; "
            "worker-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()

    def _json(self, data: dict, status: int = 200) -> None:
        encoded = json.dumps(data, allow_nan=False).encode()
        self._headers(status, "application/json", len(encoded))
        self.wfile.write(encoded)

    def _token(self) -> str:
        value = self.headers.get("Authorization", "")
        return value[7:] if value.startswith("Bearer ") and len(value) <= 256 else ""

    def _body(self) -> dict:
        if self.headers.get("Transfer-Encoding"):
            raise GameError(400, "invalid_request", "Use a bounded JSON body.")
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise GameError(400, "invalid_request", "Use a bounded JSON body.") from None
        if size <= 0 or size > 2048:
            raise GameError(413, "body_limit", "Send only a small JSON game action; no images.")
        if self.headers.get_content_type() != "application/json":
            raise GameError(400, "invalid_request", "Use application/json.")
        try:

            def invalid_constant(value):
                raise ValueError("nonfinite")

            data = json.loads(self.rfile.read(size), parse_constant=invalid_constant)
            if not isinstance(data, dict):
                raise ValueError("object")
            return data
        except (ValueError, UnicodeDecodeError):
            raise GameError(400, "invalid_request", "Use a JSON object.") from None

    def do_GET(self):
        self._handle(False)

    def do_POST(self):
        self._handle(True)

    def _handle(self, post: bool):
        try:
            parsed = urlsplit(self.path)
            if parsed.query or parsed.fragment:
                raise GameError(
                    400, "invalid_request", "Do not put game credentials in query strings."
                )
            path = parsed.path
            if post:
                origin = self.headers.get("Origin")
                if origin and origin != self.server.public_url:
                    raise GameError(403, "origin_denied", "Use the game's own page.")
                if path == "/v1/sessions":
                    if not self._token().isascii() or not hmac.compare_digest(
                        self._token(), self.server.admin_token
                    ):
                        raise GameError(401, "unauthorized", "Start games through Hermes.")
                    if not self.server.public_url:
                        raise GameError(
                            503, "not_configured", "Configure the game's HTTPS origin first."
                        )
                    body = self._body()
                    if set(body) != {"request_key"}:
                        raise GameError(400, "invalid_request", "Supply only request_key.")
                    return self._json(
                        self.server.store.create(body["request_key"], self.server.public_url)
                    )
                body = self._body()
                if path == "/v1/pair":
                    if set(body) != {"pair_token"}:
                        raise GameError(400, "invalid_request", "Supply only the pairing token.")
                    return self._json(self.server.store.pair(body["pair_token"]))
                match = re.fullmatch(
                    r"/v1/sessions/([A-Za-z0-9_-]{16,64})/(next|retry|move|tap)", path
                )
                if match:
                    return self._json(
                        self.server.store.act(match[1], self._token(), match[2], body)
                    )
            else:
                if path == "/health":
                    return self._json(
                        {
                            "ok": True,
                            "service": "terebi-rps",
                            "configured": bool(self.server.public_url),
                        }
                    )
                match = re.fullmatch(r"/v1/sessions/([A-Za-z0-9_-]{16,64})", path)
                if match:
                    return self._json(self.server.store.state(match[1], self._token()))
                for prefix, directory in (("/play/", "camera/dist"), ("/display/", "display")):
                    if path.startswith(prefix):
                        base = (self.server.root / directory).resolve()
                        target = (base / unquote(path[len(prefix) :] or "index.html")).resolve()
                        if not target.is_relative_to(base) or not target.is_file():
                            break
                        if target.suffix not in {
                            ".html",
                            ".js",
                            ".css",
                            ".json",
                            ".wasm",
                            ".task",
                            ".txt",
                        }:
                            break
                        mime = {
                            ".js": "text/javascript",
                            ".wasm": "application/wasm",
                            ".task": "application/octet-stream",
                        }.get(target.suffix)
                        mime = mime or mimetypes.guess_type(target)[0] or "application/octet-stream"
                        self._headers(200, mime, target.stat().st_size)
                        with target.open("rb") as src:
                            while chunk := src.read(65536):
                                self.wfile.write(chunk)
                        return
            raise GameError(404, "not_found", "Open the game link from Telegram.")
        except GameError as exc:
            self._json(exc.result(), exc.status)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception:
            self._json(
                {
                    "ok": False,
                    "reason": "game_failed",
                    "hint": "Refresh the game or start a new session.",
                },
                500,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "set-url", "serve"])
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--url")
    args = parser.parse_args()
    if args.command == "init":
        args.config.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(
                {
                    "admin_token": secrets.token_urlsafe(32),
                    "public_url": "",
                    "bind": "0.0.0.0",
                    "port": 8766,
                },
                f,
            )
        print("Created private game configuration. No credentials printed.")
        return
    config = json.loads(args.config.read_text())
    if args.command == "set-url":
        config["public_url"] = public_origin(args.url or "")
        args.config.write_text(json.dumps(config))
        print("HTTPS origin saved. Restart the game service before pairing.")
        return
    server = GameServer((config.get("bind", "127.0.0.1"), int(config.get("port", 8766))), config)
    print("Terebi game service listening; request/credential logging disabled.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
