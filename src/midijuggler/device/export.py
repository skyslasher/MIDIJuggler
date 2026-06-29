"""Import and export device definitions."""

from __future__ import annotations

import json
from typing import Any

from midijuggler.device.identity import generate_device_uid, parse_device_identity
from midijuggler.device.types import CustomPointSpec, DeviceConfig


def export_device(device: DeviceConfig) -> dict[str, Any]:
    return device.as_dict()


def export_devices(devices: list[DeviceConfig]) -> list[dict[str, Any]]:
    return [export_device(device) for device in devices]


def import_device(raw: Any) -> DeviceConfig:
    from midijuggler.midi.xtouch_channels import (
        DEFAULT_XTOUCH_DISPLAY_CHANNEL,
        DEFAULT_XTOUCH_VALUE_CHANNEL,
        XTOUCH_MINI_LIBRARY_ID,
        parse_midi_channel_option,
    )
    from midijuggler.midi.xtouch_feedback import parse_feedback_refresh_interval

    if not isinstance(raw, dict):
        raise ValueError("device must be an object")
    adapter = str(raw.get("adapter", "")).strip()
    if not adapter:
        raise ValueError("device.adapter is required")
    uid_raw = str(raw.get("uid", "")).strip() or str(raw.get("id", "")).strip()
    if not uid_raw:
        uid_raw = generate_device_uid(adapter)
    uid, name = parse_device_identity({**raw, "uid": uid_raw}, field_name="device")
    custom_points = tuple(
        _import_custom_point(index, item)
        for index, item in enumerate(raw.get("custom_points", []), start=1)
    )
    library = str(raw.get("library", "")).strip()
    feedback_refresh_interval = 0.0
    midi_value_channel = DEFAULT_XTOUCH_VALUE_CHANNEL
    midi_display_channel = DEFAULT_XTOUCH_DISPLAY_CHANNEL
    if "feedback_refresh_interval" in raw:
        feedback_refresh_interval = parse_feedback_refresh_interval(
            raw["feedback_refresh_interval"]
        )
    if "midi_value_channel" in raw:
        midi_value_channel = parse_midi_channel_option(
            raw["midi_value_channel"],
            field_name="device.midi_value_channel",
            default=DEFAULT_XTOUCH_VALUE_CHANNEL,
        )
    if "midi_display_channel" in raw:
        midi_display_channel = parse_midi_channel_option(
            raw["midi_display_channel"],
            field_name="device.midi_display_channel",
            default=DEFAULT_XTOUCH_DISPLAY_CHANNEL,
        )
    if feedback_refresh_interval > 0 and library != XTOUCH_MINI_LIBRARY_ID:
        raise ValueError(
            "feedback_refresh_interval is only supported for behringer_xtouch_mini"
        )
    if library != XTOUCH_MINI_LIBRARY_ID and (
        "midi_value_channel" in raw or "midi_display_channel" in raw
    ):
        raise ValueError(
            "midi_value_channel and midi_display_channel are only supported for "
            "behringer_xtouch_mini"
        )
    return DeviceConfig(
        uid=uid,
        name=name,
        adapter=adapter,
        library=library,
        library_kind=str(raw.get("library_kind", "")).strip(),
        label=str(raw.get("label", "")).strip(),
        custom_points=custom_points,
        feedback_refresh_interval=feedback_refresh_interval,
        midi_value_channel=midi_value_channel,
        midi_display_channel=midi_display_channel,
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
