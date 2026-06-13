"""Central registry and value bus for data points."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from midijuggler.datapoint.types import DataPointId, DataPointSpec, DataPointValue

LOGGER = logging.getLogger(__name__)

Handler = Callable[[DataPointValue], Awaitable[None] | None]


class DataPointStore:
    """Register data-point metadata and route value updates."""

    def __init__(self, history_size: int = 200) -> None:
        self._specs: dict[str, DataPointSpec] = {}
        self._values: dict[str, DataPointValue] = {}
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)
        self._history: deque[DataPointValue] = deque(maxlen=history_size)
        self._lock = asyncio.Lock()

    def register(self, spec: DataPointSpec) -> None:
        key = str(spec.id)
        if key in self._specs and self._specs[key] != spec:
            raise ValueError(f"data point already registered with different spec: {key}")
        self._specs[key] = spec

    def register_many(self, specs: list[DataPointSpec]) -> None:
        for spec in specs:
            self.register(spec)

    def spec(self, point_id: DataPointId | str) -> DataPointSpec | None:
        return self._specs.get(self._normalize_id(point_id))

    def specs(self) -> list[DataPointSpec]:
        return list(self._specs.values())

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {
            key: value.as_dict()
            for key, value in sorted(self._values.items())
        }

    def registry_snapshot(self) -> list[dict[str, Any]]:
        values = {
            key: self._values[key].as_dict()
            for key in self._values
        }
        payload: list[dict[str, Any]] = []
        for key in sorted(self._specs):
            entry = self._specs[key].as_dict()
            if key in values:
                entry["value"] = values[key]
            payload.append(entry)
        return payload

    def history(self) -> list[DataPointValue]:
        return list(self._history)

    def subscribe(self, point_id: DataPointId | str, handler: Handler) -> None:
        self._subscribers[self._normalize_id(point_id)].append(handler)

    def subscribe_all(self, handler: Handler) -> None:
        self._subscribers["*"].append(handler)

    async def write(self, value: DataPointValue) -> None:
        key = str(value.point_id)
        spec = self._specs.get(key)
        if spec is None:
            LOGGER.debug("write to unregistered data point %s", key)

        if not self._value_changed(key, value):
            return

        async with self._lock:
            self._values[key] = value
            self._history.append(value)

        handlers = [
            *self._subscribers.get(key, []),
            *self._subscribers.get("*", []),
        ]
        for handler in handlers:
            try:
                result = handler(value)
                if inspect.isawaitable(result):
                    await result
            except RecursionError:
                LOGGER.error("data point handler recursion for %s", key)
                raise
            except Exception:
                LOGGER.exception("data point handler failed for %s", key)

    def _value_changed(self, key: str, value: DataPointValue) -> bool:
        previous = self._values.get(key)
        if previous is None:
            return True
        if value.value_type != previous.value_type:
            return True
        if value.float_value is not None and previous.float_value is not None:
            return abs(value.float_value - previous.float_value) > 1e-9
        if value.bool_value is not None and previous.bool_value is not None:
            return value.bool_value != previous.bool_value
        if value.int_value is not None and previous.int_value is not None:
            return value.int_value != previous.int_value
        if value.midi_status != previous.midi_status:
            return True
        if value.midi_data != previous.midi_data:
            return True
        if value.osc_address != previous.osc_address:
            return True
        if value.osc_arguments != previous.osc_arguments:
            return True
        return False

    @staticmethod
    def _normalize_id(point_id: DataPointId | str) -> str:
        if isinstance(point_id, DataPointId):
            return str(point_id)
        return str(DataPointId.parse(point_id))
