"""Service orchestration for MIDIJuggler."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import replace
from pathlib import Path

from midijuggler.adapters import build_adapters
from midijuggler.adapters.base import Adapter
from midijuggler.adapters.gpio import GpioAdapter
from midijuggler.adapters.hid import HidAdapter
from midijuggler.adapters.rtp_midi import RtpMidiAdapter
from midijuggler.adapters.midi import MidiAdapter
from midijuggler.adapters.osc import OscAdapter
from midijuggler.adapters.wing_native import WingNativeAdapter
from midijuggler.alsa import (
    MASTER_CLOCK_PCM_NAME,
    alsa_config_path_for_config,
    resolve_alsa_output_device,
    write_master_clock_pcm_config,
)
from midijuggler.clock import ClockBpmTracker
from midijuggler.config import AppConfig, load_config
from midijuggler.datapoint.bridge import EventToDataPointBridge
from midijuggler.datapoint.store import DataPointStore
from midijuggler.eventbus import EventBus
from midijuggler.events import (
    BpmChangedEvent,
    MasterClockCommandEvent,
    MidiClockEvent,
    MidiMessageEvent,
    OscMessageEvent,
)
from midijuggler.master_clock import MIDI_TIMING_CLOCK, MasterClock
from midijuggler.device.registry import DeviceRegistry
from midijuggler.device.lookup import device_id_for_adapter
from midijuggler.modules.build import build_module_registry
from midijuggler.modules.interface.bandhelper.module import BandHelperModule
from midijuggler.modules.interface.gamepi_brightness import GamePiBrightnessModule
from midijuggler.modules.interface.rotary_display.module import RotaryDisplayModule
from midijuggler.modules.modifier.graph import ModifierGraph
from midijuggler.modules.io.midi import MidiIOModule
from midijuggler.modules.io.osc import OscIOModule
from midijuggler.modules.io.rtp_midi import RtpMidiIOModule
from midijuggler.rtp_midi import RtpMidiManager
from midijuggler.osc.desk_tracker import OscDeskDiscoveryManager
from midijuggler.web.monitor_log import MonitorLogHandler
from midijuggler.web.server import WebInterface, run_web_server, stop_web_server

LOGGER = logging.getLogger(__name__)

IOModule = MidiIOModule | OscIOModule | RtpMidiIOModule


class MIDIJugglerService:
    """Wire core services, adapters and web UI together."""

    def __init__(self, config: AppConfig, config_path: str | Path | None = None) -> None:
        self.config = config
        self.config_path = Path(config_path) if config_path is not None else None
        self.alsa_config_path = alsa_config_path_for_config(self.config_path)
        self.bus = EventBus()
        self.datapoint_store = DataPointStore()
        self.clock = ClockBpmTracker()
        self.device_registry = DeviceRegistry.from_config(config)
        self.rtp_midi_manager = RtpMidiManager()
        self.adapters = build_adapters(
            config.adapters,
            self.bus,
            rtp_midi_manager=self.rtp_midi_manager,
            app_config=config,
        )
        for adapter in self.adapters:
            if isinstance(adapter, MidiAdapter):
                adapter.bind_datapoint_store(self.datapoint_store)
        self._write_master_clock_alsa_config(self.config.master_clock.click_audio_device)
        self.master_clock = MasterClock(
            self._master_clock_config(),
            self.bus,
            click_audio_device=None,
            alsa_config_path=self.alsa_config_path,
        )
        self.web = WebInterface(
            config,
            self.bus,
            self.clock,
            self.master_clock,
            gpio_adapter=self._gpio_adapter(),
            hid_adapters=self._hid_adapters(),
            midi_adapters=self._midi_adapters(),
            rtp_midi_adapters=self._rtp_midi_adapters(),
            osc_adapters=self._osc_adapters(),
            wing_native_adapters=self._wing_native_adapters(),
            rtp_midi_manager=self.rtp_midi_manager,
            runtime_adapters=self.adapters,
            device_registry=self.device_registry,
            config_path=self.config_path,
            alsa_config_path=self.alsa_config_path,
            datapoint_store=self.datapoint_store,
        )
        self.osc_desk_tracker = OscDeskDiscoveryManager(self.web)
        self.web.osc_desk_tracker = self.osc_desk_tracker
        self.event_bridge = EventToDataPointBridge(
            self.datapoint_store,
            self.bus,
            self.device_registry,
        )
        self.module_registry, self.io_modules = build_module_registry(
            config,
            self.datapoint_store,
            self.bus,
            self.adapters,
            self.master_clock,
            self.web,
            self.device_registry,
        )
        for module in self.module_registry.modules():
            if isinstance(module, RotaryDisplayModule):
                self.web.bind_rotary_display_module(module)
            elif isinstance(module, BandHelperModule):
                self.web.bind_bandhelper_module(module)
            elif isinstance(module, GamePiBrightnessModule):
                self.web.bind_gamepi_module(module)
        self.web.bind_osc_io_modules(self.io_modules)
        for module in self.module_registry.modules():
            if isinstance(module, ModifierGraph):
                self.web.modifier_graph = module
                break
        if config.runtime.datapoint_routing:
            from midijuggler.modules.generator.master_clock import MasterClockGenerator

            for module in self.module_registry.modules():
                if isinstance(module, MasterClockGenerator):
                    self.master_clock.bind_datapoint_sink(module)
                    break
        self._runner = None
        self._monitor_log_handler: MonitorLogHandler | None = None

        self.bus.subscribe(MidiClockEvent, self._track_clock)
        self.bus.subscribe(MidiMessageEvent, self._handle_midi_message)
        self.bus.subscribe(OscMessageEvent, self._handle_osc_message)
        self.bus.subscribe(MasterClockCommandEvent, self._handle_master_clock_command)

    async def start(self) -> None:
        LOGGER.info("starting MIDIJuggler")
        loop = asyncio.get_running_loop()
        self._monitor_log_handler = MonitorLogHandler(self.bus, loop)
        self._monitor_log_handler.setLevel(logging.DEBUG)
        logging.getLogger("midijuggler").addHandler(self._monitor_log_handler)
        self._monitor_log_handler.start()
        await self.rtp_midi_manager.start()
        LOGGER.info("RTP-MIDI status: %s", self.rtp_midi_manager.status_summary())
        await self.osc_desk_tracker.start()
        LOGGER.info(
            "OSC desk discovery active; %s desk(s) on LAN",
            len(self.osc_desk_tracker.discovered_desks),
        )
        await self.module_registry.start_all()
        await self.web.refresh_all_device_datapoints()
        if self.web.modifier_graph is not None:
            await self.web.modifier_graph.replay_subscribed_sources_from_store()
        self.event_bridge.attach()
        for adapter in self.adapters:
            await adapter.start()
        await self.master_clock.start()
        self._runner = await run_web_server(self.web)
        LOGGER.info(
            "web interface listening on http://%s:%s",
            self.config.web.host,
            self.config.web.port,
        )

    async def stop(self) -> None:
        LOGGER.info("stopping MIDIJuggler")
        if self._monitor_log_handler is not None:
            logging.getLogger("midijuggler").removeHandler(self._monitor_log_handler)
            await self._monitor_log_handler.stop()
            self._monitor_log_handler = None
        if self._runner is not None:
            await stop_web_server(self._runner)
            self._runner = None
        await self.module_registry.stop_all()
        await self.master_clock.stop()
        for adapter in reversed(self.adapters):
            await adapter.stop()
        await self.osc_desk_tracker.stop()
        await self.rtp_midi_manager.stop()

    async def run_forever(self) -> None:
        await self.start()
        try:
            await asyncio.Event().wait()
        finally:
            await self.stop()

    async def _track_clock(self, event: MidiClockEvent) -> None:
        bpm = self.clock.tick(event.timestamp)
        if bpm is not None:
            await self.bus.publish(BpmChangedEvent(source="clock", bpm=bpm))

    async def _handle_midi_message(self, event: MidiMessageEvent) -> None:
        if (
            event.direction == "input"
            and self.config.master_clock.enabled
            and not self.config.runtime.datapoint_routing
        ):
            if event.source in self._allowed_midi_input_sources():
                await self.master_clock.handle_midi_message(event)
            return

        if event.direction != "output":
            return
        if event.source != "master_clock":
            return
        adapter = self._adapter_for_target(event.target)
        if adapter is None:
            if event.status == MIDI_TIMING_CLOCK:
                return
            LOGGER.warning("no enabled adapter for MIDI target %s", event.target)
            return
        await adapter.send_midi_message(event)

    async def _handle_osc_message(self, event: OscMessageEvent) -> None:
        if event.direction != "input":
            return
        if (
            self.config.master_clock.enabled
            and event.source in self._allowed_osc_input_sources()
        ):
            command = self.master_clock.remote.command_from_osc(event)
            if command is not None:
                await self.master_clock.handle_command(command)

    async def _handle_master_clock_command(self, event: MasterClockCommandEvent) -> None:
        if self.config.master_clock.enabled:
            await self.master_clock.handle_command(event)

    def _adapter_for_target(self, target: str) -> Adapter | None:
        adapter_name = target.split(":", 1)[0]
        return next((adapter for adapter in self.adapters if adapter.name == adapter_name), None)

    def _enabled_adapter_names(self, kinds: set[str]) -> set[str]:
        return {
            adapter.name
            for adapter in self.adapters
            if adapter.config.enabled and (adapter.config.kind or adapter.name) in kinds
        }

    def _allowed_midi_input_sources(self) -> set[str]:
        enabled = self._enabled_adapter_names({"midi", "rtp_midi"})
        configured = self.config.master_clock.midi_input_targets
        if configured is None:
            return enabled
        return enabled & set(configured)

    def _allowed_osc_input_sources(self) -> set[str]:
        enabled = self._enabled_adapter_names({"osc"})
        configured = self.config.master_clock.osc_input_targets
        if configured is None:
            return enabled
        return enabled & set(configured)

    def _gpio_adapter(self) -> GpioAdapter | None:
        return next(
            (adapter for adapter in self.adapters if isinstance(adapter, GpioAdapter)),
            None,
        )

    def _hid_adapters(self) -> dict[str, HidAdapter]:
        return {
            adapter.name: adapter
            for adapter in self.adapters
            if isinstance(adapter, HidAdapter)
        }

    def _midi_adapters(self) -> dict[str, MidiAdapter]:
        return {
            adapter.name: adapter
            for adapter in self.adapters
            if isinstance(adapter, MidiAdapter)
        }

    def _osc_adapters(self) -> dict[str, OscAdapter]:
        return {
            adapter.name: adapter
            for adapter in self.adapters
            if isinstance(adapter, OscAdapter)
        }

    def _wing_native_adapters(self) -> dict[str, WingNativeAdapter]:
        return {
            adapter.name: adapter
            for adapter in self.adapters
            if isinstance(adapter, WingNativeAdapter)
        }

    def _rtp_midi_adapters(self) -> dict[str, RtpMidiAdapter]:
        return {
            adapter.name: adapter
            for adapter in self.adapters
            if isinstance(adapter, RtpMidiAdapter)
        }

    def _master_clock_config(self):
        from midijuggler.datapoint.clock_connections import usable_clock_output_targets

        output_targets = usable_clock_output_targets(
            self.config.master_clock.output_targets,
            self.config.devices,
            self.config.adapters,
        )
        return replace(self.config.master_clock, output_targets=output_targets)

    def _write_master_clock_alsa_config(self, audio_device: str) -> None:
        if self.alsa_config_path is None:
            return
        try:
            write_master_clock_pcm_config(
                self.alsa_config_path,
                resolve_alsa_output_device(audio_device),
            )
        except OSError:
            LOGGER.exception(
                "could not write ALSA dmix config for master clock to %s",
                self.alsa_config_path,
            )


async def run_from_config(config_path: str) -> None:
    config = load_config(config_path)
    for issue in config.load_issues:
        LOGGER.error("Configuration issue: %s", issue)
    service = MIDIJugglerService(config, config_path=config_path)
    with contextlib.suppress(asyncio.CancelledError):
        await service.run_forever()
