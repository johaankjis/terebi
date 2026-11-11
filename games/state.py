"""Authoritative, bounded RPS sessions. No camera or client-provided scores."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections.abc import Callable
from typing import Any

MOVES = ("rock", "paper", "scissors")
PAIR_TTL = 180
SESSION_TTL = 1800
COUNTDOWN = 3
ACCEPT_WINDOW = 10
PROFILE_LIMIT = 32
PROFILE_CHOICES = {
    "mode": {"3d", "static"},
    "tier": {"full", "lite", "still"},
    "turn": {"gl", "css"},
}
# Frame-timing windows: [frames, mean ms, worst ms, slow frames]; hand: [frames, mean, worst];
# screen: [width, height, device pixel ratio x100].
PROFILE_NUMBERS = {"ambient": 4, "pairing": 4, "countdown": 4, "reveal": 4, "hand": 3, "screen": 3}


class GameError(Exception):
    def __init__(self, status: int, reason: str, hint: str) -> None:
        self.status, self.reason, self.hint = status, reason, hint
        super().__init__(reason)

    def result(self) -> dict:
        return {"ok": False, "reason": self.reason, "hint": self.hint}


def require(condition: bool, reason: str, hint: str, status: int = 409) -> None:
    if not condition:
        raise GameError(status, reason, hint)


class GameStore:
    """One process owns all rounds; restart expires sessions instead of replaying scores."""

    def __init__(
        self,
        *,
        clock: Callable = time.monotonic,
        choose: Callable = secrets.choice,
        epoch_ms: int | None = None,
        capacity: int = 64,
        audit: Callable | None = None,
    ) -> None:
        self.clock, self.choose, self.capacity = clock, choose, capacity
        self.origin = clock()
        self.epoch = int(time.time() * 1000) if epoch_ms is None else epoch_ms
        self.audit = audit
        self.sessions: dict[str, dict] = {}
        self.lock = threading.RLock()

    def _event(self, s: dict, kind: str, now: float, extra: dict | None = None) -> None:
        if self.audit is None:
            return
        row = {
            "event": kind,
            "at_ms": self.stamp(now),
            "session_sha256": hashlib.sha256(s["id"].encode()).hexdigest(),
            "round_sha256": hashlib.sha256(s["round_id"].encode()).hexdigest()
            if s["round_id"]
            else None,
            "round_number": s["round_number"],
            "phase": s["phase"],
            "score": dict(s["score"]),
        }
        if extra:
            row.update(extra)
        if s["result"]:
            row["result"] = {
                k: s["result"][k] for k in ("player_move", "hermes_move", "outcome", "input")
            }
        try:
            self.audit(row)
        except Exception:
            pass  # Logging failure never changes scoring or authorizes a retry.

    def stamp(self, now: float) -> int:
        return int(self.epoch + (now - self.origin) * 1000)

    def _purge(self, now: float) -> None:
        self.sessions = {k: v for k, v in self.sessions.items() if v["expires"] > now}

    def create(self, request_key: str, public_url: str) -> dict:
        require(
            isinstance(request_key, str) and 16 <= len(request_key) <= 128,
            "invalid_request",
            "Give a bounded opaque request key.",
            400,
        )
        with self.lock:
            now = self.clock()
            self._purge(now)
            session = next(
                (
                    s
                    for s in self.sessions.values()
                    if s["request_key"] == request_key and not s.get("ended")
                ),
                None,
            )
            if session is None:
                # Ended sessions are retry tombstones, not active capacity. Evict one
                # only when needed; a missing old SID is still a safe idempotent end.
                if len(self.sessions) >= self.capacity:
                    old = next((sid for sid, v in self.sessions.items() if v.get("ended")), None)
                    if old is not None:
                        del self.sessions[old]
                require(len(self.sessions) < self.capacity, "capacity", "Try again later.", 429)
                session = {
                    "id": secrets.token_urlsafe(18),
                    "request_key": request_key,
                    "expires": now + SESSION_TTL,
                    "pair_expires": now + PAIR_TTL,
                    "pair": secrets.token_urlsafe(32),
                    "player": None,
                    "viewer": secrets.token_urlsafe(32),
                    "phase": "waiting_for_player",
                    "revision": 1,
                    "round_id": None,
                    "round_number": 0,
                    "deadline": None,
                    "accept_until": None,
                    "result": None,
                    "move": None,
                    "nonce": None,
                    "commitment": None,
                    "profiles": 0,
                    "score": {"player": 0, "hermes": 0, "ties": 0, "rounds": 0},
                }
                self.sessions[session["id"]] = session
                self._event(session, "session_created", now)
            elif session["player"] is None and session["pair_expires"] <= now:
                session["pair"] = secrets.token_urlsafe(32)
                session["pair_expires"] = now + PAIR_TTL
                session["revision"] += 1
            base = public_url.rstrip("/")
            return {
                "ok": True,
                "session_id": session["id"],
                "pairing_url": f"{base}/play/#pair={session['pair']}"
                if session["player"] is None
                else None,
                "pairing_expires_at_ms": self.stamp(session["pair_expires"]),
                "display_url": f"{base}/display/#session={session['id']}&token={session['viewer']}",
                "state": self._snapshot(session, now),
            }

    def end(self, sid: str, request_key: str) -> dict:
        """Admin-only exact-session end. Retain a bounded expiry tombstone for retries."""
        require(
            isinstance(request_key, str)
            and request_key.isascii()
            and 16 <= len(request_key) <= 128,
            "invalid_request",
            "Supply the caller's opaque request key.",
            400,
        )
        with self.lock:
            now = self.clock()
            self._purge(now)
            s = self.sessions.get(sid)
            if s is None:
                return {"ok": True, "session_id": sid, "ended": True, "already_ended": True}
            require(
                hmac.compare_digest(s["request_key"], request_key),
                "session_owner_mismatch",
                "This session belongs to another conversation.",
                403,
            )
            already = bool(s.get("ended"))
            if not already:
                s.update(
                    ended=True,
                    phase="ended",
                    pair=None,
                    deadline=None,
                    accept_until=None,
                    move=None,
                    nonce=None,
                )
                s["revision"] += 1
                self._event(s, "session_ended", now)
            return {"ok": True, "session_id": sid, "ended": True, "already_ended": already}

    def _round(self, s: dict) -> None:
        s["round_number"] += 1
        s["round_id"] = secrets.token_urlsafe(18)
        s["move"], s["nonce"] = self.choose(MOVES), secrets.token_hex(24)
        s["commitment"] = hashlib.sha256(
            f"{s['id']}:{s['round_number']}:{s['move']}:{s['nonce']}".encode()
        ).hexdigest()
        s["result"] = None
        s["deadline"] = s["accept_until"] = None

    def pair(self, pair_token: str) -> dict:
        require(
            isinstance(pair_token, str) and pair_token.isascii() and len(pair_token) <= 128,
            "invalid_pair",
            "Open the pairing link from Telegram.",
            400,
        )
        with self.lock:
            now = self.clock()
            self._purge(now)
            s = next(
                (
                    v
                    for v in self.sessions.values()
                    if v["pair"] is not None and hmac.compare_digest(v["pair"], pair_token)
                ),
                None,
            )
            require(s is not None, "pair_expired", "Request a fresh pairing link in Telegram.", 410)
            require(
                s["pair_expires"] > now and s["player"] is None,
                "pair_expired",
                "Request a fresh pairing link in Telegram.",
                410,
            )
            s["pair"] = None
            s["player"] = secrets.token_urlsafe(32)
            self._round(s)
            s["phase"] = "ready"
            s["revision"] += 1
            self._event(s, "player_paired", now)
            return {
                "ok": True,
                "session_id": s["id"],
                "player_token": s["player"],
                "state": self._snapshot(s, now),
            }

    def _session(self, sid: str, token: str, *, write: bool = False) -> tuple[dict, float]:
        now = self.clock()
        s = self.sessions.get(sid)
        require(s is not None, "session_missing", "Start a new game in Telegram.", 404)
        if s["expires"] <= now:
            del self.sessions[sid]
            raise GameError(410, "session_expired", "Start a new game in Telegram.")
        allowed = [s["player"]] if write else [s["player"], s["viewer"]]
        require(
            isinstance(token, str)
            and token.isascii()
            and any(t and hmac.compare_digest(t, token) for t in allowed),
            "unauthorized",
            "Open your session link again.",
            401,
        )
        require(
            not s.get("ended"), "session_ended", "Game ended. Start a new game in Telegram.", 410
        )
        self._advance(s, now)
        return s, now

    @staticmethod
    def _advance(s: dict, now: float) -> None:
        if s["phase"] == "reveal" and now >= s["revealed"] + 1.5:
            s["phase"] = "score"
            s["revision"] += 1
        if s["phase"] == "score" and now >= s["revealed"] + 3:
            s["phase"] = "next_round"
            s["revision"] += 1

    def _snapshot(self, s: dict, now: float) -> dict[str, Any]:
        self._advance(s, now)
        return {
            "session_id": s["id"],
            "revision": s["revision"],
            "server_time_ms": self.stamp(now),
            "expires_at_ms": self.stamp(s["expires"]),
            "phase": s["phase"],
            "round_id": s["round_id"],
            "round_number": s["round_number"],
            "countdown_ends_at_ms": self.stamp(s["deadline"])
            if s["deadline"] is not None
            else None,
            "accept_until_ms": self.stamp(s["accept_until"])
            if s["accept_until"] is not None
            else None,
            "hermes_commitment": s["commitment"],
            "result": dict(s["result"]) if s["result"] else None,
            "score": dict(s["score"]),
        }

    def state(self, sid: str, token: str) -> dict:
        with self.lock:
            s, now = self._session(sid, token)
            return {"ok": True, "state": self._snapshot(s, now)}

    def profile(self, sid: str, token: str, body: dict) -> dict:
        """Record what a display measured about its own rendering. Numbers only; no game effect."""
        with self.lock:
            s, now = self._session(sid, token)
            require(
                isinstance(body, dict)
                and set(PROFILE_CHOICES) | {"screen"}
                <= set(body)
                <= set(PROFILE_CHOICES) | set(PROFILE_NUMBERS),
                "invalid_request",
                "Send only the display's render mode and frame timings.",
                400,
            )
            for key, value in body.items():
                if key in PROFILE_CHOICES:
                    valid = isinstance(value, str) and value in PROFILE_CHOICES[key]
                else:
                    valid = (
                        isinstance(value, list)
                        and len(value) == PROFILE_NUMBERS[key]
                        and all(type(v) is int and 0 <= v <= 60000 for v in value)
                    )
                require(valid, "invalid_request", "Send bounded render timings only.", 400)
            require(s["profiles"] < PROFILE_LIMIT, "profile_limit", "Enough timings recorded.", 429)
            s["profiles"] += 1
            self._event(s, "display_profile", now, {"profile": dict(body)})
            return {"ok": True}

    def act(self, sid: str, token: str, action: str, body: dict) -> dict:
        with self.lock:
            s, now = self._session(sid, token, write=True)
            keys = {"round_id", "move"} if action in {"move", "tap"} else {"round_id"}
            require(
                isinstance(body, dict) and set(body) == keys,
                "invalid_request",
                "Send only the current round ID and, for a move, the move.",
                400,
            )
            require(
                isinstance(body["round_id"], str) and body["round_id"] == s["round_id"],
                "stale_round",
                "Refresh the current round before trying again.",
            )
            if action == "next":
                require(
                    s["phase"] in {"ready", "next_round"},
                    "round_active",
                    "Finish this round first.",
                )
                if s["phase"] == "next_round":
                    self._round(s)
                self._countdown(s, now)
            elif action == "retry":
                require(
                    s["phase"] == "countdown" and now >= s["deadline"],
                    "retry_unavailable",
                    "Wait for the countdown before retrying.",
                )
                s["round_id"] = secrets.token_urlsafe(18)
                self._countdown(s, now)
            elif action in {"move", "tap"}:
                require(
                    isinstance(body["move"], str) and body["move"] in MOVES,
                    "invalid_move",
                    "Choose rock, paper, or scissors.",
                    400,
                )
                require(
                    s["phase"] == "countdown",
                    "already_scored",
                    "This round is not accepting a move.",
                )
                require(
                    s["deadline"] <= now <= s["accept_until"],
                    "outside_window",
                    "Wait for Shoot or retry the gesture.",
                )
                player = body["move"]
                outcome = (
                    "tie"
                    if player == s["move"]
                    else (
                        "player"
                        if (player, s["move"])
                        in {("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")}
                        else "hermes"
                    )
                )
                s["score"]["ties" if outcome == "tie" else outcome] += 1
                s["score"]["rounds"] += 1
                s["result"] = {
                    "round_id": s["round_id"],
                    "player_move": player,
                    "hermes_move": s["move"],
                    "outcome": outcome,
                    "input": "camera" if action == "move" else "tap",
                    "nonce": s["nonce"],
                }
                s["phase"], s["revealed"] = "reveal", now
            else:
                raise GameError(404, "not_found", "Unknown game action.")
            s["revision"] += 1
            self._event(s, "round_scored" if action in {"move", "tap"} else action, now)
            return {"ok": True, "state": self._snapshot(s, now)}

    @staticmethod
    def _countdown(s: dict, now: float) -> None:
        s["phase"] = "countdown"
        s["deadline"] = now + COUNTDOWN
        s["accept_until"] = s["deadline"] + ACCEPT_WINDOW
