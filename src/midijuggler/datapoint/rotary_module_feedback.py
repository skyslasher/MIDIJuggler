"""Rotary display module feedback data-point connections."""

from __future__ import annotations

from midijuggler.config import RotaryDisplayConfig, rotary_display_instance_id
from midijuggler.datapoint.types import ConnectionSpec, ModifierKind

ROTARY_MODULE = "rotary_display"

ROTARY_FEEDBACK_POINTS = (
    "bpm",
    "running",
    "click_enabled",
    "click_interval",
    "beat",
)


def rotary_module_feedback_connections(
    module_id: str,
    *,
    connection_prefix: str,
) -> list[ConnectionSpec]:
    return [
        ConnectionSpec(
            id=f"{connection_prefix}-{point.replace('_', '-')}",
            source=f"clock.{point}",
            target=f"{module_id}.{point}",
            modifier=ModifierKind.PASSTHROUGH,
            managed_by="rotary_display:module",
        )
        for point in ROTARY_FEEDBACK_POINTS
    ]


def merge_rotary_module_feedback_connections(
    connections: list[ConnectionSpec],
    *,
    enabled: bool = False,
    displays: tuple[RotaryDisplayConfig, ...] | None = None,
) -> list[ConnectionSpec]:
    if displays is None:
        if not enabled:
            return list(connections)
        displays = (RotaryDisplayConfig(enabled=True),)

    enabled_displays = [display for display in displays if display.enabled]
    if not enabled_displays:
        return list(connections)

    existing_pairs = {(connection.source, connection.target) for connection in connections}
    merged = list(connections)
    for display in enabled_displays:
        module_id = rotary_display_instance_id(display)
        prefix = module_id.replace(":", "-")
        for connection in rotary_module_feedback_connections(
            module_id,
            connection_prefix=prefix,
        ):
            key = (connection.source, connection.target)
            if key in existing_pairs:
                continue
            merged.append(connection)
            existing_pairs.add(key)
    return merged
