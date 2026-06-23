"""Convenience lookups for device-bound adapters."""

from __future__ import annotations

from midijuggler.config import AppConfig
from midijuggler.device.registry import DeviceRegistry


def device_id_for_adapter(config: AppConfig, adapter_name: str) -> str:
    return DeviceRegistry.from_config(config).require_device_for_adapter(adapter_name).id
