"""Rotary display module feedback data-point connections."""

from __future__ import annotations

from midijuggler.datapoint.types import ConnectionSpec, ModifierKind

ROTARY_MODULE = "rotary_display"

ROTARY_FEEDBACK_POINTS = (
    "bpm",
    "running",
    "click_enabled",
    "click_interval",
    "beat",
)


def rotary_module_feedback_connections() -> list[ConnectionSpec]:
    """Route master clock state to rotary_display feedback targets."""

    return [
        ConnectionSpec(
            id="clock-bpm-to-rotary-display",
            source="clock.bpm",
            target=f"{ROTARY_MODULE}.bpm",
            modifier=ModifierKind.PASSTHROUGH,
            managed_by="rotary_display:module",
        ),
        ConnectionSpec(
            id="clock-running-to-rotary-display",
            source="clock.running",
            target=f"{ROTARY_MODULE}.running",
            modifier=ModifierKind.PASSTHROUGH,
            managed_by="rotary_display:module",
        ),
        ConnectionSpec(
            id="clock-click-enabled-to-rotary-display",
            source="clock.click_enabled",
            target=f"{ROTARY_MODULE}.click_enabled",
            modifier=ModifierKind.PASSTHROUGH,
            managed_by="rotary_display:module",
        ),
        ConnectionSpec(
            id="clock-click-interval-to-rotary-display",
            source="clock.click_interval",
            target=f"{ROTARY_MODULE}.click_interval",
            modifier=ModifierKind.PASSTHROUGH,
            managed_by="rotary_display:module",
        ),
        ConnectionSpec(
            id="clock-beat-to-rotary-display",
            source="clock.beat",
            target=f"{ROTARY_MODULE}.beat",
            modifier=ModifierKind.PASSTHROUGH,
            managed_by="rotary_display:module",
        ),
    ]


def merge_rotary_module_feedback_connections(
    connections: list[ConnectionSpec],
    *,
    enabled: bool,
) -> list[ConnectionSpec]:
    if not enabled:
        return list(connections)

    existing_pairs = {(connection.source, connection.target) for connection in connections}
    merged = list(connections)
    for connection in rotary_module_feedback_connections():
        key = (connection.source, connection.target)
        if key in existing_pairs:
            continue
        merged.append(connection)
        existing_pairs.add(key)
    return merged
