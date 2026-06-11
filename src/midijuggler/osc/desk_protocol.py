"""Desk-specific OSC behavior for Behringer X32 and Wing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from midijuggler.osc_library import get_osc_library

DESK_LIBRARY_IDS = frozenset({"behringer_x32", "behringer_wing"})
DESK_MODE_TO_LIBRARY: dict[str, str] = {
    "x32": "behringer_x32",
    "wing": "behringer_wing",
}
LIBRARY_TO_DESK_MODE: dict[str, str] = {
    library_id: desk_mode for desk_mode, library_id in DESK_MODE_TO_LIBRARY.items()
}


@dataclass(frozen=True)
class DeskProtocol:
    """Runtime desk protocol settings derived from an OSC library."""

    library_id: str
    protocol_id: str
    default_port: int
    keepalive_address: str
    keepalive_interval: float = 9.0


DESK_PROTOCOLS: dict[str, DeskProtocol] = {
    "behringer_x32": DeskProtocol(
        library_id="behringer_x32",
        protocol_id="x32",
        default_port=10023,
        keepalive_address="/xremote",
    ),
    "behringer_wing": DeskProtocol(
        library_id="behringer_wing",
        protocol_id="wing",
        default_port=2223,
        keepalive_address="/*s~",
    ),
}


def desk_protocol_for_library(library_id: str) -> DeskProtocol | None:
    normalized = library_id.strip()
    if not normalized:
        return None
    return DESK_PROTOCOLS.get(normalized)


def is_desk_library(library_id: str) -> bool:
    return library_id.strip() in DESK_LIBRARY_IDS


def osc_library_for_desk_mode(desk_mode: str) -> str:
    normalized = desk_mode.strip().lower()
    if normalized in {"", "none"}:
        return ""
    if normalized not in DESK_MODE_TO_LIBRARY:
        raise ValueError("desk_mode must be x32, wing, or empty")
    return DESK_MODE_TO_LIBRARY[normalized]


def desk_mode_for_library(library_id: str) -> str:
    return LIBRARY_TO_DESK_MODE.get(library_id.strip(), "")


def desk_subscribe_address(desk: DeskProtocol, listen_port: int = 0) -> str:
    """Return the OSC address used to subscribe to unsolicited desk feedback."""

    if desk.protocol_id == "wing":
        if listen_port > 0:
            return f"/%{listen_port}/*s~"
        return desk.keepalive_address
    return desk.keepalive_address


def apply_desk_options(options: dict[str, Any]) -> dict[str, Any]:
    """Normalize desk adapter options, coupling listen and remote ports."""

    osc_library = str(options.get("osc_library", "")).strip()
    desk = desk_protocol_for_library(osc_library)
    normalized = dict(options)

    normalized["desk_sync_on_connect"] = bool(options.get("desk_sync_on_connect", False))
    normalized["desk_proxy_mode"] = bool(options.get("desk_proxy_mode", False))

    if desk is None:
        if normalized["desk_sync_on_connect"] or normalized["desk_proxy_mode"]:
            raise ValueError(
                "desk_sync_on_connect and desk_proxy_mode require a desk OSC library "
                "(behringer_x32 or behringer_wing)"
            )
        return normalized

    if normalized["desk_proxy_mode"] and desk.protocol_id != "wing":
        raise ValueError("desk_proxy_mode is currently supported for behringer_wing only")

    osc_port = int(options.get("osc_port", 0))
    if osc_port <= 0:
        remote_port_candidate = int(options.get("remote_port", 0))
        listen_port_candidate = int(options.get("listen_port", 0))
        osc_port = remote_port_candidate or listen_port_candidate or desk.default_port

    normalized["osc_port"] = osc_port
    normalized["listen_port"] = osc_port
    normalized["remote_port"] = osc_port
    normalized["desk_mode"] = desk.protocol_id
    return normalized


def sync_query_addresses(library_id: str) -> list[str]:
    """Return unique OSC addresses to query for a full library sync."""

    library = get_osc_library(library_id)
    seen: set[str] = set()
    addresses: list[str] = []
    for parameter in library.parameters:
        if parameter.address in seen:
            continue
        seen.add(parameter.address)
        addresses.append(parameter.address)
    return addresses
