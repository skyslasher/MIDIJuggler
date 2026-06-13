"""Route data-point updates through modifier connections."""

from __future__ import annotations

import logging

from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    ConnectionSpec,
    DataPointId,
    DataPointValue,
    ModifierKind,
    ValueType,
    float_value,
    relay_value,
)
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
        self._passthrough_index: dict[str, list[ConnectionSpec]] = {}
        self._rebuild_index()

    def datapoints(self) -> list:
        return []

    def replace_connections(self, connections: list[ConnectionSpec]) -> None:
        self.connections = list(connections)
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._source_index.clear()
        self._passthrough_index.clear()
        for connection in self.connections:
            if connection.modifier == ModifierKind.PASSTHROUGH:
                self._passthrough_index.setdefault(connection.source, []).append(connection)
                continue
            transform = RangeMapTransform.from_connection(connection)
            self._source_index.setdefault(connection.source, []).append(
                (connection, transform)
            )

    async def start(self) -> None:
        await super().start()
        sources = set(self._source_index) | set(self._passthrough_index)
        for source in sources:
            self.store.subscribe(DataPointId.parse(source), self._on_source_value)

    async def _on_source_value(self, value: DataPointValue) -> None:
        key = str(value.point_id)
        for connection in self._passthrough_index.get(key, []):
            await self._relay_passthrough(value, connection)
        if value.value_type not in {ValueType.FLOAT, ValueType.BOOL, ValueType.INT}:
            return
        numeric = _numeric_value(value)
        if numeric is None:
            return
        for connection, transform in self._source_index.get(key, []):
            mapped = apply_range_map(numeric, transform)
            await self.store.write(
                float_value(DataPointId.parse(connection.target), mapped)
            )

    async def _relay_passthrough(
        self,
        value: DataPointValue,
        connection: ConnectionSpec,
    ) -> None:
        if value.value_type == ValueType.MIDI_MESSAGE:
            if value.midi_status is None:
                return
            await self.store.write(
                relay_value(value, connection.target),
            )
            return
        if value.value_type in {ValueType.FLOAT, ValueType.BOOL, ValueType.INT, ValueType.TRIGGER}:
            await self.store.write(relay_value(value, connection.target))


def _numeric_value(value: DataPointValue) -> float | None:
    if value.float_value is not None:
        return value.float_value
    if value.int_value is not None:
        return float(value.int_value)
    if value.bool_value is not None:
        return 1.0 if value.bool_value else 0.0
    return None
