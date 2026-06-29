"""Runtime lookup between devices, adapters, and libraries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from midijuggler.device.types import DeviceConfig

if TYPE_CHECKING:
    from midijuggler.config import AdapterConfig, AppConfig


class DeviceRegistry:
    """Resolve adapter instances and connection endpoints to devices."""

    def __init__(self, devices: dict[str, DeviceConfig], adapters: dict[str, AdapterConfig]) -> None:
        self._devices = dict(devices)
        self._adapters = adapters
        self._adapter_to_device: dict[str, str] = {}
        for device in devices.values():
            if device.adapter in self._adapter_to_device:
                existing = self._adapter_to_device[device.adapter]
                raise ValueError(
                    f"adapter {device.adapter!r} is already bound to device {existing!r}"
                )
            self._adapter_to_device[device.adapter] = device.uid

    @classmethod
    def from_config(cls, config: AppConfig) -> DeviceRegistry:
        return cls(config.devices, config.adapters)

    def reload_from_config(self, config: AppConfig) -> None:
        """Replace registry contents from the current app config."""
        self._devices = dict(config.devices)
        self._adapters = config.adapters
        self._adapter_to_device = {}
        for device in self._devices.values():
            if device.adapter in self._adapter_to_device:
                existing = self._adapter_to_device[device.adapter]
                raise ValueError(
                    f"adapter {device.adapter!r} is already bound to device {existing!r}"
                )
            self._adapter_to_device[device.adapter] = device.uid

    def devices(self) -> list[DeviceConfig]:
        return list(self._devices.values())

    def get(self, device_id: str) -> DeviceConfig | None:
        return self._devices.get(device_id)

    def require(self, device_id: str) -> DeviceConfig:
        device = self.get(device_id)
        if device is None:
            raise ValueError(f"unknown device: {device_id!r}")
        return device

    def device_for_adapter(self, adapter_name: str) -> DeviceConfig | None:
        device_id = self._adapter_to_device.get(adapter_name)
        if device_id is None:
            return None
        return self._devices.get(device_id)

    def device_library_for_adapter(self, adapter_name: str) -> str:
        device = self.device_for_adapter(adapter_name)
        if device is None:
            return ""
        return str(device.library or "").strip()

    def require_device_for_adapter(self, adapter_name: str) -> DeviceConfig:
        device = self.device_for_adapter(adapter_name)
        if device is None:
            raise ValueError(f"no device bound to adapter {adapter_name!r}")
        return device

    def adapter_for_device(self, device_id: str) -> AdapterConfig:
        device = self.require(device_id)
        adapter = self._adapters.get(device.adapter)
        if adapter is None:
            raise ValueError(
                f"device {device_id!r} references missing adapter {device.adapter!r}"
            )
        return adapter

    def resolved_library_kind(self, device: DeviceConfig) -> str:
        if device.library_kind:
            return device.library_kind
        adapter = self.adapter_for_device(device.id)
        kind = adapter.kind or device.adapter
        if kind == "wing_native":
            return "wing"
        return kind

    def validate_connection_endpoint(self, point_id: str) -> None:
        module = point_id.partition(".")[0]
        if module in {"clock", "mapping"}:
            return
        if module not in self._devices:
            raise ValueError(
                f"connection endpoint {point_id!r} must reference a configured device id"
            )
