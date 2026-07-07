"""Connection resolution for data-point routing."""

from __future__ import annotations

from midijuggler.config import AppConfig
from midijuggler.datapoint.clock_connections import (
    merge_clock_output_connections,
    usable_clock_output_targets,
)
from midijuggler.datapoint.rotary_connections import merge_rotary_display_connections
from midijuggler.datapoint.types import ConnectionSpec


def stored_connections(connections: list[ConnectionSpec]) -> list[ConnectionSpec]:
    """Return configured user connections."""

    return list(connections)


def resolved_user_connections(connections: list[ConnectionSpec]) -> list[ConnectionSpec]:
    """Backward-compatible alias for stored_connections."""

    return stored_connections(connections)


def effective_connections(
    config: AppConfig,
    *,
    datapoint_routing: bool = True,
) -> list[ConnectionSpec]:
    """Return explicit connections and optional clock defaults."""

    resolved = list(config.connections)
    if not datapoint_routing:
        return resolved
    output_targets = usable_clock_output_targets(
        list(config.master_clock.output_targets),
        config.devices,
        config.adapters,
    )
    merged = merge_clock_output_connections(resolved, output_targets)
    if not config.rotary_display.enabled:
        merged = merge_rotary_display_connections(merged, config.devices)
    return merged
