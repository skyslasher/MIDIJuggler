"""Device configuration types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CustomPointSpec:
    """User-defined data point on a device."""

    id: str
    value_type: str = "float"
    direction: str = "bidirectional"
    label: str = ""
    value_min: float = 0.0
    value_max: float = 127.0
    protocol: str = ""
    input_mode: str = ""
    relative_encoding: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "value_type": self.value_type,
            "direction": self.direction,
        }
        if self.label:
            payload["label"] = self.label
        if self.value_min != 0.0:
            payload["value_min"] = self.value_min
        if self.value_max != 127.0:
            payload["value_max"] = self.value_max
        if self.protocol:
            payload["protocol"] = self.protocol
        if self.input_mode:
            payload["input_mode"] = self.input_mode
        if self.relative_encoding:
            payload["relative_encoding"] = self.relative_encoding
        return payload


@dataclass(frozen=True)
class DeviceConfig:
    """Logical device bound to one I/O adapter instance."""

    id: str
    adapter: str
    library: str = ""
    library_kind: str = ""
    label: str = ""
    custom_points: tuple[CustomPointSpec, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "adapter": self.adapter,
        }
        if self.label:
            payload["label"] = self.label
        if self.library:
            payload["library"] = self.library
        if self.library_kind:
            payload["library_kind"] = self.library_kind
        if self.custom_points:
            payload["custom_points"] = [point.as_dict() for point in self.custom_points]
        return payload
