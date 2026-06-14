"""Core data-point types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import Any


class ValueType(str, Enum):
    FLOAT = "float"
    BOOL = "bool"
    INT = "int"
    TRIGGER = "trigger"
    MIDI_MESSAGE = "midi_message"
    OSC_MESSAGE = "osc_message"


class DataPointDirection(str, Enum):
    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"


class ModifierKind(str, Enum):
    RANGE_MAP = "range_map"
    PASSTHROUGH = "passthrough"


@dataclass(frozen=True)
class DataPointId:
    """Canonical identity: module_instance.point_id."""

    module: str
    point: str

    @classmethod
    def parse(cls, value: str) -> DataPointId:
        module, separator, point = value.partition(".")
        if not separator or not module or not point:
            raise ValueError(f"invalid data point id: {value!r}")
        return cls(module=module, point=point)

    def __str__(self) -> str:
        return f"{self.module}.{self.point}"


@dataclass(frozen=True)
class DataPointSpec:
    id: DataPointId
    value_type: ValueType
    direction: DataPointDirection
    label: str = ""
    value_min: float | None = None
    value_max: float | None = None
    protocol: str = ""
    input_mode: str = ""
    relative_encoding: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": str(self.id),
            "module": self.id.module,
            "point": self.id.point,
            "value_type": self.value_type.value,
            "direction": self.direction.value,
            "label": self.label,
            "protocol": self.protocol,
        }
        if self.value_min is not None:
            payload["value_min"] = self.value_min
        if self.value_max is not None:
            payload["value_max"] = self.value_max
        if self.input_mode:
            payload["input_mode"] = self.input_mode
        if self.relative_encoding:
            payload["relative_encoding"] = self.relative_encoding
        return payload


@dataclass(frozen=True)
class DataPointValue:
    point_id: DataPointId
    value_type: ValueType
    timestamp: float = field(default_factory=monotonic)
    float_value: float | None = None
    bool_value: bool | None = None
    int_value: int | None = None
    midi_status: int | None = None
    midi_data: tuple[int, ...] | None = None
    osc_address: str | None = None
    osc_arguments: tuple[Any, ...] | None = None
    emit_outputs: bool = True

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": str(self.point_id),
            "value_type": self.value_type.value,
            "timestamp": self.timestamp,
        }
        if self.float_value is not None:
            payload["float_value"] = self.float_value
        if self.bool_value is not None:
            payload["bool_value"] = self.bool_value
        if self.int_value is not None:
            payload["int_value"] = self.int_value
        if self.midi_status is not None:
            payload["midi_status"] = self.midi_status
        if self.midi_data is not None:
            payload["midi_data"] = list(self.midi_data)
        if self.osc_address is not None:
            payload["osc_address"] = self.osc_address
        if self.osc_arguments is not None:
            payload["osc_arguments"] = list(self.osc_arguments)
        return payload


@dataclass(frozen=True)
class ConnectionSpec:
    """Modifier connection between source and target data points."""

    id: str
    source: str
    target: str
    modifier: ModifierKind = ModifierKind.RANGE_MAP
    input_min: float = 0.0
    input_max: float = 1.0
    output_min: float = 0.0
    output_max: float = 127.0
    invert: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "modifier": self.modifier.value,
            "input_min": self.input_min,
            "input_max": self.input_max,
            "output_min": self.output_min,
            "output_max": self.output_max,
            "invert": self.invert,
        }


def float_value(
    point_id: DataPointId | str,
    value: float,
    *,
    emit_outputs: bool = True,
) -> DataPointValue:
    resolved = point_id if isinstance(point_id, DataPointId) else DataPointId.parse(point_id)
    return DataPointValue(
        point_id=resolved,
        value_type=ValueType.FLOAT,
        float_value=value,
        emit_outputs=emit_outputs,
    )


def trigger_value(point_id: DataPointId | str, active: bool = True) -> DataPointValue:
    resolved = point_id if isinstance(point_id, DataPointId) else DataPointId.parse(point_id)
    return DataPointValue(
        point_id=resolved,
        value_type=ValueType.TRIGGER,
        bool_value=active,
    )


def midi_message_value(
    point_id: DataPointId | str,
    status: int,
    data: tuple[int, ...] = (),
    *,
    emit_outputs: bool = True,
) -> DataPointValue:
    resolved = point_id if isinstance(point_id, DataPointId) else DataPointId.parse(point_id)
    return DataPointValue(
        point_id=resolved,
        value_type=ValueType.MIDI_MESSAGE,
        midi_status=status,
        midi_data=data,
        emit_outputs=emit_outputs,
    )


def relay_value(value: DataPointValue, target: DataPointId | str) -> DataPointValue:
    resolved = target if isinstance(target, DataPointId) else DataPointId.parse(target)
    return DataPointValue(
        point_id=resolved,
        value_type=value.value_type,
        float_value=value.float_value,
        bool_value=value.bool_value,
        int_value=value.int_value,
        midi_status=value.midi_status,
        midi_data=value.midi_data,
        osc_address=value.osc_address,
        osc_arguments=value.osc_arguments,
        emit_outputs=value.emit_outputs,
    )
