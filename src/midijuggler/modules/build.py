"""Build the runtime module registry from adapters and configuration."""

from __future__ import annotations

import logging

from midijuggler.adapters.base import Adapter
from midijuggler.adapters.gpio import GpioAdapter
from midijuggler.adapters.hid import HidAdapter
from midijuggler.adapters.midi import MidiAdapter
from midijuggler.adapters.osc import OscAdapter
from midijuggler.adapters.rtp_midi import RtpMidiAdapter
from midijuggler.adapters.wing_native import WingNativeAdapter
from midijuggler.config import AppConfig
from midijuggler.datapoint.migrate import effective_connections
from midijuggler.datapoint.store import DataPointStore
from midijuggler.device.registry import DeviceRegistry
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.modules.generator.master_clock import MasterClockGenerator
from midijuggler.modules.interface.gamepi_brightness import GamePiBrightnessModule
from midijuggler.modules.interface.rotary_display import RotaryDisplayModule
from midijuggler.modules.interface.web import WebInterfaceModule
from midijuggler.modules.io.gpio import GpioIOModule
from midijuggler.modules.io.hid import HidIOModule
from midijuggler.modules.io.midi import MidiIOModule
from midijuggler.modules.io.osc import OscIOModule
from midijuggler.modules.io.rtp_midi import RtpMidiIOModule
from midijuggler.modules.io.wing_native import WingNativeIOModule
from midijuggler.modules.modifier.graph import ModifierGraph
from midijuggler.modules.registry import ModuleRegistry
from midijuggler.web.server import WebInterface

LOGGER = logging.getLogger(__name__)


def build_module_registry(
    config: AppConfig,
    store: DataPointStore,
    bus: EventBus,
    adapters: list[Adapter],
    master_clock: MasterClock,
    web: WebInterface,
    device_registry: DeviceRegistry,
) -> tuple[
    ModuleRegistry,
    dict[str, MidiIOModule | OscIOModule | RtpMidiIOModule | WingNativeIOModule],
]:
    registry = ModuleRegistry()
    io_modules: dict[str, MidiIOModule | OscIOModule | RtpMidiIOModule | WingNativeIOModule] = {}

    for adapter in adapters:
        device = device_registry.device_for_adapter(adapter.name)
        if device is None:
            if adapter.config.enabled:
                LOGGER.warning(
                    "adapter %s is enabled but has no bound device; skipping I/O module",
                    adapter.name,
                )
            continue
        if isinstance(adapter, GpioAdapter):
            registry.add(GpioIOModule(adapter, device, store, device_registry))
        elif isinstance(adapter, HidAdapter):
            registry.add(HidIOModule(adapter, device, store, device_registry))
        elif isinstance(adapter, MidiAdapter):
            module = MidiIOModule(adapter, device, store, config, device_registry)
            registry.add(module)
            io_modules[adapter.name] = module
        elif isinstance(adapter, OscAdapter):
            module = OscIOModule(adapter, device, store, config, device_registry)
            registry.add(module)
            io_modules[adapter.name] = module
        elif isinstance(adapter, RtpMidiAdapter):
            module = RtpMidiIOModule(adapter, device, store, config, device_registry)
            registry.add(module)
            io_modules[adapter.name] = module
        elif isinstance(adapter, WingNativeAdapter):
            module = WingNativeIOModule(adapter, device, store, config, device_registry)
            registry.add(module)
            io_modules[adapter.name] = module

    connections = effective_connections(
        config,
        datapoint_routing=config.runtime.datapoint_routing,
    )
    registry.add(
        ModifierGraph(
            store,
            connections,
            feedback_suppress_ms=config.runtime.feedback_suppress_ms,
        )
    )
    registry.add(MasterClockGenerator(master_clock, store))
    registry.add(GamePiBrightnessModule(store))
    if config.rotary_display.enabled:
        registry.add(
            RotaryDisplayModule(
                store,
                config.rotary_display,
                master_clock,
                bus,
            )
        )
    registry.add(WebInterfaceModule(web, store))
    return registry, io_modules
