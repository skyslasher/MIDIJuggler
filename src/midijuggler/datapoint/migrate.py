"""Migration helpers from legacy mappings to data-point connections."""

from __future__ import annotations

from midijuggler.config import MasterClockConfig
from midijuggler.datapoint.bridge import migrate_mappings_to_connections
from midijuggler.datapoint.clock_connections import merge_clock_output_connections
from midijuggler.datapoint.types import ConnectionSpec
from midijuggler.mapping import MappingRule

LEGACY_MAPPING_DEPRECATION = (
    "[[mappings]] remain supported; prefer [[connections]] with datapoint ids "
    "when runtime.datapoint_routing is enabled."
)


def effective_connections(
    mappings: list[MappingRule],
    connections: list[ConnectionSpec],
    *,
    datapoint_routing: bool = False,
    master_clock: MasterClockConfig | None = None,
) -> list[ConnectionSpec]:
    """Return explicit connections, migrated mappings, and optional clock defaults."""

    resolved = list(connections) if connections else migrate_mappings_to_connections(mappings)
    if not datapoint_routing or master_clock is None:
        return resolved
    return merge_clock_output_connections(resolved, master_clock.output_targets)
