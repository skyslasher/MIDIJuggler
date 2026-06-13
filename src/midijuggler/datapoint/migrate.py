"""Migration helpers from legacy mappings to data-point connections."""

from __future__ import annotations

from midijuggler.datapoint.bridge import migrate_mappings_to_connections
from midijuggler.datapoint.types import ConnectionSpec
from midijuggler.mapping import MappingRule

LEGACY_MAPPING_DEPRECATION = (
    "[[mappings]] remain supported; prefer [[connections]] with datapoint ids "
    "when runtime.datapoint_routing is enabled."
)


def effective_connections(
    mappings: list[MappingRule],
    connections: list[ConnectionSpec],
) -> list[ConnectionSpec]:
    """Return explicit connections or migrate legacy mappings."""

    if connections:
        return list(connections)
    return migrate_mappings_to_connections(mappings)
