"""Route data-point updates through modifier connections."""

from __future__ import annotations

import logging

from midijuggler.datapoint.compare import compare_epsilon
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    ConnectionSpec,
    DataPointId,
    DataPointSpec,
    DataPointValue,
    ModifierKind,
    ValueType,
    float_value,
    relay_value,
    trigger_value,
    value_is_active,
)
from midijuggler.modules.base import ModifierModule
from midijuggler.modules.modifier.feedback_suppress import (
    FeedbackSuppressor,
    control_group,
    reciprocal_feedback_pairs,
)
from midijuggler.modules.modifier.range_map import (
    RangeMapTransform,
    apply_output_scale_curve,
    apply_range_map,
)
from midijuggler.modules.modifier.relative_delta import (
    DEFAULT_RELATIVE_ENCODING,
    ENCODING_ABSOLUTE_DELTA,
    apply_relative_delta,
)

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
        self._feedback_suppressor = FeedbackSuppressor(feedback_suppress_ms)
        self._user_sources: set[str] = set()
        self._last_relative_input: dict[str, int] = {}
        self._relative_targets: dict[tuple[str, str], float] = {}
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
        feedback_pairs = reciprocal_feedback_pairs(self.connections)
        self._user_sources = set(feedback_pairs.values())
        self._feedback_suppressor.set_feedback_pairs(feedback_pairs)

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
        if key in self._user_sources:
            self._feedback_suppressor.note_user_input(key, now=value.timestamp)
        for connection in self._passthrough_index.get(key, []):
            await self._relay_passthrough(value, connection)
        if value.value_type not in {ValueType.FLOAT, ValueType.BOOL, ValueType.INT}:
            return
        numeric = _numeric_value(value)
        if numeric is None:
            return
        suppress_source = self._feedback_suppressor.should_suppress_source(
            key,
            now=value.timestamp,
        )
        for connection, transform in self._source_index.get(key, []):
            force_desk_forward = _should_force_desk_forward(key, connection.target)
            suppress_target = False
            if not force_desk_forward:
                suppress_target = self._feedback_suppressor.should_suppress_target(
                    connection.target,
                    now=value.timestamp,
                )
            effective_suppress_source = False if force_desk_forward else suppress_source
            if effective_suppress_source or suppress_target:
                LOGGER.debug(
                    "modifier_graph suppressed feedback %s -> %s",
                    connection.source,
                    connection.target,
                )
            mapped = self._map_value(key, numeric, connection.target, transform)
            if mapped is None:
                continue
            current = self.store.float_value(connection.target)
            if (
                not force_desk_forward
                and current is not None
                and abs(current - mapped) <= _compare_epsilon(
                    self.store,
                    connection.target,
                )
            ):
                continue
            emit_outputs = not (effective_suppress_source or suppress_target)
            await self.store.write(
                float_value(
                    DataPointId.parse(connection.target),
                    mapped,
                    emit_outputs=emit_outputs,
                )
            )
            if emit_outputs:
                self._feedback_suppressor.note_outbound_target(
                    connection.target,
                    now=value.timestamp,
                )

    def _map_value(
        self,
        source_key: str,
        numeric: float,
        target_key: str,
        transform: RangeMapTransform,
    ) -> float | None:
        if not self._is_relative_source(source_key):
            return apply_range_map(numeric, transform)

        encoding = self._relative_encoding(source_key)
        step = int(round(numeric))
        last_step = self._last_relative_input.get(source_key)
        if encoding == ENCODING_ABSOLUTE_DELTA:
            self._last_relative_input[source_key] = step
        accumulator_key = (source_key, target_key)
        current = self._relative_targets.get(accumulator_key)
        if current is None:
            stored = self.store.float_value(target_key)
            current = (
                stored
                if stored is not None
                else (transform.output_min + transform.output_max) / 2.0
            )
        mapped = apply_relative_delta(
            current,
            numeric,
            transform,
            encoding=encoding,
            last_value=last_step,
        )
        if mapped is None:
            return None
        if transform.scale_curve != "linear":
            mapped = apply_output_scale_curve(mapped, transform)
        self._relative_targets[accumulator_key] = mapped
        return mapped

    def _is_relative_source(self, source_key: str) -> bool:
        spec = self.store.spec(source_key)
        if spec is not None and spec.input_mode == "relative":
            return True
        point = source_key.split(".", 1)[-1]
        return point.endswith("_turn")

    def _relative_encoding(self, source_key: str) -> str:
        spec = self.store.spec(source_key)
        if isinstance(spec, DataPointSpec) and spec.relative_encoding:
            return spec.relative_encoding
        return DEFAULT_RELATIVE_ENCODING

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
            coerced = self._coerce_relay_value(value, connection.target)
            if coerced.value_type == ValueType.TRIGGER and value_is_active(coerced):
                await self.store.write(trigger_value(connection.target, False))
            await self.store.write(coerced)

    def _coerce_relay_value(
        self,
        value: DataPointValue,
        target: DataPointId | str,
    ) -> DataPointValue:
        spec = self.store.spec(target)
        if spec is not None and spec.value_type == ValueType.TRIGGER:
            return trigger_value(target, value_is_active(value))
        return relay_value(value, target)


def _numeric_value(value: DataPointValue) -> float | None:
    if value.float_value is not None:
        return value.float_value
    if value.int_value is not None:
        return float(value.int_value)
    if value.bool_value is not None:
        return 1.0 if value.bool_value else 0.0
    return None


def _compare_epsilon(store: DataPointStore, target_key: str) -> float:
    return compare_epsilon(store.spec(target_key))


def _should_force_desk_forward(source_key: str, target_key: str) -> bool:
    """Always forward active controller input to desk targets."""

    if control_group(target_key) is not None:
        return False
    if control_group(source_key) is not None:
        return True
    return source_key.rsplit(".", 1)[-1].endswith("_turn")
