"""Logical device layer between I/O adapters and connections."""

from midijuggler.device.export import export_device, export_devices, import_device, import_devices
from midijuggler.device.registry import DeviceRegistry
from midijuggler.device.types import CustomPointSpec, DeviceConfig

__all__ = [
    "CustomPointSpec",
    "DeviceConfig",
    "DeviceRegistry",
    "MIDI_OUT_POINT",
    "build_device_datapoints",
    "export_device",
    "export_devices",
    "import_device",
    "import_devices",
    "library_address_for_point",
]


def __getattr__(name: str):
    if name in {"MIDI_OUT_POINT", "build_device_datapoints", "library_address_for_point"}:
        from midijuggler.device import points as points_module

        return getattr(points_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
