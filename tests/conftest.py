"""Shared helpers for device-layer test configs."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from midijuggler.adapters.midi import MidiAdapter
    from midijuggler.config import AppConfig
    from midijuggler.datapoint.store import DataPointStore
    from midijuggler.device.registry import DeviceRegistry
    from midijuggler.eventbus import EventBus
    from midijuggler.modules.io.midi import MidiIOModule


def gpio_device(device_id: str = "gpio", adapter: str = "gpio") -> dict:
    return {"id": device_id, "adapter": adapter, "library_kind": "gpio"}


def midi_device(
    device_id: str,
    *,
    adapter: str | None = None,
    library: str = "",
) -> dict:
    entry = {"id": device_id, "adapter": adapter or device_id, "library_kind": "midi"}
    if library:
        entry["library"] = library
    return entry


def osc_device(
    device_id: str,
    library: str,
    *,
    adapter: str | None = None,
    library_kind: str = "osc",
) -> dict:
    return {
        "id": device_id,
        "adapter": adapter or device_id,
        "library": library,
        "library_kind": library_kind,
    }


def wing_device(
    device_id: str,
    *,
    adapter: str | None = None,
    library: str = "behringer_wing",
) -> dict:
    return {
        "id": device_id,
        "adapter": adapter or device_id,
        "library": library,
        "library_kind": "wing",
    }


def hid_device(device_id: str = "gamepad", adapter: str = "gamepad") -> dict:
    return {"id": device_id, "adapter": adapter, "library_kind": "hid"}


def midi_custom_point(point_id: str, **options) -> dict:
    return {"id": point_id, "direction": "bidirectional", **options}


def make_midi_io_module(
    config: AppConfig,
    store: DataPointStore,
    adapter_name: str = "xtouch_mini",
    bus: EventBus | None = None,
) -> tuple[MidiIOModule, MidiAdapter, DeviceRegistry]:
    from midijuggler.adapters.midi import MidiAdapter
    from midijuggler.device.registry import DeviceRegistry
    from midijuggler.eventbus import EventBus
    from midijuggler.modules.io.midi import MidiIOModule

    bus = bus or EventBus()
    registry = DeviceRegistry.from_config(config)
    device = registry.require_device_for_adapter(adapter_name)
    adapter = MidiAdapter(
        adapter_name,
        config.adapters[adapter_name],
        bus,
        app_config=config,
    )
    module = MidiIOModule(adapter, device, store, config, registry)
    return module, adapter, registry


def make_osc_io_module(
    config: AppConfig,
    store: DataPointStore,
    adapter_name: str,
    bus: EventBus | None = None,
):
    from midijuggler.adapters.osc import OscAdapter
    from midijuggler.device.registry import DeviceRegistry
    from midijuggler.eventbus import EventBus
    from midijuggler.modules.io.osc import OscIOModule

    bus = bus or EventBus()
    registry = DeviceRegistry.from_config(config)
    device = registry.require_device_for_adapter(adapter_name)
    adapter = OscAdapter(adapter_name, config.adapters[adapter_name], bus)
    module = OscIOModule(adapter, device, store, config, registry)
    return module, adapter, registry


def make_hid_io_module(
    config: AppConfig,
    adapter,
    store: DataPointStore,
    adapter_name: str,
):
    from midijuggler.device.registry import DeviceRegistry
    from midijuggler.modules.io.hid import HidIOModule

    registry = DeviceRegistry.from_config(config)
    device = registry.require_device_for_adapter(adapter_name)
    module = HidIOModule(adapter, device, store, registry)
    return module, registry


def make_wing_io_module(
    config: AppConfig,
    adapter,
    store: DataPointStore,
    adapter_name: str,
):
    from midijuggler.device.registry import DeviceRegistry
    from midijuggler.modules.io.wing_native import WingNativeIOModule

    registry = DeviceRegistry.from_config(config)
    device = registry.require_device_for_adapter(adapter_name)
    module = WingNativeIOModule(adapter, device, store, config, registry)
    return module, registry


def xtouch_devices_config(**device_options) -> dict:
    return {
        "adapters": {
            "xtouch_mini": {
                "enabled": True,
                "type": "midi",
            }
        },
        "devices": [
            {
                **midi_device("xtouch_mini", library="behringer_xtouch_mini"),
                **device_options,
            },
        ],
    }


def make_bridge(
    config: AppConfig,
    store: DataPointStore,
    bus: EventBus | None = None,
):
    from midijuggler.datapoint.bridge import EventToDataPointBridge
    from midijuggler.device.registry import DeviceRegistry
    from midijuggler.eventbus import EventBus

    bus = bus or EventBus()
    registry = DeviceRegistry.from_config(config)
    bridge = EventToDataPointBridge(store, bus, registry)
    return bridge, registry
