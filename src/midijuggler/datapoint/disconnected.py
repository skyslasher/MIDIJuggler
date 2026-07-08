"""Placeholder endpoints for connections with missing source or target devices."""

from __future__ import annotations

DISCONNECTED_MODULE = "nicht_verbunden"
DISCONNECTED_POINT = "nicht_verbunden"
DISCONNECTED_LABEL = "Nicht verbunden"


def disconnected_endpoint() -> str:
    return f"{DISCONNECTED_MODULE}.{DISCONNECTED_POINT}"


def is_disconnected_module(module: str) -> bool:
    return module == DISCONNECTED_MODULE


def is_disconnected_endpoint(endpoint: str) -> bool:
    module, separator, point = endpoint.partition(".")
    return bool(separator) and module == DISCONNECTED_MODULE and point == DISCONNECTED_POINT


def is_reserved_connection_module(module: str) -> bool:
    return module in {"clock", "gamepi", "mapping", DISCONNECTED_MODULE, "rotary_display", "song"}
