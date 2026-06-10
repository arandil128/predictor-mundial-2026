"""Caché simple en memoria con TTL, para no agotar los planes gratuitos de las APIs."""
from __future__ import annotations

import time
from typing import Any

_store: dict[str, tuple[float, Any]] = {}


def get(key: str) -> Any | None:
    """Devuelve el valor cacheado si no expiró, si no None."""
    entry = _store.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.monotonic() > expires_at:
        _store.pop(key, None)
        return None
    return value


def set(key: str, value: Any, ttl_seconds: int) -> None:
    _store[key] = (time.monotonic() + ttl_seconds, value)


def clear() -> None:
    _store.clear()
