"""Simple global toggle for Teach Mode."""

from __future__ import annotations

from threading import Lock

_teach_mode = False
_lock = Lock()


def is_teach_mode_on() -> bool:
    with _lock:
        return _teach_mode


def set_teach_mode(enabled: bool) -> bool:
    global _teach_mode
    with _lock:
        _teach_mode = bool(enabled)
        return _teach_mode
