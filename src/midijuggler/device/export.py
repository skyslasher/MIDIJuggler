"""Import and export device definitions."""

from __future__ import annotations

import json
from typing import Any

from midijuggler.device.types import CustomPointSpec, DeviceConfig


def export_device(device: DeviceConfig) -> dict[str, Any]:
    return device.as_dict()


def export_devices(devices: list[DeviceConfig]) -> list[dict[str, Any]]:
    return [export_device(device) for device in devices]


def import_device(raw: Any) -> DeviceConfig:
    if not isinstance(raw, dict):
        raise ValueError("device must be an object")
    device_id = str(raw.get("id", "")).strip()
    adapter = str(raw.get("adapter", "")).strip()
    if not device_id:
        raise ValueError("device.id is required")
    if not adapter:
        raise ValueError("device.adapter is required")
    custom_points = tuple(
        _import_custom_point(index, item)
        for index, item in enumerate(raw.get("custom_points", []), start=1)
    )
    return DeviceConfig(
        id=device_id,
        adapter=adapter,
        library=str(raw.get("library", "")).strip(),
        library_kind=str(raw.get("library_kind", "")).strip(),
        label=str(raw.get("label", "")).strip(),
        custom_points=custom_points,
    )


def import_devices(raw: Any) -> list[DeviceConfig]:
    if not isinstance(raw, list):
        raise ValueError("devices must be a list")
    return [import_device(item) for item in raw]


def export_devices_json(devices: list[DeviceConfig]) -> str:
    return json.dumps(export_devices(devices), indent=2, sort_keys=True)


def import_devices_json(text: str) -> list[DeviceConfig]:
    return import_devices(json.loads(text))


def _import_custom_point(index: int, raw: Any) -> CustomPointSpec:
    if not isinstance(raw, dict):
        raise ValueError(f"custom_points[{index}] must be an object")
    point_id = str(raw.get("id", "")).strip()
    if not point_id:
        raise ValueError(f"custom_points[{index}].id is required")
    return CustomPointSpec(
        id=point_id,
        value_type=str(raw.get("value_type", "float")),
        direction=str(raw.get("direction", "bidirectional")),
        label=str(raw.get("label", "")),
        value_min=float(raw.get("value_min", 0.0)),
        value_max=float(raw.get("value_max", 127.0)),
        protocol=str(raw.get("protocol", "")),
        input_mode=str(raw.get("input_mode", "")),
        relative_encoding=str(raw.get("relative_encoding", "")),
    )
