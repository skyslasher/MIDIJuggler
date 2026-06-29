"""Helpers for updating connections when devices are removed."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from midijuggler.datapoint.disconnected import disconnected_endpoint
from midijuggler.datapoint.types import ConnectionSpec


def connection_uses_module(connection: ConnectionSpec, module: str) -> bool:
    if not module:
        return False
    for endpoint in (connection.source, connection.target):
        endpoint_module, separator, _ = endpoint.partition(".")
        if separator and endpoint_module == module:
            return True
    return False


def _remap_endpoint(
    endpoint: str,
    removed_module: str,
    replacement_module: str | None,
    *,
    point_available: Callable[[str, str], bool] | None,
) -> tuple[str, bool]:
    module, separator, point = endpoint.partition(".")
    if not separator or module != removed_module:
        return endpoint, False
    if replacement_module and point_available is not None and point_available(replacement_module, point):
        return f"{replacement_module}.{point}", False
    return disconnected_endpoint(), True


def apply_module_removal_to_connections(
    connections: list[ConnectionSpec],
    removed_module: str,
    replacement_module: str | None = None,
    *,
    point_available: Callable[[str, str], bool] | None = None,
) -> list[ConnectionSpec]:
    """Remap or disconnect connection endpoints that referenced a removed device module."""

    updated: list[ConnectionSpec] = []
    for connection in connections:
        if not connection_uses_module(connection, removed_module):
            updated.append(connection)
            continue

        source, source_disconnect = _remap_endpoint(
            connection.source,
            removed_module,
            replacement_module,
            point_available=point_available,
        )
        target, target_disconnect = _remap_endpoint(
            connection.target,
            removed_module,
            replacement_module,
            point_available=point_available,
        )
        enabled = connection.enabled
        if source_disconnect or target_disconnect:
            enabled = False

        if (
            source == connection.source
            and target == connection.target
            and enabled == connection.enabled
        ):
            updated.append(connection)
            continue

        updated.append(
            replace(
                connection,
                source=source,
                target=target,
                enabled=enabled,
            )
        )
    return updated
