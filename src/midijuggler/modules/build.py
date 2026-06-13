"""Build the runtime module registry from adapters and configuration."""

from __future__ import annotations

from midijuggler.adapters.base import Adapter
from midijuggler.adapters.gpio import GpioAdapter
from midijuggler.adapters.midi import MidiAdapter
from midijuggler.adapters.osc import OscAdapter
from midijuggler.adapters.rtp_midi import RtpMidiAdapter
from midijuggler.config import AppConfig
from midijuggler.datapoint.bridge import connections_from_legacy_mappings
from midijuggler.datapoint.store import DataPointStore
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.modules.generator.master_clock import MasterClockGenerator
from midijuggler.modules.interface.web import WebInterfaceModule
from midijuggler.modules.io.gpio import GpioIOModule
from midijuggler.modules.io.midi import MidiIOModule
from midijuggler.modules.io.osc import OscIOModule
from midijuggler.modules.io.rtp_midi import RtpMidiIOModule
from midijuggler.modules.modifier.graph import ModifierGraph
from midijuggler.modules.registry import ModuleRegistry
from midijuggler.web.server import WebInterface


def build_module_registry(
    config: AppConfig,
    store: DataPointStore,
    bus: EventBus,
    adapters: list[Adapter],
    master_clock: MasterClock,
    web: WebInterface,
) -> tuple[ModuleRegistry, dict[str, MidiIOModule | OscIOModule | RtpMidiIOModule]]:
    registry = ModuleRegistry()
    io_modules: dict[str, MidiIOModule | OscIOModule | RtpMidiIOModule] = {}

    for adapter in adapters:
        if isinstance(adapter, GpioAdapter):
            registry.add(GpioIOModule(adapter, store))
        elif isinstance(adapter, MidiAdapter):
            module = MidiIOModule(adapter, store, config)
            registry.add(module)
            io_modules[adapter.name] = module
        elif isinstance(adapter, OscAdapter):
            module = OscIOModule(adapter, store, config)
            registry.add(module)
            io_modules[adapter.name] = module
        elif isinstance(adapter, RtpMidiAdapter):
            module = RtpMidiIOModule(adapter, store, config)
            registry.add(module)
            io_modules[adapter.name] = module

    connections = list(config.connections)
    if not connections:
        connections = connections_from_legacy_mappings(config.mappings)
    registry.add(ModifierGraph(store, connections))
    registry.add(MasterClockGenerator(master_clock, store))
    registry.add(WebInterfaceModule(web, store))
    return registry, io_modules
