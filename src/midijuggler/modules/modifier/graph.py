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
from midijuggler.modules.modifier.feedback_suppress import EncoderFeedbackSuppressor
from midijuggler.modules.modifier.range_map import RangeMapTransform, apply_range_map
from midijuggler.modules.modifier.relative_delta import apply_relative_delta

LOGGER = logging.getLogger(__name__)


class ModifierGraph(ModifierModule):
    """Apply configured connections when source data points change."""

    def __init__(
        self,
        store: DataPointStore,
        connections: list[ConnectionSpec],
        *,
        feedback_suppress_ms: int = 500,
    ) -> None:
        super().__init__("modifier_graph", store)
        self.connections = list(connections)
        self._source_index: dict[str, list[tuple[ConnectionSpec, RangeMapTransform]]] = {}
        self._passthrough_index: dict[str, list[ConnectionSpec]] = {}
        self._subscribed_sources: set[str] = set()
        self._feedback_suppressor = EncoderFeedbackSuppressor(feedback_suppress_ms)
        self._rebuild_index()

    def datapoints(self) -> list:
        return []

    def replace_connections(self, connections: list[ConnectionSpec]) -> None:
        self.connections = list(connections)
        self._rebuild_index()
        if self.running:
            self._sync_subscriptions()

    def configure_feedback_suppress(self, window_ms: int) -> None:
        self._feedback_suppressor.configure(window_ms)

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
        self._sync_subscriptions()
        self.store.subscribe_all(self._on_any_value)

    def _sync_subscriptions(self) -> None:
        sources = set(self._source_index) | set(self._passthrough_index)
        for source in sorted(sources):
            if source in self._subscribed_sources:
                continue
            self.store.subscribe(DataPointId.parse(source), self._on_source_value)
            self._subscribed_sources.add(source)

    async def _on_any_value(self, value: DataPointValue) -> None:
        if self._is_relative_source(str(value.point_id)):
            self._feedback_suppressor.note_turn(
                str(value.point_id),
                now=value.timestamp,
            )

    async def _on_source_value(self, value: DataPointValue) -> None:
        key = str(value.point_id)
        if self._is_relative_source(key):
            self._feedback_suppressor.note_turn(key, now=value.timestamp)
        for connection in self._passthrough_index.get(key, []):
            await self._relay_passthrough(value, connection)
        if value.value_type not in {ValueType.FLOAT, ValueType.BOOL, ValueType.INT}:
            return
        numeric = _numeric_value(value)
        if numeric is None:
            return
        for connection, transform in self._source_index.get(key, []):
            if self._feedback_suppressor.should_suppress_target(
                connection.target,
                now=value.timestamp,
            ):
                LOGGER.debug(
                    "modifier_graph suppressed feedback %s -> %s",
                    connection.source,
                    connection.target,
                )
                continue
            mapped = self._map_value(key, numeric, connection.target, transform)
            if mapped is None:
                continue
            await self.store.write(
                float_value(DataPointId.parse(connection.target), mapped)
            )

    def _map_value(
        self,
        source_key: str,
        numeric: float,
        target_key: str,
        transform: RangeMapTransform,
    ) -> float | None:
        if self._is_relative_source(source_key):
            current = self.store.float_value(target_key)
            if current is None:
                current = (transform.output_min + transform.output_max) / 2.0
            return apply_relative_delta(current, numeric, transform)
        return apply_range_map(numeric, transform)

    def _is_relative_source(self, source_key: str) -> bool:
        spec = self.store.spec(source_key)
        return spec is not None and spec.input_mode == "relative"

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
