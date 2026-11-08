"""Error model for Hermes Screen.

Errors are data, never stack traces: handlers return small dicts shaped
``{"ok": False, "reason": "...", "hint": "..."}``.
"""

from __future__ import annotations

from typing import Any


class HermesScreenError(Exception):
    """Base error for Hermes Screen."""


def error_payload(reason: str, hint: str, **extra: Any) -> dict[str, Any]:
    """Build a standard failure payload."""
    payload: dict[str, Any] = {"ok": False, "reason": reason, "hint": hint}
    payload.update(extra)
    return payload


def ok_payload(**data: Any) -> dict[str, Any]:
    """Build a standard success payload."""
    return {"ok": True, **data}
