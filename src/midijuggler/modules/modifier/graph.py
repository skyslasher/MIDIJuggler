"""Route data-point updates through modifier connections."""

from __future__ import annotations

import logging

from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import ConnectionSpec, DataPointId, DataPointValue, ValueType, float_value
from midijuggler.modules.base import ModifierModule
from midijuggler.modules.modifier.range_map import RangeMapTransform, apply_range_map

LOGGER = logging.getLogger(__name__)


class ModifierGraph(ModifierModule):
    """Apply configured connections when source data points change."""

    def __init__(
        self,
        store: DataPointStore,
        connections: list[ConnectionSpec],
    ) -> None:
        super().__init__("modifier_graph", store)
        self.connections = list(connections)
        self._source_index: dict[str, list[tuple[ConnectionSpec, RangeMapTransform]]] = {}
        self._rebuild_index()

    def datapoints(self) -> list:
        return []

    def replace_connections(self, connections: list[ConnectionSpec]) -> None:
        self.connections = list(connections)
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._source_index.clear()
        for connection in self.connections:
            transform = RangeMapTransform.from_connection(connection)
            self._source_index.setdefault(connection.source, []).append(
                (connection, transform)
            )

    async def start(self) -> None:
        await super().start()
        for source in self._source_index:
            self.store.subscribe(DataPointId.parse(source), self._on_source_value)

    async def _on_source_value(self, value: DataPointValue) -> None:
        if value.value_type not in {ValueType.FLOAT, ValueType.BOOL, ValueType.INT}:
            return
        numeric = _numeric_value(value)
        if numeric is None:
            return
        key = str(value.point_id)
        for connection, transform in self._source_index.get(key, []):
            mapped = apply_range_map(numeric, transform)
            await self.store.write(
                float_value(DataPointId.parse(connection.target), mapped)
            )


def _numeric_value(value: DataPointValue) -> float | None:
    if value.float_value is not None:
        return value.float_value
    if value.int_value is not None:
        return float(value.int_value)
    if value.bool_value is not None:
        return 1.0 if value.bool_value else 0.0
    return None
