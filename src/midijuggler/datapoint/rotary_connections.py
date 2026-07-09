"""Default data-point connections for rotary display OSC devices."""

from __future__ import annotations

from midijuggler.datapoint.types import ConnectionSpec, ModifierKind
from midijuggler.device.types import DeviceConfig
from midijuggler.osc_library import get_osc_library

ROTARY_DISPLAY_LIBRARY = "rotary_display"


def rotary_display_device_ids(devices: dict[str, DeviceConfig]) -> list[str]:
    return [
        device.uid
        for device in devices.values()
        if str(device.library or "").strip() == ROTARY_DISPLAY_LIBRARY
    ]


def _modifier_kind(value: str) -> ModifierKind:
    try:
        return ModifierKind(value)
    except ValueError:
        return ModifierKind.PASSTHROUGH


def bundled_connections_for_device(
    library_id: str,
    device_id: str,
    *,
    include_feedback: bool = True,
) -> list[ConnectionSpec]:
    """Build bundled library connections for one device instance."""

    library = get_osc_library(library_id)
    connections: list[ConnectionSpec] = []
    for bundled in library.bundled_connections:
        if bundled.direction == "host_to_encoder" and not include_feedback:
            continue
        connection_id, source, target = bundled.resolve(device_id)
        connections.append(
            ConnectionSpec(
                id=connection_id,
                source=source,
                target=target,
                modifier=_modifier_kind(bundled.modifier),
                managed_by=bundled.managed_by,
            )
        )
    return connections


def rotary_encoder_to_clock_connections(device_id: str) -> list[ConnectionSpec]:
    """Map encoder OSC commands on a rotary_display device to clock inputs."""

    return bundled_connections_for_device(
        ROTARY_DISPLAY_LIBRARY,
        device_id,
        include_feedback=False,
    )


def rotary_clock_feedback_connections(device_id: str) -> list[ConnectionSpec]:
    """Map master clock feedback to the rotary display OSC targets."""

    library = get_osc_library(ROTARY_DISPLAY_LIBRARY)
    connections: list[ConnectionSpec] = []
    for bundled in library.bundled_connections:
        if bundled.direction != "host_to_encoder":
            continue
        connection_id, source, target = bundled.resolve(device_id)
        connections.append(
            ConnectionSpec(
                id=connection_id,
                source=source,
                target=target,
                modifier=_modifier_kind(bundled.modifier),
                managed_by=bundled.managed_by,
            )
        )
    return connections


def merge_rotary_display_connections(
    connections: list[ConnectionSpec],
    devices: dict[str, DeviceConfig],
    *,
    include_feedback: bool = True,
) -> list[ConnectionSpec]:
    """Append default rotary encoder connections for configured devices."""

    existing_pairs = {(connection.source, connection.target) for connection in connections}
    merged = list(connections)
    for device_id in rotary_display_device_ids(devices):
        defaults = bundled_connections_for_device(
            ROTARY_DISPLAY_LIBRARY,
            device_id,
            include_feedback=include_feedback,
        )
        for connection in defaults:
            key = (connection.source, connection.target)
            if key in existing_pairs:
                continue
            merged.append(connection)
            existing_pairs.add(key)
    return merged
