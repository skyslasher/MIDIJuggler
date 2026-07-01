"""Resolve connection and OSC datapoint endpoint identifiers."""

from __future__ import annotations

from midijuggler.datapoint.disconnected import is_reserved_connection_module
from midijuggler.device.types import DeviceConfig


def osc_address_variants(address: str) -> tuple[str, ...]:
    stripped = address.lstrip("/")
    variants: list[str] = []
    seen: set[str] = set()
    for candidate in (address, f"/{stripped}", stripped):
        if candidate and candidate not in seen:
            seen.add(candidate)
            variants.append(candidate)
    return tuple(variants)


def align_custom_point_endpoint(
    endpoint: str,
    devices: dict[str, DeviceConfig],
) -> str:
    """Rewrite an endpoint to the configured custom-point id when slash forms differ."""

    module, _, point = endpoint.partition(".")
    if not point or is_reserved_connection_module(module):
        return endpoint
    device = devices.get(module)
    if device is None or not device.custom_points:
        return endpoint
    registered = {custom.id for custom in device.custom_points}
    if point in registered:
        return endpoint
    point_variants = set(osc_address_variants(point))
    for custom_id in registered:
        if point_variants & set(osc_address_variants(custom_id)):
            return f"{module}.{custom_id}"
    return endpoint
