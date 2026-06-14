"""Migration helpers from legacy mappings to data-point connections."""

from __future__ import annotations

from midijuggler.config import AdapterConfig, MasterClockConfig
from midijuggler.datapoint.bridge import migrate_mappings_to_connections
from midijuggler.datapoint.clock_connections import (
    merge_clock_output_connections,
    usable_clock_output_targets,
)
from midijuggler.datapoint.types import ConnectionSpec
from midijuggler.mapping import MappingRule

LEGACY_MAPPING_DEPRECATION = (
    "[[mappings]] remain supported; prefer [[connections]] with datapoint ids "
    "when runtime.datapoint_routing is enabled."
)


def resolved_user_connections(
    mappings: list[MappingRule],
    connections: list[ConnectionSpec],
) -> list[ConnectionSpec]:
    """Resolve configured user connections without resurrecting cleared mappings."""

    if connections or not mappings:
        return list(connections)
    return migrate_mappings_to_connections(mappings)


def stored_connections(
    mappings: list[MappingRule],
    connections: list[ConnectionSpec],
) -> list[ConnectionSpec]:
    """Return user-defined connections, migrating legacy mappings when needed."""

    return resolved_user_connections(mappings, connections)


def effective_connections(
    mappings: list[MappingRule],
    connections: list[ConnectionSpec],
    *,
    datapoint_routing: bool = False,
    master_clock: MasterClockConfig | None = None,
    adapters: dict[str, AdapterConfig] | None = None,
) -> list[ConnectionSpec]:
    """Return explicit connections, migrated mappings, and optional clock defaults."""

    resolved = resolved_user_connections(mappings, connections)
    if not datapoint_routing or master_clock is None:
        return resolved
    output_targets = list(master_clock.output_targets)
    if adapters is not None:
        output_targets = usable_clock_output_targets(output_targets, adapters)
    return merge_clock_output_connections(resolved, output_targets)
