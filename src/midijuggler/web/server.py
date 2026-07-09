"""aiohttp web interface for monitoring MIDIJuggler."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import mimetypes
import time
import tomllib
from dataclasses import replace
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import WSMsgType, web

from midijuggler.adapters.base import Adapter
from midijuggler.adapters.gpio import GpioAdapter, RASPBERRY_PI_HEADER_BCM_PINS
from midijuggler.adapters.hid import HidAdapter
from midijuggler.adapters.midi import MidiAdapter
from midijuggler.adapters.osc import OscAdapter
from midijuggler.adapters.wing_native import WingNativeAdapter
from midijuggler.adapters.rtp_midi import RtpMidiAdapter
from midijuggler.alsa import (
    lookup_alsa_output_device,
    normalize_alsa_output_device,
    resolve_alsa_output_device,
    write_master_clock_pcm_config,
)
from midijuggler.clock import CLICK_INTERVALS, ClockBpmTracker
from midijuggler.config import (
    adapter_device_options,
    DEFAULT_ADAPTERS,
    AdapterConfig,
    AppConfig,
    BandHelperConfig,
    GamePiConfig,
    MasterClockConfig,
    RuntimeConfig,
    RotaryDisplayConfig,
    RotaryDisplayDeviceConfig,
    _validate_adapter_instance_name,
    _validate_tap_tempo_min_taps,
    _validate_bpm_step,
    _validate_beat_flash_ms,
    parse_config,
    save_devices,
    save_gpio_adapter_options,
    supplement_devices,
    normalize_device_libraries,
    update_suppressed_inferred_device_adapters,
    save_connections,
    save_master_clock_config,
    save_bandhelper_config,
    save_gamepi_config,
    save_rotary_display_config,
    save_runtime_config,
    remove_midi_adapter_configs,
    remove_osc_adapter_configs,
    remove_wing_native_adapter_configs,
    remove_hid_adapter_configs,
    save_midi_adapter_configs,
    save_osc_adapter_configs,
    save_wing_native_adapter_configs,
    save_hid_adapter_configs,
)
from midijuggler.hid.codes import (
    hid_available,
    hid_device_key,
    list_input_devices,
    lookup_input_device,
    normalize_hid_device_options,
    parse_hid_device_key,
)
from midijuggler.modules.io.gpio import GpioIOModule
from midijuggler.modules.io.hid import HidIOModule
from midijuggler.modules.io.midi import MidiIOModule
from midijuggler.modules.io.osc import OscIOModule
from midijuggler.modules.io.wing_native import WingNativeIOModule
from midijuggler.modules.modifier.feedback_suppress import parse_feedback_suppress_ms
from midijuggler.eventbus import EventBus
from midijuggler.events import (
    AdapterStatusEvent,
    Event,
    MasterClockCommandEvent,
    MasterClockStateEvent,
    MidiMessageEvent,
)
from midijuggler.master_clock import quantize_bpm, TAP_TEMPO_BPM_QUANTIZE_STEP
from midijuggler.learn import (
    LearnController,
    lookup_datapoint_ranges,
    lookup_osc_target_ranges,
    resolve_monitor_source,
    resolve_osc_target_address,
    resolve_target_datapoint,
    reverse_connection,
    upsert_connection,
)
from midijuggler.device.export import export_device, export_devices, import_device, import_devices
from midijuggler.device.identity import validate_device_name
from midijuggler.device.registry import DeviceRegistry
from midijuggler.device.types import DeviceConfig
from midijuggler.midi.target_encode import (
    encode_midi_target_message,
    lookup_midi_target_ranges,
    resolve_midi_target_parameter,
)
from midijuggler.midi.echo_guard import DEFAULT_ECHO_GUARD_MS, parse_echo_guard_ms
from midijuggler.midi_library import get_midi_library, list_midi_libraries
from midijuggler.master_clock import MasterClock
from midijuggler.rtp_midi.manager import RtpMidiManager
from midijuggler.osc.desk_protocol import (
    apply_desk_options,
    desk_mode_for_library,
    desk_protocol_for_library,
    is_desk_library,
    osc_library_for_desk_mode,
)
from midijuggler.osc.discovery import (
    DiscoveredDesk,
    desk_identity,
    discover_desks,
    discovery_scan_networks,
)
from midijuggler.osc_library import get_osc_library, list_osc_libraries
from midijuggler.connection.bundle import (
    apply_connection_bundle_import,
    export_connection_bundle,
    preview_connection_bundle_import,
)
from midijuggler.datapoint.bridge import adapter_control_to_datapoint
from midijuggler.datapoint.migrate import effective_connections, implicit_connections, stored_connections
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    ConnectionSpec,
    DataPointId,
    DataPointValue,
    ModifierKind,
    SCALE_CURVES,
    ValueType,
    float_value,
)
from midijuggler.modules.modifier.graph import ModifierGraph
from midijuggler.web.monitor_coalesce import (
    MonitorCoalescer,
    monitor_datapoint_key,
    monitor_event_key,
)

if TYPE_CHECKING:
    from midijuggler.modules.interface.bandhelper.module import BandHelperModule
    from midijuggler.modules.interface.gamepi_brightness import GamePiBrightnessModule
    from midijuggler.modules.interface.rotary_display.module import RotaryDisplayModule
from midijuggler.system_hostname import (
    apply_hostname,
    can_restart_service,
    can_set_hostname,
    capability_message,
    get_hostname,
    restart_service,
    system_diagnostics,
    validate_hostname,
)
from midijuggler.system_info import (
    enrich_midi_port_choice,
    list_alsa_output_devices,
    list_click_wavs,
    list_midi_input_ports,
    list_midi_output_ports,
    list_midi_ports,
    lookup_midi_port,
    normalize_midi_port_id,
)

LOGGER = logging.getLogger(__name__)

CLOCK_TRIGGER_POINTS = frozenset(
    {
        "bpm_up",
        "bpm_down",
        "bpm_huge_up",
        "bpm_huge_down",
        "start",
        "stop",
        "start_stop",
        "tap_tempo",
        "click_toggle",
    }
)

_CLOCK_REMOTE_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def _clock_remote_cors_path(path: str) -> bool:
    if path == "/api/status":
        return True
    if path.startswith("/api/clock/"):
        return True
    if path == "/api/master-clock" or path.startswith("/api/master-clock/"):
        return True
    if path.startswith("/api/gamepi/"):
        return True
    return False


@web.middleware
async def clock_remote_cors_middleware(
    request: web.Request,
    handler: Any,
) -> web.StreamResponse:
    if not _clock_remote_cors_path(request.path):
        return await handler(request)
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=_CLOCK_REMOTE_CORS_HEADERS)
    response = await handler(request)
    for header, value in _CLOCK_REMOTE_CORS_HEADERS.items():
        response.headers[header] = value
    return response


class WebInterface:
    """HTTP API, static UI and WebSocket event monitor."""

    def __init__(
        self,
        config: AppConfig,
        bus: EventBus,
        clock: ClockBpmTracker,
        master_clock: MasterClock,
        gpio_adapter: GpioAdapter | None = None,
        hid_adapters: dict[str, HidAdapter] | None = None,
        midi_adapters: dict[str, MidiAdapter] | None = None,
        rtp_midi_adapters: dict[str, RtpMidiAdapter] | None = None,
        osc_adapters: dict[str, OscAdapter] | None = None,
        wing_native_adapters: dict[str, WingNativeAdapter] | None = None,
        rtp_midi_manager: RtpMidiManager | None = None,
        runtime_adapters: list[Adapter] | None = None,
        device_registry: DeviceRegistry | None = None,
        config_path: str | Path | None = None,
        alsa_config_path: str | Path | None = None,
        datapoint_store: DataPointStore | None = None,
        modifier_graph: ModifierGraph | None = None,
    ) -> None:
        self.config = config
        self.bus = bus
        self.clock = clock
        self.master_clock = master_clock
        self.gpio_adapter = gpio_adapter
        self.hid_adapters = hid_adapters or {}
        self.midi_adapters = midi_adapters or {}
        self.rtp_midi_adapters = rtp_midi_adapters or {}
        self.osc_adapters = osc_adapters or {}
        self.wing_native_adapters = wing_native_adapters or {}
        self.rtp_midi_manager = rtp_midi_manager
        self.device_registry = device_registry or DeviceRegistry.from_config(config)
        self._runtime_adapters = runtime_adapters
        self.datapoint_store = datapoint_store
        self.modifier_graph = modifier_graph
        self._osc_io_modules: dict[str, OscIOModule] | None = None
        self.osc_desk_tracker = None
        self.learn = LearnController()
        self.config_path = Path(config_path) if config_path is not None else None
        self.alsa_config_path = (
            Path(alsa_config_path) if alsa_config_path is not None else None
        )
        self._websockets: set[web.WebSocketResponse] = set()
        self._hid_learn_instance: str | None = None
        self._adapter_runtime_status: dict[str, dict[str, str]] = {}
        self._monitor_coalescer = MonitorCoalescer()
        self._rotary_display_module: RotaryDisplayModule | None = None
        self._bandhelper_module: BandHelperModule | None = None
        self._gamepi_module: GamePiBrightnessModule | None = None
        self.bus.subscribe("*", self._broadcast_event)

    def bind_rotary_display_module(self, module: RotaryDisplayModule) -> None:
        self._rotary_display_module = module

    def bind_bandhelper_module(self, module: BandHelperModule) -> None:
        self._bandhelper_module = module

    def bind_gamepi_module(self, module: GamePiBrightnessModule) -> None:
        self._gamepi_module = module

    def bind_osc_io_modules(self, io_modules: dict[str, OscIOModule]) -> None:
        self._osc_io_modules = io_modules

    def create_app(self) -> web.Application:
        app = web.Application(middlewares=[clock_remote_cors_middleware])
        app["web_interface"] = self
        app.router.add_get("/", self.index)
        app.router.add_get("/static/{filename}", self.static_asset)
        app.router.add_get("/api/status", self.status)
        app.router.add_get("/api/system", self.system_config)
        app.router.add_post("/api/system/hostname", self.set_system_hostname)
        app.router.add_post("/api/system/restart", self.restart_service_endpoint)
        app.router.add_get("/api/config/export", self.export_config)
        app.router.add_post("/api/config/import", self.import_config)
        app.router.add_get("/api/gpio", self.gpio_config)
        app.router.add_post("/api/gpio", self.set_gpio_config)
        app.router.add_get("/api/hid-adapters", self.hid_adapters_config)
        app.router.add_post("/api/hid-adapters", self.set_hid_adapters_config)
        app.router.add_post("/api/hid-adapters/learn", self.set_hid_learn_mode)
        app.router.add_get("/api/midi-adapters", self.midi_adapters_config)
        app.router.add_post("/api/midi-adapters", self.set_midi_adapters_config)
        app.router.add_post("/api/midi-adapters/test-send", self.test_send_midi_adapter)
        app.router.add_get("/api/osc-adapters", self.osc_adapters_config)
        app.router.add_get("/api/osc-adapters/discover", self.discover_osc_desks)
        app.router.add_post("/api/osc-adapters", self.set_osc_adapters_config)
        app.router.add_post("/api/osc-adapters/test-send", self.test_send_osc_adapter)
        app.router.add_get("/api/wing-native-adapters", self.wing_native_adapters_config)
        app.router.add_post("/api/wing-native-adapters", self.set_wing_native_adapters_config)
        app.router.add_post(
            "/api/wing-native-adapters/test-send",
            self.test_send_wing_native_adapter,
        )
        app.router.add_get("/api/master-clock", self.master_clock_config)
        app.router.add_post("/api/master-clock", self.set_master_clock_config)
        app.router.add_post("/api/master-clock/tap", self.tap_master_clock)
        app.router.add_post("/api/master-clock/transport", self.master_clock_transport)
        app.router.add_post("/api/clock/trigger", self.clock_trigger)
        app.router.add_get("/api/gamepi/brightness", self.gamepi_brightness_status)
        app.router.add_post("/api/gamepi/brightness", self.gamepi_brightness_adjust)
        app.router.add_post("/api/gamepi/brightness/refresh", self.gamepi_brightness_refresh)
        app.router.add_post("/api/gamepi/reboot", self.gamepi_reboot)
        app.router.add_get("/api/rotary-display", self.rotary_display_config)
        app.router.add_post("/api/rotary-display", self.set_rotary_display_config)
        app.router.add_post("/api/rotary-display/push", self.push_rotary_display_config)
        app.router.add_get("/api/bandhelper", self.bandhelper_config)
        app.router.add_post("/api/bandhelper", self.set_bandhelper_config)
        app.router.add_get("/api/gamepi", self.gamepi_config)
        app.router.add_post("/api/gamepi", self.set_gamepi_config)
        app.router.add_get("/api/midi-libraries", self.midi_libraries)
        app.router.add_get("/api/midi-libraries/{library_id}", self.midi_library)
        app.router.add_get("/api/osc-libraries", self.osc_libraries)
        app.router.add_get("/api/osc-libraries/{library_id}", self.osc_library)
        app.router.add_post("/api/learn", self.set_learn_mode)
        app.router.add_post("/api/learn/clear", self.clear_learn_source)
        app.router.add_post("/api/learn/source", self.select_learn_source)
        app.router.add_post("/api/learn/complete", self.complete_learn_mapping)
        app.router.add_get("/api/datapoints", self.datapoints_config)
        app.router.add_get("/api/devices", self.devices_config)
        app.router.add_post("/api/devices", self.set_devices_config)
        app.router.add_post("/api/devices/test-send", self.test_send_device)
        app.router.add_get("/api/devices/export", self.export_devices_config)
        app.router.add_post("/api/devices/import", self.import_devices_config)
        app.router.add_get("/api/connections", self.connections_config)
        app.router.add_post("/api/connections", self.set_connections_config)
        app.router.add_post("/api/connections/reverse", self.reverse_connection_config)
        app.router.add_post("/api/connections/export", self.export_connections_bundle)
        app.router.add_post("/api/connections/import/preview", self.preview_connections_import)
        app.router.add_post("/api/connections/import", self.import_connections_bundle)
        app.router.add_get("/ws/monitor", self.monitor_ws)
        return app

    async def index(self, request: web.Request) -> web.Response:
        return await self.static_asset(request, filename="index.html")

    async def static_asset(
        self, request: web.Request, filename: str | None = None
    ) -> web.Response:
        asset_name = filename or request.match_info["filename"]
        if "/" in asset_name or asset_name.startswith("."):
            raise web.HTTPNotFound()

        asset = resources.files("midijuggler.web").joinpath("static", asset_name)
        if not asset.is_file():
            raise web.HTTPNotFound()

        content_type = mimetypes.guess_type(asset_name)[0] or "application/octet-stream"
        return web.Response(body=asset.read_bytes(), content_type=content_type)

    async def broadcast_datapoint_update(self, payload: dict[str, Any]) -> None:
        if not self._websockets:
            return
        key = monitor_datapoint_key(payload)
        if key is None:
            await self._broadcast_payload({"type": "datapoint", "payload": payload})
            return
        await self._monitor_coalescer.offer(
            key,
            payload,
            lambda item: self._broadcast_payload({"type": "datapoint", "payload": item}),
            immediate=self.learn.state.enabled,
        )

    def datapoints_payload(self) -> dict[str, Any]:
        if self.datapoint_store is None:
            return {"datapoints": [], "values": {}}
        return {
            "datapoints": self.datapoint_store.registry_snapshot(),
            "values": self.datapoint_store.snapshot(),
        }

    async def datapoints_config(self, request: web.Request) -> web.Response:
        return web.json_response(self.datapoints_payload())

    def devices_payload(self) -> dict[str, Any]:
        object.__setattr__(
            self.config,
            "devices",
            normalize_device_libraries(
                supplement_devices(
                    dict(self.config.devices),
                    self.config.adapters,
                    suppressed_adapters=self.config.runtime.suppressed_inferred_device_adapters,
                ),
                self.config.adapters,
            ),
        )
        self.device_registry.reload_from_config(self.config)
        return {
            "devices": [device.as_dict() for device in self.config.devices.values()],
            "adapter_options": adapter_device_options(
                self.config.adapters,
                self.config.devices,
            ),
        }

    async def devices_config(self, request: web.Request) -> web.Response:
        return web.json_response(self.devices_payload())

    async def set_devices_config(self, request: web.Request) -> web.Response:
        payload = await request.json()
        raw_devices = payload.get("devices", [])
        if not isinstance(raw_devices, list):
            return web.Response(text="devices must be a list", status=400)
        try:
            imported = import_devices(raw_devices)
        except ValueError as exc:
            return web.Response(text=str(exc), status=400)

        from midijuggler.config import normalize_device_adapter_refs, normalize_device_libraries

        devices = normalize_device_adapter_refs(
            {device.uid: device for device in imported},
            self.config.adapters,
        )
        devices = normalize_device_libraries(devices, self.config.adapters)
        bound_adapters: dict[str, str] = {}
        for device in devices.values():
            if device.adapter not in self.config.adapters:
                return web.Response(
                    text=f"device {device.display_name()!r} references unknown adapter {device.adapter!r}",
                    status=400,
                )
            existing = bound_adapters.get(device.adapter)
            if existing is not None and existing != device.uid:
                return web.Response(
                    text=(
                        f"adapter {device.adapter!r} is already bound to device "
                        f"{existing!r}"
                    ),
                    status=400,
                )
            bound_adapters[device.adapter] = device.uid

        previous_device_uids = set(self.config.devices.keys())
        previous_devices = dict(self.config.devices)
        runtime = replace(
            self.config.runtime,
            suppressed_inferred_device_adapters=update_suppressed_inferred_device_adapters(
                previous_devices,
                devices,
                self.config.adapters,
                self.config.runtime.suppressed_inferred_device_adapters,
            ),
        )
        object.__setattr__(self.config, "runtime", runtime)
        object.__setattr__(self.config, "devices", devices)
        self.device_registry.reload_from_config(self.config)

        persisted = False
        persist_error = ""
        if self.config_path is not None:
            try:
                save_devices(self.config_path, devices)
                save_runtime_config(self.config_path, runtime)
                persisted = True
            except OSError as exc:
                persist_error = str(exc)
        else:
            persist_error = "no config path available"

        await self._refresh_device_datapoints_after_config_change(
            set(previous_device_uids),
        )

        response = self.devices_payload()
        response["persisted"] = persisted
        response["persist_error"] = persist_error
        return web.json_response(response)

    async def export_devices_config(self, request: web.Request) -> web.Response:
        return web.json_response(
            {"devices": export_devices(list(self.config.devices.values()))}
        )

    async def import_devices_config(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            imported = import_devices(payload.get("devices", payload))
        except ValueError as exc:
            return web.Response(text=str(exc), status=400)

        merged = dict(self.config.devices)
        for device in imported:
            merged[device.uid] = device
        object.__setattr__(self.config, "devices", merged)

        persisted = False
        persist_error = ""
        if self.config_path is not None:
            try:
                save_devices(self.config_path, merged)
                persisted = True
            except OSError as exc:
                persist_error = str(exc)
        else:
            persist_error = "no config path available"

        return web.json_response(
            {
                "devices": export_devices(list(merged.values())),
                "persisted": persisted,
                "persist_error": persist_error,
            }
        )

    def connections_payload(self) -> dict[str, Any]:
        stored = self._stored_connections()
        return {
            "connections": [connection.as_dict() for connection in self._effective_connections()],
            "stored_connections": [connection.as_dict() for connection in stored],
            "implicit_connections": [
                connection.as_dict() for connection in self._implicit_connections()
            ],
            "datapoint_routing": self.config.runtime.datapoint_routing,
            "feedback_suppress_ms": self.config.runtime.feedback_suppress_ms,
        }

    def _implicit_connections(self) -> list[ConnectionSpec]:
        return implicit_connections(
            self.config,
            datapoint_routing=self.config.runtime.datapoint_routing,
        )

    def _effective_connections(self) -> list[ConnectionSpec]:
        return effective_connections(
            self.config,
            datapoint_routing=self.config.runtime.datapoint_routing,
        )

    async def connections_config(self, request: web.Request) -> web.Response:
        return web.json_response(self.connections_payload())

    async def set_connections_config(self, request: web.Request) -> web.Response:
        payload = await request.json()
        raw_connections = payload.get("connections", [])
        if not isinstance(raw_connections, list):
            return web.Response(text="connections must be a list", status=400)

        connections: list[ConnectionSpec] = []
        for index, item in enumerate(raw_connections, start=1):
            if not isinstance(item, dict):
                return web.Response(text=f"connections[{index}] must be an object", status=400)
            try:
                scale_curve = str(item.get("scale_curve", "linear")).strip() or "linear"
                if scale_curve not in SCALE_CURVES:
                    return web.Response(
                        text=f"connections[{index}] unsupported scale_curve: {scale_curve!r}",
                        status=400,
                    )
                connections.append(
                    ConnectionSpec(
                        id=str(item["id"]),
                        source=str(item["source"]),
                        target=str(item["target"]),
                        modifier=ModifierKind(str(item.get("modifier", ModifierKind.RANGE_MAP.value))),
                        input_min=float(item.get("input_min", 0.0)),
                        input_max=float(item.get("input_max", 1.0)),
                        output_min=float(item.get("output_min", 0.0)),
                        output_max=float(item.get("output_max", 127.0)),
                        invert=bool(item.get("invert", False)),
                        scale_curve=scale_curve,
                        factor=float(item.get("factor", 1.0)),
                        enabled=bool(item.get("enabled", True)),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                return web.Response(text=str(exc), status=400)

        object.__setattr__(self.config, "connections", connections)
        try:
            runtime_changed = self._apply_runtime_settings_from_payload(payload)
        except ValueError as exc:
            return web.Response(text=str(exc), status=400)
        self._apply_stored_connections(connections)
        persisted_connections, persist_error = self._persist_stored_connections(connections)
        persisted_runtime = True
        runtime_persist_error = ""
        if runtime_changed:
            persisted_runtime, runtime_persist_error = self._persist_runtime_config()
        response = self.connections_payload()
        response["persisted"] = persisted_connections and persisted_runtime
        response["persist_error"] = persist_error or runtime_persist_error
        return web.json_response(response)

    async def export_connections_bundle(self, request: web.Request) -> web.Response:
        payload = await request.json()
        device_a_uid = str(payload.get("device_a", "")).strip()
        device_b_uid = str(payload.get("device_b", "")).strip()
        if not device_a_uid or not device_b_uid:
            return web.Response(text="device_a and device_b are required", status=400)
        try:
            bundle = export_connection_bundle(
                self._stored_connections(),
                device_a_uid,
                device_b_uid,
                self.config.devices,
                self.config.adapters,
                datapoint_store=self.datapoint_store,
            )
        except ValueError as exc:
            return web.Response(text=str(exc), status=400)
        return web.json_response(bundle)

    async def preview_connections_import(self, request: web.Request) -> web.Response:
        payload = await request.json()
        bundle = payload.get("bundle", payload)
        try:
            preview = preview_connection_bundle_import(bundle, self.config)
        except ValueError as exc:
            return web.Response(text=str(exc), status=400)
        return web.json_response(preview)

    async def import_connections_bundle(self, request: web.Request) -> web.Response:
        payload = await request.json()
        bundle = payload.get("bundle")
        if bundle is None:
            bundle = payload
        device_mapping = payload.get("device_mapping", {})
        try:
            imported, updated_devices, merged_connections = apply_connection_bundle_import(
                bundle,
                device_mapping,
                self.config,
                self._stored_connections(),
                datapoint_store=self.datapoint_store,
            )
        except ValueError as exc:
            return web.Response(text=str(exc), status=400)

        if not imported:
            return web.Response(text="bundle contains no importable connections", status=400)

        previous_device_uids = set(self.config.devices)
        devices = dict(self.config.devices)
        devices.update(updated_devices)
        object.__setattr__(self.config, "devices", devices)
        self.device_registry.reload_from_config(self.config)
        await self._refresh_device_datapoints_after_config_change(previous_device_uids)

        self._apply_stored_connections(merged_connections)
        persisted_connections, persist_error = self._persist_stored_connections(merged_connections)
        persisted_devices = True
        devices_persist_error = ""
        if updated_devices and self.config_path is not None:
            try:
                save_devices(self.config_path, devices)
            except OSError as exc:
                persisted_devices = False
                devices_persist_error = str(exc)
        elif updated_devices:
            persisted_devices = False
            devices_persist_error = "no config path available"

        response = self.connections_payload()
        response.update(
            {
                "imported_count": len(imported),
                "imported_connections": [connection.as_dict() for connection in imported],
                "updated_devices": [device.as_dict() for device in updated_devices.values()],
                "persisted": persisted_connections and persisted_devices,
                "persist_error": persist_error or devices_persist_error,
            }
        )
        return web.json_response(response)

    async def reverse_connection_config(self, request: web.Request) -> web.Response:
        payload = await request.json()
        connection_id = str(payload.get("id", "")).strip()
        if not connection_id:
            return web.Response(text="id is required", status=400)

        stored = self._stored_connections()
        original = next(
            (connection for connection in stored if connection.id == connection_id),
            None,
        )
        if original is None:
            return web.Response(text=f"unknown connection id: {connection_id!r}", status=404)

        from midijuggler.datapoint.disconnected import is_disconnected_endpoint

        if is_disconnected_endpoint(original.source) or is_disconnected_endpoint(original.target):
            return web.Response(
                text="cannot reverse a connection with a disconnected endpoint",
                status=400,
            )

        feedback = reverse_connection(original, self.datapoint_store)
        updated_connections = upsert_connection(stored, feedback)
        self._apply_stored_connections(updated_connections)

        persisted = False
        persist_error = ""
        if self.config_path is not None:
            try:
                save_connections(self.config_path, updated_connections)
                persisted = True
            except OSError as exc:
                persist_error = str(exc)
                LOGGER.warning(
                    "Reverse connection applied at runtime but could not be persisted to %s: %s",
                    self.config_path,
                    exc,
                )
        else:
            persist_error = "no config path available"

        response = self.connections_payload()
        response.update(
            {
                "created_connection": feedback.as_dict(),
                "persisted": persisted,
                "persist_error": persist_error,
            }
        )
        return web.json_response(response)

    async def write_datapoint(self, point_id: str, value: float) -> None:
        if self.datapoint_store is None:
            raise ValueError("data point store is unavailable")
        await self.datapoint_store.write(float_value(point_id, value))

    async def broadcast_status(self) -> None:
        await self._broadcast_payload({"type": "status", "payload": self._status_payload()})

    async def status(self, request: web.Request) -> web.Response:
        return web.json_response(self._status_payload())

    def system_config_payload(self) -> dict[str, Any]:
        return {
            "hostname": get_hostname(),
        }

    async def system_config(self, request: web.Request) -> web.Response:
        can_set, can_restart, message = await asyncio.gather(
            can_set_hostname(),
            can_restart_service(),
            capability_message(),
        )
        payload = self.system_config_payload()
        payload["can_set_hostname"] = can_set
        payload["can_restart_service"] = can_restart
        payload["capability_message"] = message
        payload.update(system_diagnostics())
        return web.json_response(payload)

    async def set_system_hostname(self, request: web.Request) -> web.Response:
        payload = await request.json()
        hostname = str(payload.get("hostname", ""))
        LOGGER.info("hostname change requested: %r", hostname)
        try:
            validate_hostname(hostname)
        except ValueError as exc:
            return web.Response(text=str(exc), status=400)

        if not await can_set_hostname():
            message = await capability_message()
            detail = message or "hostname changes are not permitted on this system"
            LOGGER.warning("hostname change blocked: %s", detail)
            return web.Response(text=detail, status=503)

        try:
            new_hostname, changed = await apply_hostname(hostname)
        except OSError as exc:
            LOGGER.warning("failed to set hostname: %s", exc)
            return web.Response(text=str(exc), status=503)

        mdns_refreshed = False
        if changed and self.rtp_midi_manager is not None:
            try:
                await self.rtp_midi_manager.refresh_announcements()
                mdns_refreshed = True
            except Exception:
                LOGGER.exception("failed to refresh RTP-MIDI announcements")

        await self._broadcast_payload(
            {"type": "status", "payload": self._status_payload()}
        )
        return web.json_response(
            {
                "hostname": new_hostname,
                "changed": changed,
                "mdns_refreshed": mdns_refreshed,
            }
        )

    async def restart_service_endpoint(self, request: web.Request) -> web.Response:
        LOGGER.info("service restart requested from web UI")
        if not await can_restart_service():
            message = await capability_message()
            detail = message or "service restart is not permitted on this system"
            LOGGER.warning("service restart blocked: %s", detail)
            return web.Response(text=detail, status=503)

        async def _delayed_restart() -> None:
            await asyncio.sleep(0.3)
            try:
                await restart_service()
            except OSError as exc:
                LOGGER.error("failed to restart MIDIJuggler service: %s", exc)

        asyncio.create_task(_delayed_restart())
        return web.json_response({"restarting": True})

    async def export_config(self, request: web.Request) -> web.Response:
        try:
            body = self.export_config_text()
        except FileNotFoundError as exc:
            raise web.HTTPNotFound(text=str(exc)) from exc
        except OSError as exc:
            raise web.HTTPInternalServerError(text=str(exc)) from exc
        return web.Response(
            text=body,
            content_type="application/toml",
            headers={
                "Content-Disposition": 'attachment; filename="midijuggler-config.toml"'
            },
        )

    async def import_config(self, request: web.Request) -> web.Response:
        if self.config_path is None:
            raise web.HTTPNotFound(text="no config path available")
        payload = await request.json()
        content = str(payload.get("content", ""))
        try:
            result = self.import_config_text(content)
        except (tomllib.TOMLDecodeError, ValueError) as exc:
            raise web.HTTPBadRequest(text=f"invalid config: {exc}") from exc
        except FileNotFoundError as exc:
            raise web.HTTPNotFound(text=str(exc)) from exc
        except OSError as exc:
            raise web.HTTPInternalServerError(text=str(exc)) from exc
        return web.json_response(result)

    def export_config_text(self) -> str:
        if self.config_path is None:
            raise FileNotFoundError("no config path available")
        return self.config_path.read_text(encoding="utf-8")

    def import_config_text(self, content: str) -> dict[str, bool]:
        if self.config_path is None:
            raise FileNotFoundError("no config path available")
        if not content.strip():
            raise ValueError("config content is empty")
        parse_config(tomllib.loads(content), strict=True)
        temp_path = self.config_path.with_suffix(self.config_path.suffix + ".tmp")
        temp_path.write_text(content.rstrip() + "\n", encoding="utf-8")
        temp_path.replace(self.config_path)
        return {"imported": True, "restart_required": True}

    async def gpio_config(self, request: web.Request) -> web.Response:
        return web.json_response(self.gpio_config_payload())

    async def set_gpio_config(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            response = await self.apply_gpio_config(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def hid_adapters_config(self, request: web.Request) -> web.Response:
        return web.json_response(self.hid_adapters_config_payload())

    async def set_hid_adapters_config(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            response = await self.apply_hid_adapters_config(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def set_hid_learn_mode(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            response = await self.apply_hid_learn_mode(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def midi_adapters_config(self, request: web.Request) -> web.Response:
        return web.json_response(self.midi_adapters_config_payload())

    async def set_midi_adapters_config(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            response = await self.apply_midi_adapters_config(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def test_send_midi_adapter(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            response = await self.send_midi_adapter_test_message(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        except OSError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def test_send_osc_adapter(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            response = await self.send_osc_adapter_test_message(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        except OSError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def test_send_device(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            response = await self.send_device_test_message(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        except OSError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def test_send_wing_native_adapter(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            response = await self.send_wing_native_adapter_test_message(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        except OSError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def osc_adapters_config(self, request: web.Request) -> web.Response:
        return web.json_response(self.osc_adapters_config_payload())

    async def set_osc_adapters_config(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            response = await self.apply_osc_adapters_config(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def wing_native_adapters_config(self, request: web.Request) -> web.Response:
        return web.json_response(self.wing_native_adapters_config_payload())

    async def set_wing_native_adapters_config(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            response = await self.apply_wing_native_adapters_config(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def master_clock_config(self, request: web.Request) -> web.Response:
        return web.json_response(self.master_clock_config_payload())

    async def set_master_clock_config(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            response = await self.apply_master_clock_config(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def tap_master_clock(self, request: web.Request) -> web.Response:
        try:
            payload = await self.apply_tap_tempo()
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(payload)

    async def clock_trigger(self, request: web.Request) -> web.Response:
        payload = await request.json()
        point = str(payload.get("point", ""))
        try:
            response = await self.apply_clock_trigger(point)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def gamepi_brightness_status(self, request: web.Request) -> web.Response:
        from midijuggler.web.gamepi_brightness import brightness_status_payload

        return web.json_response(brightness_status_payload())

    async def gamepi_brightness_adjust(self, request: web.Request) -> web.Response:
        from midijuggler.modules.interface.gamepi_brightness import publish_brightness_to_store
        from midijuggler.web.gamepi_brightness import adjust_brightness_payload

        payload = await request.json()
        try:
            delta = int(payload.get("delta", 0))
        except (TypeError, ValueError) as exc:
            raise web.HTTPBadRequest(text="delta must be an integer") from exc
        result = adjust_brightness_payload(delta)
        await publish_brightness_to_store(self.datapoint_store, result)
        return web.json_response(result)

    async def gamepi_brightness_refresh(self, request: web.Request) -> web.Response:
        from midijuggler.modules.interface.gamepi_brightness import publish_brightness_to_store
        from midijuggler.web.gamepi_brightness import brightness_status_payload

        if self.datapoint_store is None:
            raise web.HTTPServiceUnavailable(text="datapoint store unavailable")
        await publish_brightness_to_store(self.datapoint_store)
        return web.json_response(brightness_status_payload(fresh=True))

    async def gamepi_reboot(self, request: web.Request) -> web.Response:
        from midijuggler.web.gamepi_system import request_reboot

        try:
            return web.json_response(request_reboot(request))
        except PermissionError as exc:
            raise web.HTTPForbidden(text=str(exc)) from exc

    async def rotary_display_config(self, request: web.Request) -> web.Response:
        return web.json_response(self.rotary_display_config_payload())

    async def set_rotary_display_config(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            response = await self.apply_rotary_display_config(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def push_rotary_display_config(self, request: web.Request) -> web.Response:
        try:
            response = await self.apply_rotary_display_push()
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def bandhelper_config(self, request: web.Request) -> web.Response:
        return web.json_response(self.bandhelper_config_payload())

    async def set_bandhelper_config(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            response = await self.apply_bandhelper_config(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def gamepi_config(self, request: web.Request) -> web.Response:
        return web.json_response(self.gamepi_config_payload())

    async def set_gamepi_config(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            response = await self.apply_gamepi_config(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def master_clock_transport(self, request: web.Request) -> web.Response:
        payload = await request.json()
        action = str(payload.get("action", "toggle"))
        try:
            response = await self.apply_master_clock_transport(action)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def midi_libraries(self, request: web.Request) -> web.Response:
        libraries = list_midi_libraries()
        return web.json_response(
            [
                {
                    "id": library.id,
                    "name": library.name,
                    "vendor": library.vendor,
                    "model": library.model,
                    "notes": library.notes,
                    "parameter_count": len(library.parameters),
                }
                for library in libraries
            ]
        )

    async def midi_library(self, request: web.Request) -> web.Response:
        try:
            library = get_midi_library(request.match_info["library_id"])
        except KeyError:
            raise web.HTTPNotFound() from None
        return web.json_response(library.as_dict())

    async def osc_libraries(self, request: web.Request) -> web.Response:
        libraries = list_osc_libraries()
        return web.json_response(
            [
                {
                    "id": library.id,
                    "name": library.name,
                    "vendor": library.vendor,
                    "model": library.model,
                    "notes": library.notes,
                    "bundled": library.bundled,
                    "bundled_connection_count": len(library.bundled_connections),
                    "parameter_count": len(library.parameters),
                }
                for library in libraries
            ]
        )

    async def osc_library(self, request: web.Request) -> web.Response:
        try:
            library = get_osc_library(request.match_info["library_id"])
        except KeyError:
            raise web.HTTPNotFound() from None
        return web.json_response(library.as_dict())

    async def set_learn_mode(self, request: web.Request) -> web.Response:
        payload: dict[str, Any] = await request.json()
        self.learn.set_enabled(bool(payload.get("enabled", False)))
        return web.json_response(self._status_payload())

    async def clear_learn_source(self, request: web.Request) -> web.Response:
        await request.json()
        self.learn.clear_source()
        return web.json_response(self._status_payload())

    async def select_learn_source(self, request: web.Request) -> web.Response:
        payload: dict[str, Any] = await request.json()
        try:
            response = await self.apply_learn_source(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def complete_learn_mapping(self, request: web.Request) -> web.Response:
        payload: dict[str, Any] = await request.json()
        try:
            response = await self.apply_learn_mapping(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.json_response(response)

    async def monitor_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        self._websockets.add(ws)
        await ws.send_json({"type": "status", "payload": self._status_payload()})
        for event in self.bus.history_dicts():
            await ws.send_json({"type": "event", "payload": event})
        if self.datapoint_store is not None:
            for update in self.datapoint_store.history():
                await ws.send_json(
                    {"type": "datapoint", "payload": update.as_dict()}
                )

        async for message in ws:
            if message.type == WSMsgType.TEXT:
                await self._handle_ws_message(ws, message.data)
            elif message.type == WSMsgType.ERROR:
                break

        self._websockets.discard(ws)
        return ws

    async def _handle_ws_message(self, ws: web.WebSocketResponse, data: str) -> None:
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            await ws.send_json({"type": "error", "message": "invalid JSON"})
            return

        if payload.get("type") == "learn":
            self.learn.set_enabled(bool(payload.get("enabled", False)))
            await self._broadcast_payload({"type": "status", "payload": self._status_payload()})
            return

        if payload.get("type") == "learn_clear":
            self.learn.clear_source()
            await self._broadcast_payload({"type": "status", "payload": self._status_payload()})
            return

        if payload.get("type") == "learn_select":
            try:
                result = await self.apply_learn_source(payload)
            except ValueError as exc:
                await ws.send_json({"type": "error", "message": str(exc)})
                return
            await self._broadcast_payload({"type": "status", "payload": result})
            return

        if payload.get("type") == "learn_complete":
            try:
                result = await self.apply_learn_mapping(payload)
            except ValueError as exc:
                await ws.send_json({"type": "error", "message": str(exc)})
                return
            status = self._status_payload()
            status.update(
                {
                    key: result[key]
                    for key in (
                        "created_mapping",
                        "created_connection",
                        "persisted",
                        "persist_error",
                    )
                    if key in result
                }
            )
            await self._broadcast_payload({"type": "status", "payload": status})

    async def apply_learn_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.learn.state.enabled:
            raise ValueError("learn mode is disabled")

        datapoint = str(payload.get("datapoint", "")).strip()
        if datapoint:
            self.learn.select_source_datapoint(datapoint)
            return self._status_payload()

        event = payload.get("event")
        if not isinstance(event, dict):
            raise ValueError("datapoint or event payload is required")

        source = resolve_monitor_source(self.config, event)
        self.learn.select_source(source, device_registry=self.device_registry)
        return self._status_payload()

    async def apply_learn_mapping(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_datapoint = str(payload.get("source_datapoint", "")).strip()
        if not source_datapoint and self.learn.state.source_datapoint:
            source_datapoint = self.learn.state.source_datapoint
        if not source_datapoint and self.learn.state.source is not None:
            source_datapoint = adapter_control_to_datapoint(
                self.learn.state.source.adapter,
                self.learn.state.source.control,
                self.device_registry,
            )
        if not source_datapoint:
            raise ValueError("learn mode has no captured source")

        target_datapoint = resolve_target_datapoint(
            self.config,
            target_datapoint=str(payload.get("target_datapoint", "")).strip(),
            target_adapter=str(payload.get("target_adapter", "")).strip(),
            target_parameter_id=str(payload.get("parameter_id", "")).strip(),
            device_registry=self.device_registry,
        )

        modifier_raw = str(payload.get("modifier", ModifierKind.RANGE_MAP.value)).strip()
        try:
            modifier = ModifierKind(modifier_raw)
        except ValueError as exc:
            raise ValueError(f"unsupported modifier: {modifier_raw!r}") from exc

        input_min = float(payload.get("input_min", lookup_datapoint_ranges(
            self.datapoint_store,
            source_datapoint,
            fallback=(0.0, 127.0),
        )[0]))
        input_max = float(payload.get("input_max", lookup_datapoint_ranges(
            self.datapoint_store,
            source_datapoint,
            fallback=(0.0, 127.0),
        )[1]))
        output_min = float(payload.get("output_min", lookup_datapoint_ranges(
            self.datapoint_store,
            target_datapoint,
            fallback=(0.0, 127.0),
        )[0]))
        output_max = float(payload.get("output_max", lookup_datapoint_ranges(
            self.datapoint_store,
            target_datapoint,
            fallback=(0.0, 127.0),
        )[1]))
        invert = bool(payload.get("invert", False))
        scale_curve = str(payload.get("scale_curve", "linear")).strip() or "linear"
        if scale_curve not in SCALE_CURVES:
            raise ValueError(f"unsupported scale_curve: {scale_curve!r}")
        factor = float(payload.get("factor", 1.0))
        if modifier == ModifierKind.FACTOR and factor == 0.0:
            raise ValueError("factor must not be zero")

        connection = self.learn.build_connection(
            source_datapoint=source_datapoint,
            target_datapoint=target_datapoint,
            modifier=modifier,
            input_min=input_min,
            input_max=input_max,
            output_min=output_min,
            output_max=output_max,
            invert=invert,
            scale_curve=scale_curve,
            factor=factor,
            connection_id=str(payload.get("id", "")).strip() or None,
        )

        updated_connections = upsert_connection(self.config.connections, connection)
        self._apply_stored_connections(updated_connections)

        persisted = False
        persist_error = ""
        if self.config_path is not None:
            try:
                save_connections(self.config_path, updated_connections)
                persisted = True
            except OSError as exc:
                persist_error = str(exc)
                LOGGER.warning(
                    "Learn connection applied at runtime but could not be persisted to %s: %s",
                    self.config_path,
                    exc,
                )
        else:
            persist_error = "no config path available"

        self.learn.clear_source()
        response = self._status_payload()
        response.update(
            {
                "created_connection": connection.as_dict(),
                "persisted": persisted,
                "persist_error": persist_error,
            }
        )
        return response

    def _stored_connections(self) -> list[ConnectionSpec]:
        return stored_connections(self.config.connections)

    def _apply_stored_connections(self, connections: list[ConnectionSpec]) -> None:
        from midijuggler.config import normalize_connections

        normalized = normalize_connections(connections, self.config.devices)
        object.__setattr__(self.config, "connections", list(normalized))
        self._apply_runtime_connections()

    def _persist_stored_connections(
        self,
        connections: list[ConnectionSpec],
    ) -> tuple[bool, str]:
        if self.config_path is None:
            return False, "no config path available"
        try:
            save_connections(self.config_path, connections)
            return True, ""
        except OSError as exc:
            LOGGER.warning(
                "Could not persist connections to %s: %s",
                self.config_path,
                exc,
            )
            return False, str(exc)

    def _apply_runtime_connections(self) -> None:
        if self.modifier_graph is not None:
            self.modifier_graph.configure_feedback_suppress(
                self.config.runtime.feedback_suppress_ms
            )
        if self.modifier_graph is None:
            return
        user_connections = self._stored_connections()
        self.modifier_graph.replace_connections(
            effective_connections(
                self.config,
                datapoint_routing=self.config.runtime.datapoint_routing,
            )
        )

    def _apply_runtime_settings_from_payload(self, payload: dict[str, Any]) -> bool:
        runtime_changed = False
        current = self.config.runtime
        datapoint_routing = current.datapoint_routing
        feedback_suppress_ms = current.feedback_suppress_ms

        if "datapoint_routing" in payload:
            datapoint_routing = bool(payload["datapoint_routing"])
            runtime_changed = True
        if "feedback_suppress_ms" in payload:
            feedback_suppress_ms = parse_feedback_suppress_ms(payload["feedback_suppress_ms"])
            runtime_changed = True

        if not runtime_changed:
            return False

        object.__setattr__(
            self.config,
            "runtime",
            RuntimeConfig(
                datapoint_routing=datapoint_routing,
                feedback_suppress_ms=feedback_suppress_ms,
            ),
        )
        if self.modifier_graph is not None:
            self.modifier_graph.configure_feedback_suppress(feedback_suppress_ms)
        return True

    def _persist_runtime_config(self) -> tuple[bool, str]:
        if self.config_path is None:
            return False, "no config path available"
        try:
            save_runtime_config(self.config_path, self.config.runtime)
            return True, ""
        except OSError as exc:
            LOGGER.warning(
                "Could not persist runtime config to %s: %s",
                self.config_path,
                exc,
            )
            return False, str(exc)

    async def _broadcast_event(self, event: Event) -> None:
        if isinstance(event, AdapterStatusEvent):
            self._adapter_runtime_status[event.adapter] = {
                "status": event.status,
                "detail": event.detail,
                "connection_phase": event.connection_phase,
            }
        payload = {"type": "event", "payload": event.as_dict()}
        if self._websockets:
            key = monitor_event_key(event)
            if key is None:
                await self._broadcast_payload(payload)
            else:
                await self._monitor_coalescer.offer(
                    key,
                    payload,
                    self._broadcast_payload,
                    immediate=self.learn.state.enabled,
                )
        if isinstance(event, MasterClockStateEvent):
            await self.broadcast_status()
            return

    async def _broadcast_payload(self, payload: dict[str, Any]) -> None:
        if not self._websockets:
            return

        stale: list[web.WebSocketResponse] = []
        encoded = json.dumps(payload)
        for ws in self._websockets:
            try:
                await ws.send_str(encoded)
            except (ConnectionResetError, RuntimeError):
                stale.append(ws)

        for ws in stale:
            self._websockets.discard(ws)

    def _status_payload(self) -> dict[str, Any]:
        return {
            "hostname": get_hostname(),
            "config_issues": list(self.config.load_issues),
            "bpm": self.clock.bpm,
            "master_clock": {
                "enabled": self.master_clock.config.enabled,
                "bpm": self.master_clock.bpm,
                "running": self.master_clock.running,
                "position_ticks": self.master_clock.position_ticks,
                "click_enabled": self.master_clock.config.click_enabled,
                "click_interval": self.master_clock.click_interval,
                "bpm_step": self.master_clock.config.bpm_step,
                "bpm_huge_step": self.master_clock.config.bpm_huge_step,
                "beat_flash_ms": self.master_clock.config.beat_flash_ms,
                "parameters": self.master_clock.parameters.as_controls(),
            },
            "learn_mode": self.learn.state.enabled,
            "learn": self.learn.state.as_dict(),
            "osc_instances": self._osc_instances_payload(),
            "wing_native_instances": self._wing_native_instances_payload(),
            "osc_discovered_desks": (
                self.osc_desk_tracker.discovered_desks
                if self.osc_desk_tracker is not None
                else []
            ),
            "devices": [device.as_dict() for device in self.config.devices.values()],
            "stored_connections": [
                connection.as_dict() for connection in self._stored_connections()
            ],
            "implicit_connections": [
                connection.as_dict() for connection in self._implicit_connections()
            ],
            "connections": [
                connection.as_dict() for connection in self._effective_connections()
            ],
            "datapoint_routing": self.config.runtime.datapoint_routing,
            "feedback_suppress_ms": self.config.runtime.feedback_suppress_ms,
            "adapters": {
                name: self._adapter_status_entry(name, adapter)
                for name, adapter in self.config.adapters.items()
            },
        }

    def _adapter_runtime_connection(self, name: str) -> dict[str, str] | None:
        cached = self._adapter_runtime_status.get(name)
        if not cached:
            return None
        return dict(cached)

    def _adapter_status_entry(self, name: str, adapter: AdapterConfig) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "type": adapter.kind or name,
            "enabled": adapter.enabled,
            "options": adapter.options,
        }
        runtime_connection = self._adapter_runtime_connection(name)
        if runtime_connection is not None:
            entry["runtime_connection"] = runtime_connection
        if (adapter.kind or name) == "wing_native":
            runtime_adapter = self.wing_native_adapters.get(name)
            if runtime_adapter is not None:
                entry["wing_connectivity"] = runtime_adapter.connectivity_snapshot()
        return entry

    def _wing_native_instances_payload(self) -> list[dict[str, Any]]:
        instances: list[dict[str, Any]] = []
        for name, adapter in self.config.adapters.items():
            kind = adapter.kind or name
            if kind != "wing_native":
                continue
            if not adapter.enabled and name not in self.wing_native_adapters:
                continue
            options = dict(adapter.options)
            runtime_adapter = self.wing_native_adapters.get(name)
            payload: dict[str, Any] = {
                "name": name,
                "type": "wing_native",
                "enabled": adapter.enabled,
                "remote_host": str(options.get("remote_host", "")).strip(),
                "native_port": int(options.get("native_port", 2222)),
                "wing_library": str(options.get("wing_library", "behringer_wing")).strip(),
                "runtime_active": runtime_adapter is not None and runtime_adapter.running,
            }
            runtime_connection = self._adapter_runtime_connection(name)
            if runtime_connection is not None:
                payload["runtime_connection"] = runtime_connection
            if runtime_adapter is not None:
                payload["connectivity"] = runtime_adapter.connectivity_snapshot()
            elif runtime_connection is not None:
                payload["connectivity"] = {
                    "connection_phase": runtime_connection.get("connection_phase", ""),
                    "connected": runtime_connection.get("connection_phase") == "connected",
                    "last_error": runtime_connection.get("detail", ""),
                }
            instances.append(payload)
        return instances

    def _parse_midi_test_message(self, payload: dict[str, Any]) -> tuple[int, tuple[int, ...]]:
        if "status" not in payload:
            raise ValueError("MIDI test message requires status")

        status = int(payload["status"])
        raw_data = payload.get("data", [])
        if not isinstance(raw_data, list):
            raise ValueError("data must be a list of MIDI bytes")

        if not 0 <= status <= 255:
            raise ValueError("status must be between 0 and 255")

        data: list[int] = []
        for index, raw_byte in enumerate(raw_data):
            byte = int(raw_byte)
            if not 0 <= byte <= 127:
                raise ValueError(f"data[{index}] must be between 0 and 127")
            data.append(byte)

        return status, tuple(data)

    def _parse_osc_test_arguments(self, payload: dict[str, Any]) -> list[Any]:
        if "arguments" in payload:
            raw_arguments = payload.get("arguments")
            if not isinstance(raw_arguments, list):
                raise ValueError("arguments must be a list")
            return raw_arguments

        if "value" not in payload:
            return []

        value = payload["value"]
        if isinstance(value, bool):
            return [value]
        if isinstance(value, int):
            return [value]
        if isinstance(value, float):
            return [value]
        if isinstance(value, str):
            return [value]
        raise ValueError("value must be a number, string, or boolean")

    async def send_midi_adapter_test_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("MIDI test payload must be an object")

        kind = str(payload.get("kind", "midi")).strip().lower()
        if kind not in {"midi", "rtp_midi"}:
            raise ValueError("kind must be midi or rtp_midi")

        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("name is required")

        adapter = (
            self.midi_adapters.get(name)
            if kind == "midi"
            else self.rtp_midi_adapters.get(name)
        )
        if adapter is None:
            raise ValueError(f"unknown {kind} adapter instance: {name}")
        if not adapter.running:
            raise OSError(f"{kind} adapter {name} is not running")

        status, data = self._parse_midi_test_message(payload)

        if isinstance(adapter, MidiAdapter):
            await adapter.send_test_message(status, data)
        else:
            await adapter.send_test_message(status, data)
        return {
            "ok": True,
            "name": name,
            "kind": kind,
            "status": status,
            "data": list(data),
        }

    def _resolve_device_library_test_message(
        self,
        device: DeviceConfig,
        parameter_id: str,
        payload: dict[str, Any],
    ) -> tuple[str, list[Any], str]:
        address = resolve_osc_target_address(self.config, device, parameter_id)
        value_min, value_max = lookup_osc_target_ranges(
            self.config,
            device.adapter,
            parameter_id,
        )

        library_id = device.library.strip()
        if not library_id:
            raise ValueError(f"device {device.uid} has no library configured")
        library = get_osc_library(library_id)
        parameter = next(
            (entry for entry in library.parameters if entry.id == parameter_id),
            None,
        )
        if parameter is None:
            raise ValueError(
                f"unknown OSC parameter {parameter_id!r} in library {library_id!r}"
            )

        if "value" not in payload:
            raise ValueError("value is required when parameter_id is set")

        value = float(payload["value"])
        if value < value_min or value > value_max:
            raise ValueError(
                f"value must be between {value_min} and {value_max} for {parameter.label}"
            )

        if parameter.value_type == "int":
            arguments: list[Any] = [int(round(value))]
        else:
            arguments = [float(value)]

        return address, arguments, parameter.label

    async def _resolve_osc_runtime_adapter(self, name: str) -> OscAdapter:
        adapter = self.osc_adapters.get(name)
        if adapter is not None:
            return adapter

        config = self.config.adapters.get(name)
        if config is None:
            raise ValueError(f"unknown OSC adapter instance: {name}")
        if not config.enabled:
            raise ValueError(f"OSC adapter {name} is disabled; enable it before testing")
        await self._apply_osc_runtime_adapter(name, config)
        adapter = self.osc_adapters.get(name)
        if adapter is None:
            raise ValueError(f"OSC adapter {name} could not be started")
        return adapter

    async def _resolve_wing_native_runtime_adapter(self, name: str) -> WingNativeAdapter:
        adapter = self.wing_native_adapters.get(name)
        if adapter is not None:
            return adapter

        config = self.config.adapters.get(name)
        if config is None:
            raise ValueError(f"unknown Wing native adapter instance: {name}")
        if not config.enabled:
            raise ValueError(
                f"Wing native adapter {name} is disabled; enable it before testing"
            )
        await self._apply_wing_native_runtime_adapter(name, config)
        adapter = self.wing_native_adapters.get(name)
        if adapter is None:
            raise ValueError(f"Wing native adapter {name} could not be started")
        return adapter

    async def send_osc_adapter_test_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("OSC test payload must be an object")

        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("name is required")

        adapter = await self._resolve_osc_runtime_adapter(name)
        if not adapter.running:
            raise OSError(f"OSC adapter {name} is not running")

        address = str(payload.get("address", "")).strip()
        if not address:
            raise ValueError("address is required")
        arguments = self._parse_osc_test_arguments(payload)

        await adapter.send_test_message(address, arguments)
        return {
            "ok": True,
            "name": name,
            "address": address,
            "arguments": arguments,
        }

    async def send_wing_native_adapter_test_message(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Wing native test payload must be an object")

        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("name is required")

        adapter = await self._resolve_wing_native_runtime_adapter(name)
        if not adapter.running:
            raise OSError(f"Wing native adapter {name} is not running")

        address = str(payload.get("address", "")).strip()
        if not address:
            raise ValueError("address is required")
        if "value" not in payload:
            raise ValueError("value is required")

        value = float(payload["value"])
        await adapter.send_test_message(address, value)
        return {
            "ok": True,
            "name": name,
            "address": address if address.startswith("/") else f"/{address}",
            "value": value,
        }

    async def send_device_test_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("device test payload must be an object")

        uid = str(payload.get("uid", "")).strip()
        if not uid:
            raise ValueError("uid is required")

        datapoint_id = str(payload.get("datapoint_id", "")).strip()
        parameter_id = str(payload.get("parameter_id", "")).strip()
        if datapoint_id:
            module, _, point = datapoint_id.partition(".")
            if not module or not point:
                raise ValueError("datapoint_id must be module.point")
            if module != uid:
                raise ValueError(f"datapoint_id {datapoint_id!r} does not belong to device {uid}")
            parameter_id = self._resolve_device_test_parameter_id(
                self.device_registry.require(uid),
                point,
            )
        elif not parameter_id:
            raise ValueError("parameter_id or datapoint_id is required")
        if "value" not in payload:
            raise ValueError("value is required")

        device = self.device_registry.require(uid)
        adapter_config = self.device_registry.adapter_for_device(uid)
        adapter_kind = (adapter_config.kind or device.adapter).strip().lower()
        library_kind = (device.library_kind or "").strip().lower()

        if library_kind == "midi" or (
            not library_kind and adapter_kind in {"midi", "rtp_midi"}
        ):
            return await self._send_device_midi_library_test(
                device,
                adapter_kind,
                parameter_id,
                payload,
            )
        if library_kind in {"osc", "wing"} or adapter_kind in {"osc", "wing_native"}:
            return await self._send_device_osc_library_test(
                device,
                adapter_kind,
                parameter_id,
                payload,
            )
        raise ValueError(
            f"device {uid} library kind {library_kind or adapter_kind!r} "
            "does not support library test send"
        )

    def _resolve_device_test_parameter_id(self, device: DeviceConfig, point: str) -> str:
        adapter_config = self.device_registry.adapter_for_device(device.uid)
        library_kind = (device.library_kind or "").strip().lower()
        adapter_kind = (adapter_config.kind or device.adapter).strip().lower()
        kind = library_kind or adapter_kind
        if kind == "wing_native":
            kind = "wing"

        if kind == "midi" or (not library_kind and adapter_kind in {"midi", "rtp_midi"}):
            return point

        if kind in {"osc", "wing"} or adapter_kind in {"osc", "wing_native"}:
            if not point.startswith("/"):
                return point
            library_id = device.library.strip()
            if not library_id:
                raise ValueError(f"device {device.uid} has no library configured")
            library = get_osc_library(library_id)
            for parameter in library.parameters:
                if parameter.direction != "target":
                    continue
                address = (
                    parameter.address
                    if parameter.address.startswith("/")
                    else parameter.id
                )
                if address == point:
                    return parameter.id
            raise ValueError(
                f"unknown OSC data point {point!r} for device {device.uid}"
            )

        raise ValueError(
            f"device {device.uid} library kind {kind!r} does not support test send"
        )

    async def _send_device_midi_library_test(
        self,
        device: DeviceConfig,
        adapter_kind: str,
        parameter_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if adapter_kind not in {"midi", "rtp_midi"}:
            raise ValueError(
                f"device {device.uid} is bound to adapter kind {adapter_kind!r}, "
                "expected midi or rtp_midi"
            )

        adapter_name = device.adapter
        adapter = (
            self.midi_adapters.get(adapter_name)
            if adapter_kind == "midi"
            else self.rtp_midi_adapters.get(adapter_name)
        )
        if adapter is None:
            raise ValueError(f"unknown {adapter_kind} adapter instance: {adapter_name}")
        if not adapter.running:
            raise OSError(f"{adapter_kind} adapter {adapter_name} is not running")

        adapter_config = self.device_registry.adapter_for_device(device.uid)
        parameter = resolve_midi_target_parameter(
            self.config,
            self.device_registry,
            device.uid,
            parameter_id,
        )
        value_min, value_max = lookup_midi_target_ranges(
            self.config,
            self.device_registry,
            device.uid,
            parameter_id,
        )
        feedback_value = float(payload["value"])
        if feedback_value < value_min or feedback_value > value_max:
            raise ValueError(
                f"value must be between {value_min} and {value_max} for {parameter.label}"
            )
        status, data = encode_midi_target_message(
            parameter,
            feedback_value,
            adapter=adapter_config,
            device=device,
        )

        if isinstance(adapter, MidiAdapter):
            await adapter.send_test_message(
                status,
                data,
                feedback_point=parameter_id,
                feedback_value=feedback_value,
            )
        else:
            await adapter.send_test_message(status, data)

        return {
            "ok": True,
            "uid": device.uid,
            "parameter_id": parameter_id,
            "parameter_label": parameter.label,
            "status": status,
            "data": list(data),
        }

    async def _send_device_osc_library_test(
        self,
        device: DeviceConfig,
        adapter_kind: str,
        parameter_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        address, arguments, parameter_label = self._resolve_device_library_test_message(
            device,
            parameter_id,
            payload,
        )
        adapter_name = device.adapter

        if adapter_kind == "wing_native":
            adapter = await self._resolve_wing_native_runtime_adapter(adapter_name)
            if not adapter.running:
                raise OSError(f"Wing native adapter {adapter_name} is not running")
            if len(arguments) != 1:
                raise ValueError("Wing native test send expects one numeric value")
            await adapter.send_test_message(address, float(arguments[0]))
        elif adapter_kind == "osc":
            adapter = await self._resolve_osc_runtime_adapter(adapter_name)
            if not adapter.running:
                raise OSError(f"OSC adapter {adapter_name} is not running")
            await adapter.send_test_message(address, arguments)
        else:
            raise ValueError(
                f"device {device.uid} is bound to adapter kind {adapter_kind!r}, "
                "expected osc or wing_native"
            )

        return {
            "ok": True,
            "uid": device.uid,
            "parameter_id": parameter_id,
            "parameter_label": parameter_label,
            "address": address,
            "arguments": arguments,
        }

    def _should_list_osc_instance(self, name: str, adapter: AdapterConfig) -> bool:
        kind = adapter.kind or name
        if kind != "osc":
            return False
        if name != "osc":
            return True
        return adapter.enabled or bool(adapter.options)

    def _should_list_wing_native_instance(self, name: str, adapter: AdapterConfig) -> bool:
        kind = adapter.kind or name
        if kind != "wing_native":
            return False
        if name != "wing_native":
            return True
        return adapter.enabled or bool(adapter.options)

    def _osc_instances_payload(self) -> list[dict[str, Any]]:
        return [
            {
                "name": instance["name"],
                "osc_library": instance.get("osc_library", ""),
            }
            for instance in self.osc_adapters_config_payload()["instances"]
            if instance.get("enabled")
        ]

    def _osc_instance_payload(self, name: str, adapter: AdapterConfig) -> dict[str, Any]:
        options = apply_desk_options(dict(adapter.options))
        osc_library = str(options.get("osc_library", ""))
        desk_mode = str(options.get("desk_mode", "")) or desk_mode_for_library(osc_library)
        runtime_adapter = self.osc_adapters.get(name)
        return {
            "uid": name,
            "name": adapter.display_name(name),
            "type": "osc",
            "enabled": adapter.enabled,
            "runtime_active": runtime_adapter is not None and runtime_adapter.running,
            "listen_host": str(options.get("listen_host", "0.0.0.0")),
            "listen_port": int(options.get("listen_port", 9000)),
            "remote_host": str(options.get("remote_host", "")),
            "remote_port": int(options.get("remote_port", 0)),
            "desk_identity": str(options.get("desk_identity", "")),
            "desk_label": str(options.get("desk_label", "")),
            "osc_port": int(options.get("osc_port", options.get("listen_port", 9000))),
            "osc_library": osc_library,
            "desk_mode": desk_mode,
            "desk_sync_on_connect": bool(options.get("desk_sync_on_connect", False)),
            "desk_proxy_mode": bool(options.get("desk_proxy_mode", False)),
            "echo_guard_ms": int(
                options.get("echo_guard_ms", DEFAULT_ECHO_GUARD_MS)
                or DEFAULT_ECHO_GUARD_MS
            ),
            "proxy_client_count": (
                runtime_adapter.desk_proxy_client_count
                if runtime_adapter is not None and runtime_adapter.running
                else 0
            ),
        }

    def _wing_native_instance_payload(self, name: str, adapter: AdapterConfig) -> dict[str, Any]:
        options = dict(adapter.options)
        runtime_adapter = self.wing_native_adapters.get(name)
        payload: dict[str, Any] = {
            "uid": name,
            "name": adapter.display_name(name),
            "type": "wing_native",
            "enabled": adapter.enabled,
            "runtime_active": runtime_adapter is not None and runtime_adapter.running,
            "remote_host": str(options.get("remote_host", "")).strip(),
            "native_port": int(options.get("native_port", 2222)),
            "echo_guard_ms": int(
                options.get("echo_guard_ms", DEFAULT_ECHO_GUARD_MS) or DEFAULT_ECHO_GUARD_MS
            ),
            **self._adapter_device_payload_fields(name),
        }
        runtime_connection = self._adapter_runtime_connection(name)
        if runtime_connection is not None:
            payload["runtime_connection"] = runtime_connection
        if runtime_adapter is not None:
            payload["connectivity"] = runtime_adapter.connectivity_snapshot()
        return payload

    def _normalized_osc_options(
        self,
        payload: dict[str, Any],
        current: dict[str, Any],
    ) -> dict[str, Any]:
        if "desk_mode" in payload:
            osc_library = osc_library_for_desk_mode(str(payload.get("desk_mode", "")))
        else:
            osc_library = str(payload.get("osc_library", current.get("osc_library", ""))).strip()
        desk_mode = is_desk_library(osc_library)

        if desk_mode:
            desk = desk_protocol_for_library(osc_library)
            default_port = desk.default_port if desk is not None else 9000
            osc_port = int(
                payload.get(
                    "osc_port",
                    payload.get(
                        "listen_port",
                        current.get("osc_port", current.get("listen_port", default_port)),
                    ),
                )
            )
            listen_port = osc_port
            remote_port = osc_port
        else:
            listen_port = int(payload.get("listen_port", current.get("listen_port", 9000)))
            remote_port = int(payload.get("remote_port", current.get("remote_port", 0)))

        if not 0 <= listen_port <= 65535:
            raise ValueError("listen_port must be between 0 and 65535")
        if not 0 <= remote_port <= 65535:
            raise ValueError("remote_port must be between 0 and 65535")

        options: dict[str, Any] = {
            "listen_host": str(payload.get("listen_host", current.get("listen_host", "0.0.0.0"))).strip(),
            "listen_port": listen_port,
            "remote_host": str(payload.get("remote_host", current.get("remote_host", ""))).strip(),
            "remote_port": remote_port,
            "desk_sync_on_connect": bool(
                payload.get("desk_sync_on_connect", current.get("desk_sync_on_connect", False))
            ),
            "desk_proxy_mode": bool(
                payload.get("desk_proxy_mode", current.get("desk_proxy_mode", False))
            ),
        }
        if desk_mode:
            options["osc_port"] = listen_port
        if osc_library:
            known_libraries = {library.id for library in list_osc_libraries()}
            if osc_library not in known_libraries:
                raise ValueError(f"unknown OSC library: {osc_library}")
            options["osc_library"] = osc_library
        options["echo_guard_ms"] = parse_echo_guard_ms(
            payload.get("echo_guard_ms", current.get("echo_guard_ms", DEFAULT_ECHO_GUARD_MS))
        )
        desk_identity_value = str(
            payload.get("desk_identity", current.get("desk_identity", ""))
        ).strip()
        if desk_identity_value:
            options["desk_identity"] = desk_identity_value
        desk_label = str(payload.get("desk_label", current.get("desk_label", ""))).strip()
        if desk_label:
            options["desk_label"] = desk_label
        return apply_desk_options(options)

    def _device_registry(self) -> DeviceRegistry:
        return DeviceRegistry.from_config(self.config)

    def _device_library_for_adapter(self, adapter_name: str) -> str:
        return self._device_registry().device_library_for_adapter(adapter_name)

    def _adapter_device_payload_fields(self, adapter_name: str) -> dict[str, Any]:
        device = self._device_registry().device_for_adapter(adapter_name)
        if device is None:
            return {"device_id": "", "device_library": ""}
        payload: dict[str, Any] = {
            "device_id": device.uid,
            "device_uid": device.uid,
            "device_name": device.display_name(),
            "device_library": str(device.library or "").strip(),
        }
        from midijuggler.midi.xtouch_channels import is_xtouch_library

        if is_xtouch_library(payload["device_library"]):
            payload["feedback_refresh_interval"] = float(device.feedback_refresh_interval)
            payload["midi_value_channel"] = int(device.midi_value_channel)
            payload["midi_display_channel"] = int(device.midi_display_channel)
        return payload

    def _resolved_midi_library_id(
        self,
        adapter_name: str,
        payload: dict[str, Any],
        current: dict[str, Any],
    ) -> str:
        from_device = self._device_library_for_adapter(adapter_name)
        if from_device:
            return from_device
        return str(payload.get("midi_library", current.get("midi_library", ""))).strip()

    def _resolved_wing_library_id(self, adapter_name: str) -> str:
        library = self._device_library_for_adapter(adapter_name)
        if library:
            known_libraries = {entry.id for entry in list_osc_libraries()}
            if library in known_libraries and desk_mode_for_library(library) == "wing":
                return library
        return "behringer_wing"

    def _normalized_wing_native_options(
        self,
        payload: dict[str, Any],
        current: dict[str, Any],
        *,
        adapter_name: str = "",
    ) -> dict[str, Any]:
        native_port = int(payload.get("native_port", current.get("native_port", 2222)))
        if not 1 <= native_port <= 65535:
            raise ValueError("native_port must be between 1 and 65535")

        wing_library = self._resolved_wing_library_id(adapter_name)
        known_libraries = {library.id for library in list_osc_libraries()}
        if wing_library not in known_libraries:
            raise ValueError(f"unknown wing library: {wing_library}")
        if desk_mode_for_library(wing_library) != "wing":
            raise ValueError(f"wing library must target a Wing desk, not {wing_library!r}")

        return {
            "remote_host": str(payload.get("remote_host", current.get("remote_host", ""))).strip(),
            "native_port": native_port,
            "wing_library": wing_library,
            "echo_guard_ms": parse_echo_guard_ms(
                payload.get("echo_guard_ms", current.get("echo_guard_ms", DEFAULT_ECHO_GUARD_MS))
            ),
        }

    def _validate_osc_listen_ports(self) -> None:
        port_users: dict[int, str] = {}
        for name, adapter in self.config.adapters.items():
            if not adapter.enabled:
                continue
            kind = adapter.kind or name
            if kind != "osc":
                continue
            options = apply_desk_options(dict(adapter.options))
            listen_port = int(options.get("listen_port", 0))
            if listen_port <= 0:
                continue
            existing = port_users.get(listen_port)
            if existing is not None:
                raise ValueError(
                    f"OSC listen port {listen_port} is already used by adapter {existing!r}"
                )
            port_users[listen_port] = name

    async def discover_osc_desks(self, request: web.Request) -> web.Response:
        protocol = request.query.get("protocol", "all").strip().lower()
        if protocol in {"", "all"}:
            protocols = ["wing", "x32"]
        elif protocol in {"wing", "x32"}:
            protocols = [protocol]
        else:
            raise web.HTTPBadRequest(text="protocol must be wing, x32, or all")

        devices = await discover_desks(protocols)
        if self.osc_desk_tracker is not None:
            self.osc_desk_tracker.remember_desks(devices)
        return web.json_response(
            {
                "devices": [device.as_dict() for device in devices],
                "networks": [str(network) for network in discovery_scan_networks()],
            }
        )

    @staticmethod
    def _desk_label(desk: DiscoveredDesk) -> str:
        parts = [desk.name.strip(), desk.model.strip()]
        if desk.serial.strip():
            parts.append(desk.serial.strip())
        return " · ".join(part for part in parts if part)

    async def _bind_osc_desk_identity(
        self,
        instance_name: str,
        adapter: AdapterConfig,
        desk: DiscoveredDesk,
    ) -> bool:
        identity = desk_identity(desk)
        if not identity:
            return False
        options = dict(adapter.options)
        options["desk_identity"] = identity
        options["desk_label"] = self._desk_label(desk)
        updated = AdapterConfig(enabled=adapter.enabled, options=options, kind="osc")
        self.config.adapters[instance_name] = updated
        if self.config_path is not None:
            save_osc_adapter_configs(self.config_path, {instance_name: updated})
        LOGGER.info(
            "bound OSC adapter %s to desk identity %s (%s)",
            instance_name,
            identity,
            desk.ip,
        )
        return True

    async def apply_osc_desk_ip_from_discovery(
        self,
        instance_name: str,
        desk: DiscoveredDesk,
    ) -> bool:
        adapter = self.config.adapters.get(instance_name)
        if adapter is None or (adapter.kind or instance_name) != "osc":
            return False

        options = dict(adapter.options)
        current_host = str(options.get("remote_host", "")).strip()
        identity = desk_identity(desk)
        if identity:
            options["desk_identity"] = identity
            options["desk_label"] = self._desk_label(desk)
        if current_host == desk.ip and options == dict(adapter.options):
            return False

        options["remote_host"] = desk.ip
        updated = AdapterConfig(enabled=adapter.enabled, options=options, kind="osc")
        self.config.adapters[instance_name] = updated

        if self.config_path is not None:
            save_osc_adapter_configs(self.config_path, {instance_name: updated})

        if adapter.enabled:
            await self._apply_osc_runtime_adapter(instance_name, updated)
            await self._refresh_osc_datapoints(instance_name)

        LOGGER.info(
            "relocated OSC adapter %s to %s (%s)",
            instance_name,
            desk.ip,
            identity or "unknown desk",
        )
        return True

    async def sync_osc_desk_addresses(
        self,
        desks: list[DiscoveredDesk] | None = None,
    ) -> dict[str, Any]:
        discovered = desks if desks is not None else await discover_desks()
        by_identity = {
            identity: desk
            for desk in discovered
            if (identity := desk_identity(desk))
        }
        by_ip = {desk.ip: desk for desk in discovered if desk.ip}

        updates: list[dict[str, str]] = []
        bindings: list[dict[str, str]] = []

        for name, adapter in sorted(self.config.adapters.items()):
            if (adapter.kind or name) != "osc":
                continue

            options = dict(adapter.options)
            if not is_desk_library(str(options.get("osc_library", "")).strip()):
                continue

            identity = str(options.get("desk_identity", "")).strip()
            if not identity:
                remote_host = str(options.get("remote_host", "")).strip()
                matched = by_ip.get(remote_host)
                if matched is not None and await self._bind_osc_desk_identity(name, adapter, matched):
                    bindings.append(
                        {
                            "instance": name,
                            "identity": desk_identity(matched),
                            "ip": matched.ip,
                        }
                    )
                    adapter = self.config.adapters[name]
                    identity = str(adapter.options.get("desk_identity", "")).strip()

            if not identity:
                continue

            desk = by_identity.get(identity)
            if desk is None:
                continue

            if await self.apply_osc_desk_ip_from_discovery(name, desk):
                updates.append(
                    {
                        "instance": name,
                        "identity": identity,
                        "ip": desk.ip,
                    }
                )

        return {
            "desks": [desk.as_dict() for desk in discovered],
            "updates": updates,
            "bindings": bindings,
            "networks": [str(network) for network in discovery_scan_networks()],
        }

    def gpio_config_payload(self) -> dict[str, Any]:
        options = self._gpio_options()
        configured_pins = set(options["pins"])
        gpio_adapter = self.config.adapters["gpio"]
        return {
            "enabled": gpio_adapter.enabled,
            "name": gpio_adapter.display_name("gpio"),
            "runtime_active": self.gpio_adapter is not None and self.gpio_adapter.running,
            "active_low": options["active_low"],
            "bounce_ms": options["bounce_ms"],
            "poll_interval_ms": options["poll_interval_ms"],
            "pins": [
                {
                    "pin": pin,
                    "label": f"GPIO {pin}",
                    "enabled": pin in configured_pins,
                }
                for pin in RASPBERRY_PI_HEADER_BCM_PINS
            ],
        }

    async def apply_gpio_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("GPIO config payload must be an object")
        options = self._normalized_gpio_options(payload)
        gpio_adapter = self.config.adapters["gpio"]
        display_name = validate_device_name(
            str(payload.get("name", gpio_adapter.display_name("gpio"))),
            field_name="gpio.name",
        )
        persisted = False
        persist_error = ""

        if self.gpio_adapter is not None:
            await self.gpio_adapter.configure_options(options)
        else:
            gpio_adapter.options.clear()
            gpio_adapter.options.update(options)

        self.config.adapters["gpio"] = AdapterConfig(
            enabled=gpio_adapter.enabled,
            options=options,
            kind=gpio_adapter.kind or "gpio",
            name=display_name,
        )

        if self.config_path is not None:
            try:
                save_gpio_adapter_options(
                    self.config_path,
                    options,
                    name=display_name,
                )
                persisted = True
            except OSError as exc:
                persist_error = str(exc)
                LOGGER.warning(
                    "GPIO config applied at runtime but could not be persisted to %s: %s",
                    self.config_path,
                    exc,
                )
        else:
            persist_error = "no config path available"

        response = self.gpio_config_payload()
        response.update({"persisted": persisted, "persist_error": persist_error})
        return response

    def hid_adapters_config_payload(self) -> dict[str, Any]:
        return {
            "hid_available": hid_available(),
            "available_devices": list_input_devices(),
            "learn_active": self._hid_learn_instance,
            "instances": [
                self._hid_instance_payload(name, adapter)
                for name, adapter in sorted(self.config.adapters.items())
                if self._should_list_hid_instance(name, adapter)
            ],
        }

    def _should_list_hid_instance(self, name: str, adapter: AdapterConfig) -> bool:
        kind = adapter.kind or name
        if kind != "hid":
            return False
        if name != "hid":
            return True
        return adapter.enabled or bool(adapter.options)

    def _hid_device_fields(self, name: str, options: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_hid_device_options(dict(options))
        available_devices = list_input_devices()
        matched = lookup_input_device(
            vendor_id=normalized.get("vendor_id"),
            product_id=normalized.get("product_id"),
            device_path=str(normalized.get("device", "")).strip() or None,
            devices=available_devices,
        )
        runtime_adapter = self.hid_adapters.get(name)
        resolved_device = ""
        if runtime_adapter is not None and runtime_adapter.device_path:
            resolved_device = runtime_adapter.device_path
        elif matched is not None:
            resolved_device = matched["path"]

        vendor_id = str(normalized.get("vendor_id", "")).strip()
        product_id = str(normalized.get("product_id", "")).strip()
        device_key = ""
        if vendor_id and product_id:
            with contextlib.suppress(ValueError):
                device_key = hid_device_key(vendor_id, product_id)

        device_name = matched["name"] if matched is not None else ""
        legacy_device = str(normalized.get("device", "")).strip()

        return {
            "vendor_id": vendor_id,
            "product_id": product_id,
            "device_key": device_key,
            "device_name": device_name,
            "resolved_device": resolved_device,
            "device": legacy_device,
        }

    def _hid_instance_payload(self, name: str, adapter: AdapterConfig) -> dict[str, Any]:
        options = dict(adapter.options)
        runtime_adapter = self.hid_adapters.get(name)
        device_fields = self._hid_device_fields(name, options)
        inputs = options.get("inputs")
        if not isinstance(inputs, list):
            inputs = []
        normalized_inputs: list[dict[str, Any]] = []
        for raw_input in inputs:
            if not isinstance(raw_input, dict):
                continue
            normalized_inputs.append(
                {
                    "code": str(raw_input.get("code", "")).strip().upper(),
                    "control": str(raw_input.get("control", "")).strip(),
                    "value_min": float(raw_input.get("value_min", 0.0)),
                    "value_max": float(raw_input.get("value_max", 1.0)),
                }
            )
        return {
            "uid": name,
            "name": adapter.display_name(name),
            "type": "hid",
            "enabled": adapter.enabled,
            "runtime_active": runtime_adapter is not None and runtime_adapter.running,
            "learn_active": self._hid_learn_instance == name,
            **device_fields,
            "keystrokes": bool(options.get("keystrokes", False)),
            "grab": bool(options.get("grab", options.get("keystrokes", False))),
            "inputs": normalized_inputs,
        }

    def _normalized_hid_options(
        self,
        payload: dict[str, Any],
        current: dict[str, Any],
    ) -> dict[str, Any]:
        vendor_id = payload.get("vendor_id", current.get("vendor_id"))
        product_id = payload.get("product_id", current.get("product_id"))
        device = str(payload.get("device", current.get("device", ""))).strip()
        device_key = str(payload.get("device_key", "")).strip()
        if device_key and (vendor_id in (None, "") or product_id in (None, "")):
            with contextlib.suppress(ValueError):
                vendor_id, product_id = parse_hid_device_key(device_key)

        raw_inputs = payload.get("inputs", current.get("inputs", []))
        if not isinstance(raw_inputs, list):
            raise ValueError("HID inputs must be a list")

        inputs: list[dict[str, Any]] = []
        for index, raw_input in enumerate(raw_inputs, start=1):
            if not isinstance(raw_input, dict):
                raise ValueError(f"HID inputs[{index}] must be an object")
            code = str(raw_input.get("code", "")).strip().upper()
            if not code:
                raise ValueError(f"HID inputs[{index}].code is required")
            control = str(raw_input.get("control", "")).strip()
            if not control:
                control = code.lower()
            value_min = float(raw_input.get("value_min", 0.0))
            value_max = float(raw_input.get("value_max", 1.0))
            if value_max < value_min:
                raise ValueError(f"HID inputs[{index}].value_max must be >= value_min")
            inputs.append(
                {
                    "code": code,
                    "control": control,
                    "value_min": value_min,
                    "value_max": value_max,
                }
            )

        options: dict[str, Any] = {"inputs": inputs}
        if vendor_id not in (None, "") and product_id not in (None, ""):
            options["vendor_id"] = vendor_id
            options["product_id"] = product_id
        elif device:
            options["device"] = device
        else:
            raise ValueError("HID adapter requires vendor_id and product_id or device")

        if "keystrokes" in payload or "keystrokes" in current:
            options["keystrokes"] = bool(
                payload.get("keystrokes", current.get("keystrokes", False))
            )
        if "grab" in payload or "grab" in current or options.get("keystrokes"):
            options["grab"] = bool(
                payload.get(
                    "grab",
                    current.get("grab", options.get("keystrokes", False)),
                )
            )
        return normalize_hid_device_options(options)

    async def _resolve_hid_runtime_adapter(self, name: str) -> HidAdapter:
        adapter = self.hid_adapters.get(name)
        if adapter is not None:
            return adapter

        config = self.config.adapters.get(name)
        if config is None:
            raise ValueError(f"unknown HID adapter instance: {name}")
        if not config.enabled:
            raise ValueError(f"HID adapter {name} is disabled; enable it before learning")
        await self._apply_hid_runtime_adapter(name, config)
        adapter = self.hid_adapters.get(name)
        if adapter is None:
            raise ValueError(f"HID adapter {name} could not be started")
        return adapter

    async def _apply_hid_runtime_adapter(self, name: str, updated: AdapterConfig) -> None:
        adapter = self.hid_adapters.get(name)
        if adapter is None:
            if not updated.enabled:
                return
            adapter = HidAdapter(name=name, config=updated, bus=self.bus)
            self.hid_adapters[name] = adapter
            try:
                await adapter.start()
            except (OSError, ValueError, ImportError) as exc:
                self.hid_adapters.pop(name, None)
                raise ValueError(str(exc)) from exc
            self._register_runtime_adapter(adapter)
            self._refresh_hid_datapoints(name)
            return

        if updated.enabled:
            try:
                if adapter.running:
                    await adapter.reload(updated)
                else:
                    adapter.config = updated
                    adapter._apply_options(updated.options)  # noqa: SLF001
                    await adapter.start()
            except (OSError, ValueError, ImportError) as exc:
                raise ValueError(str(exc)) from exc
            self._register_runtime_adapter(adapter)
            self._refresh_hid_datapoints(name)
            return

        if self._hid_learn_instance == name:
            await adapter.set_learn_active(False)
            self._hid_learn_instance = None
        if adapter.running:
            await adapter.stop()
        adapter.config = updated
        adapter._apply_options(updated.options)  # noqa: SLF001
        self._unregister_runtime_adapter(adapter)

    async def _refresh_device_datapoints_after_config_change(
        self,
        previous_device_ids: set[str],
    ) -> None:
        if self.datapoint_store is None:
            return

        current_device_ids = set(self.config.devices.keys())
        for device_id in previous_device_ids - current_device_ids:
            self.datapoint_store.unregister_module_except(device_id, set())

        for adapter_name in sorted(self.config.adapters):
            await self._refresh_device_datapoints_for_adapter(adapter_name)

    async def refresh_all_device_datapoints(self) -> None:
        """Register data points for all configured devices, including disabled adapters."""

        object.__setattr__(
            self.config,
            "devices",
            normalize_device_libraries(
                supplement_devices(
                    dict(self.config.devices),
                    self.config.adapters,
                    suppressed_adapters=self.config.runtime.suppressed_inferred_device_adapters,
                ),
                self.config.adapters,
            ),
        )
        self.device_registry.reload_from_config(self.config)
        await self._refresh_device_datapoints_after_config_change(
            set(self.config.devices.keys()),
        )

    async def _refresh_device_datapoints_for_adapter(self, adapter_name: str) -> None:
        adapter_config = self.config.adapters.get(adapter_name)
        if adapter_config is None:
            return

        kind = adapter_config.kind or adapter_name
        if kind == "gpio":
            self._refresh_gpio_datapoints(adapter_name)
            return
        if kind == "hid":
            self._refresh_hid_datapoints(adapter_name)
            return
        if kind in {"midi", "rtp_midi"}:
            self._refresh_midi_datapoints(adapter_name)
            runtime = self.midi_adapters.get(adapter_name)
            if runtime is not None and runtime.running:
                await runtime._start_feedback_refresh()  # noqa: SLF001
            return
        if kind == "osc":
            await self._refresh_osc_datapoints(adapter_name)
            return
        if kind == "wing_native":
            await self._refresh_wing_native_datapoints(adapter_name)

    def _refresh_gpio_datapoints(self, name: str) -> None:
        if self.datapoint_store is None:
            return
        device = self.device_registry.device_for_adapter(name)
        if device is None:
            self.datapoint_store.unregister_module_except(name, set())
            return

        adapter_config = self.config.adapters.get(name)
        if adapter_config is None:
            self.datapoint_store.unregister_module_except(device.uid, set())
            return

        gpio_adapter = self.gpio_adapter
        if gpio_adapter is None or gpio_adapter.name != name:
            gpio_adapter = GpioAdapter(name=name, config=adapter_config, bus=self.bus)

        module = GpioIOModule(
            gpio_adapter,
            device,
            self.datapoint_store,
            self.device_registry,
        )
        specs = module.datapoints()
        keep = {str(spec.id) for spec in specs}
        self.datapoint_store.unregister_module_except(device.uid, keep)
        self.datapoint_store.register_many(specs)

    def _refresh_midi_datapoints(self, name: str) -> None:
        if self.datapoint_store is None:
            return
        device = self.device_registry.device_for_adapter(name)
        if device is None:
            self.datapoint_store.unregister_module_except(name, set())
            return

        adapter_config = self.config.adapters.get(name)
        if adapter_config is None:
            self.datapoint_store.unregister_module_except(device.uid, set())
            return

        adapter = self.midi_adapters.get(name) or self.rtp_midi_adapters.get(name)
        if adapter is None:
            adapter = MidiAdapter(
                name=name,
                config=adapter_config,
                bus=self.bus,
                app_config=self.config,
            )

        module = MidiIOModule(
            adapter,
            device,
            self.datapoint_store,
            self.config,
            self.device_registry,
        )
        specs = module.datapoints()
        keep = {str(spec.id) for spec in specs}
        self.datapoint_store.unregister_module_except(device.uid, keep)
        self.datapoint_store.register_many(specs)

    def _refresh_hid_datapoints(self, name: str) -> None:
        if self.datapoint_store is None:
            return
        device = self.device_registry.device_for_adapter(name)
        adapter_config = self.config.adapters.get(name)
        if device is None or adapter_config is None:
            self.datapoint_store.unregister_module_except(name, set())
            return

        adapter = self.hid_adapters.get(name)
        if adapter is None:
            adapter = HidAdapter(name=name, config=adapter_config, bus=self.bus)

        module = HidIOModule(adapter, device, self.datapoint_store, self.device_registry)
        specs = module.datapoints()
        keep = {str(spec.id) for spec in specs}
        self.datapoint_store.unregister_module_except(device.uid, keep)
        self.datapoint_store.register_many(specs)

    async def _clear_osc_datapoints(self, name: str) -> None:
        if self.datapoint_store is None:
            return
        module = None
        if self._osc_io_modules is not None:
            module = self._osc_io_modules.pop(name, None)
        if module is not None and module.running:
            await module.stop()
        self.datapoint_store.unregister_module_except(name, set())

    async def _refresh_osc_datapoints(self, name: str) -> None:
        if self.datapoint_store is None:
            return
        device = self.device_registry.device_for_adapter(name)
        adapter_config = self.config.adapters.get(name)
        if device is None or adapter_config is None:
            await self._clear_osc_datapoints(name)
            return

        adapter = self.osc_adapters.get(name)
        if adapter is None:
            adapter = OscAdapter(name=name, config=adapter_config, bus=self.bus)

        module = OscIOModule(
            adapter,
            device,
            self.datapoint_store,
            self.config,
            self.device_registry,
        )
        specs = module.datapoints()
        keep = {str(spec.id) for spec in specs}
        self.datapoint_store.unregister_module_except(device.uid, keep)
        self.datapoint_store.register_many(specs)

        if not adapter_config.enabled:
            if self._osc_io_modules is not None:
                existing = self._osc_io_modules.pop(name, None)
                if existing is not None and existing.running:
                    await existing.stop()
            return

        if self._osc_io_modules is not None:
            existing = self._osc_io_modules.get(name)
            if existing is not None and existing.running:
                await existing.stop()
            self._osc_io_modules[name] = module

        await module.start()

    async def _clear_wing_native_datapoints(self, name: str) -> None:
        if self.datapoint_store is None:
            return
        module = None
        if self._osc_io_modules is not None:
            module = self._osc_io_modules.pop(name, None)
        if module is not None and module.running:
            await module.stop()
        self.datapoint_store.unregister_module_except(name, set())

    async def _refresh_wing_native_datapoints(self, name: str) -> None:
        if self.datapoint_store is None:
            return
        device = self.device_registry.device_for_adapter(name)
        adapter_config = self.config.adapters.get(name)
        if device is None or adapter_config is None:
            await self._clear_wing_native_datapoints(name)
            return

        adapter = self.wing_native_adapters.get(name)
        if adapter is None:
            adapter = WingNativeAdapter(name=name, config=adapter_config, bus=self.bus)

        module = WingNativeIOModule(
            adapter,
            device,
            self.datapoint_store,
            self.config,
            self.device_registry,
        )
        specs = module.datapoints()
        keep = {str(spec.id) for spec in specs}
        self.datapoint_store.unregister_module_except(device.uid, keep)
        self.datapoint_store.register_many(specs)

        if not adapter_config.enabled:
            if self._osc_io_modules is not None:
                existing = self._osc_io_modules.pop(name, None)
                if existing is not None and existing.running:
                    await existing.stop()
            return

        if self._osc_io_modules is not None:
            existing = self._osc_io_modules.get(name)
            if existing is not None and existing.running:
                await existing.stop()
            self._osc_io_modules[name] = module

        await module.start()

    async def apply_hid_adapters_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("HID adapter config payload must be an object")

        raw_instances = payload.get("instances")
        if not isinstance(raw_instances, list):
            raise ValueError("HID adapter config requires an instances list")

        raw_deleted = payload.get("deleted", [])
        if not isinstance(raw_deleted, list):
            raise ValueError("deleted must be a list")

        deleted_names: list[str] = []
        updates: dict[str, AdapterConfig] = {}

        for raw_name in raw_deleted:
            name = str(raw_name).strip()
            if not name:
                continue
            if name in DEFAULT_ADAPTERS:
                raise ValueError(f"cannot delete default adapter instance: {name}")
            if name not in self.config.adapters:
                raise ValueError(f"unknown HID adapter instance: {name}")
            adapter_kind = self.config.adapters[name].kind or name
            if adapter_kind != "hid":
                raise ValueError(f"adapter {name} is not a HID adapter")
            deleted_names.append(name)

        for raw_instance in raw_instances:
            if not isinstance(raw_instance, dict):
                raise ValueError("each HID adapter instance must be an object")

            uid, display_name = self._adapter_instance_identity(raw_instance)

            if uid not in self.config.adapters:
                _validate_adapter_instance_name(uid)
                kind = str(raw_instance.get("type", "hid")).strip()
                if kind != "hid":
                    raise ValueError(f"adapter {uid} must use type 'hid', not {kind!r}")
                current_options: dict[str, Any] = {}
                enabled = bool(raw_instance.get("enabled", False))
            else:
                current = self.config.adapters[uid]
                kind = current.kind or uid
                if kind != "hid":
                    raise ValueError(f"adapter {uid} is not a HID adapter")
                current_options = current.options
                enabled = bool(raw_instance.get("enabled", current.enabled))

            options = self._normalized_hid_options(raw_instance, current_options)
            updated = AdapterConfig(
                enabled=enabled,
                options=options,
                kind="hid",
                name=display_name,
            )
            updates[uid] = updated
            self.config.adapters[uid] = updated

        removed_names = [*deleted_names]

        persisted = False
        persist_error = ""
        if self.config_path is not None and (updates or removed_names):
            try:
                if updates:
                    save_hid_adapter_configs(self.config_path, updates)
                if removed_names:
                    remove_hid_adapter_configs(self.config_path, removed_names)
                persisted = True
            except OSError as exc:
                persist_error = str(exc)
                LOGGER.warning(
                    "HID adapter config applied at runtime but could not be persisted to %s: %s",
                    self.config_path,
                    exc,
                )
        elif self.config_path is None and (updates or removed_names):
            persist_error = "no config path available"

        for name in deleted_names:
            adapter = self.hid_adapters.pop(name, None)
            if adapter is not None:
                if self._hid_learn_instance == name:
                    self._hid_learn_instance = None
                if adapter.running:
                    await adapter.stop()
                self._unregister_runtime_adapter(adapter)
            self.config.adapters.pop(name, None)

        for name, updated in updates.items():
            await self._apply_hid_runtime_adapter(name, updated)

        response = self.hid_adapters_config_payload()
        response.update({"persisted": persisted, "persist_error": persist_error})
        return response

    async def apply_hid_learn_mode(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("HID learn payload must be an object")

        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("name is required")
        active = bool(payload.get("active", False))
        from midijuggler.device.identity import resolve_adapter_uid

        uid = resolve_adapter_uid(name, self.config.adapters) or name

        if active:
            for instance_name, adapter in self.hid_adapters.items():
                if instance_name != uid:
                    await adapter.set_learn_active(False)
            adapter = await self._resolve_hid_runtime_adapter(uid)
            if not adapter.running:
                raise ValueError(f"HID adapter {uid} is not running")
            await adapter.set_learn_active(True)
            self._hid_learn_instance = uid
        else:
            adapter = self.hid_adapters.get(uid)
            if adapter is not None:
                await adapter.set_learn_active(False)
            if self._hid_learn_instance == uid:
                self._hid_learn_instance = None

        return self.hid_adapters_config_payload()

    def _adapter_instance_identity(self, raw_instance: dict[str, Any]) -> tuple[str, str]:
        from midijuggler.device.identity import resolve_adapter_instance_identity

        return resolve_adapter_instance_identity(raw_instance)

    def _rename_adapter_config_instance(
        self,
        old_name: str,
        new_name: str,
        *,
        allowed_kinds: set[str],
    ) -> str:
        _validate_adapter_instance_name(new_name)
        if old_name in DEFAULT_ADAPTERS:
            raise ValueError(f"cannot rename default adapter instance: {old_name}")
        if new_name in DEFAULT_ADAPTERS:
            raise ValueError(f"cannot rename adapter instance to reserved name: {new_name}")
        if old_name not in self.config.adapters:
            raise ValueError(f"unknown adapter instance: {old_name}")
        if new_name in self.config.adapters:
            raise ValueError(f"adapter instance already exists: {new_name}")

        adapter = self.config.adapters[old_name]
        kind = adapter.kind or old_name
        if kind not in allowed_kinds:
            raise ValueError(f"adapter {old_name} is not a supported adapter instance")

        self.config.adapters[new_name] = adapter
        self.config.adapters.pop(old_name)
        return kind

    def _register_runtime_adapter(self, adapter: Adapter) -> None:
        if self._runtime_adapters is None:
            return
        if adapter not in self._runtime_adapters:
            self._runtime_adapters.append(adapter)

    def _unregister_runtime_adapter(self, adapter: Adapter) -> None:
        if self._runtime_adapters is None:
            return
        with contextlib.suppress(ValueError):
            self._runtime_adapters.remove(adapter)

    async def _apply_osc_runtime_adapter(self, name: str, updated: AdapterConfig) -> None:
        adapter = self.osc_adapters.get(name)
        if adapter is None:
            if not updated.enabled:
                return
            adapter = OscAdapter(name=name, config=updated, bus=self.bus)
            self.osc_adapters[name] = adapter
            try:
                await adapter.start()
            except OSError as exc:
                self.osc_adapters.pop(name, None)
                raise ValueError(str(exc)) from exc
            self._register_runtime_adapter(adapter)
            return

        if updated.enabled:
            try:
                if adapter.running:
                    await adapter.reload(updated)
                else:
                    adapter.config = updated
                    adapter._apply_options(updated.options)  # noqa: SLF001
                    await adapter.start()
            except OSError as exc:
                raise ValueError(str(exc)) from exc
            self._register_runtime_adapter(adapter)
            return

        if adapter.running:
            await adapter.stop()
        adapter.config = updated
        adapter._apply_options(updated.options)  # noqa: SLF001

    async def _apply_wing_native_runtime_adapter(self, name: str, updated: AdapterConfig) -> None:
        adapter = self.wing_native_adapters.get(name)
        if adapter is None:
            if not updated.enabled:
                return
            adapter = WingNativeAdapter(name=name, config=updated, bus=self.bus)
            self.wing_native_adapters[name] = adapter
            try:
                await adapter.start()
            except OSError as exc:
                self.wing_native_adapters.pop(name, None)
                raise ValueError(str(exc)) from exc
            self._register_runtime_adapter(adapter)
            return

        if updated.enabled:
            try:
                if adapter.running:
                    await adapter.reload(updated)
                else:
                    adapter.config = updated
                    adapter._apply_options(updated.options)  # noqa: SLF001
                    await adapter.start()
            except OSError as exc:
                raise ValueError(str(exc)) from exc
            self._register_runtime_adapter(adapter)
            return

        if adapter.running:
            await adapter.stop()
        adapter.config = updated
        adapter._apply_options(updated.options)  # noqa: SLF001

    async def _rename_runtime_adapter(self, old_name: str, new_name: str, kind: str) -> None:
        if kind == "midi":
            adapter = self.midi_adapters.pop(old_name, None)
            if adapter is not None:
                adapter.name = new_name
                self.midi_adapters[new_name] = adapter
            return

        if kind == "osc":
            adapter = self.osc_adapters.pop(old_name, None)
            if adapter is not None:
                adapter.name = new_name
                self.osc_adapters[new_name] = adapter
            return

        if kind == "wing_native":
            adapter = self.wing_native_adapters.pop(old_name, None)
            if adapter is not None:
                adapter.name = new_name
                self.wing_native_adapters[new_name] = adapter
            return

        if kind == "hid":
            adapter = self.hid_adapters.pop(old_name, None)
            if adapter is not None:
                adapter.name = new_name
                self.hid_adapters[new_name] = adapter
            if self._hid_learn_instance == old_name:
                self._hid_learn_instance = new_name
            return

        if kind == "rtp_midi" and self.rtp_midi_manager is not None:
            config = self.config.adapters.get(new_name)
            if config is not None:
                await self.rtp_midi_manager.remove_instance(old_name)
                await self.rtp_midi_manager.apply_instance(new_name, config)

    def midi_adapters_config_payload(self) -> dict[str, Any]:
        available_input_ports = list_midi_input_ports()
        available_output_ports = list_midi_output_ports()
        libraries = list_midi_libraries()
        discovered_sessions = (
            self.rtp_midi_manager.discovered_sessions()
            if self.rtp_midi_manager is not None
            else []
        )
        return {
            "available_ports": list_midi_ports(),
            "available_input_ports": available_input_ports,
            "available_output_ports": available_output_ports,
            "available_midi_libraries": [
                {"id": library.id, "label": library.name}
                for library in libraries
            ],
            "rtp_midi_available": (
                self.rtp_midi_manager.available if self.rtp_midi_manager is not None else False
            ),
            "rtp_midi_backend": (
                self.rtp_midi_manager.backend if self.rtp_midi_manager is not None else "none"
            ),
            "discovered_rtp_sessions": discovered_sessions,
            "joinable_rtp_sessions": (
                self.rtp_midi_manager.joinable_sessions()
                if self.rtp_midi_manager is not None
                else []
            ),
            "hosted_rtp_session_ids": (
                sorted(self.rtp_midi_manager.hosted_session_ids())
                if self.rtp_midi_manager is not None
                else []
            ),
            "instances": [
                self._midi_instance_payload(
                    name,
                    adapter,
                    available_input_ports,
                    available_output_ports,
                )
                for name, adapter in sorted(self.config.adapters.items())
                if (adapter.kind or name) in {"midi", "rtp_midi"}
            ],
        }

    async def _apply_midi_runtime_adapter(self, name: str, updated: AdapterConfig) -> None:
        adapter = self.midi_adapters.get(name)
        if adapter is None:
            if not updated.enabled:
                return
            adapter = MidiAdapter(
                name=name,
                config=updated,
                bus=self.bus,
                app_config=self.config,
            )
            self.midi_adapters[name] = adapter
            try:
                await adapter.start()
            except OSError as exc:
                self.midi_adapters.pop(name, None)
                raise ValueError(str(exc)) from exc
            self._register_runtime_adapter(adapter)
            return

        if updated.enabled:
            try:
                await adapter.reload(updated)
            except OSError as exc:
                raise ValueError(str(exc)) from exc
            self._register_runtime_adapter(adapter)
            return

        if adapter.running:
            await adapter.stop()
        adapter.config = updated
        self._unregister_runtime_adapter(adapter)

    async def apply_midi_adapters_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("MIDI adapter config payload must be an object")

        raw_instances = payload.get("instances")
        if not isinstance(raw_instances, list):
            raise ValueError("MIDI adapter config requires an instances list")

        kind_filter = payload.get("kind")
        if kind_filter is not None:
            kind_filter = str(kind_filter).strip()
            if kind_filter not in {"midi", "rtp_midi"}:
                raise ValueError("kind must be midi or rtp_midi")

        raw_deleted = payload.get("deleted", [])
        if not isinstance(raw_deleted, list):
            raise ValueError("deleted must be a list")

        deleted_names: list[str] = []
        deleted_rtp_names: list[str] = []
        for raw_name in raw_deleted:
            name = str(raw_name).strip()
            if not name:
                continue
            if name in DEFAULT_ADAPTERS:
                raise ValueError(f"cannot delete default adapter instance: {name}")
            if name not in self.config.adapters:
                raise ValueError(f"unknown MIDI adapter instance: {name}")

            adapter_kind = self.config.adapters[name].kind or name
            if adapter_kind not in {"midi", "rtp_midi"}:
                raise ValueError(f"adapter {name} is not a MIDI adapter")
            if kind_filter is not None and adapter_kind != kind_filter:
                raise ValueError(
                    f"adapter {name} is not a {kind_filter} adapter instance"
                )

            deleted_names.append(name)
            if adapter_kind == "rtp_midi":
                deleted_rtp_names.append(name)

        for name in deleted_names:
            adapter_config = self.config.adapters.get(name)
            adapter_kind = adapter_config.kind or name if adapter_config else name
            if adapter_kind == "midi":
                adapter = self.midi_adapters.pop(name, None)
                if adapter is not None:
                    if adapter.running:
                        await adapter.stop()
                    self._unregister_runtime_adapter(adapter)
                self._adapter_runtime_status.pop(name, None)
            self.config.adapters.pop(name, None)

        updates: dict[str, AdapterConfig] = {}
        for raw_instance in raw_instances:
            if not isinstance(raw_instance, dict):
                raise ValueError("each MIDI adapter instance must be an object")
            uid, display_name = self._adapter_instance_identity(raw_instance)

            if uid not in self.config.adapters:
                if kind_filter is None:
                    raise ValueError(f"unknown MIDI adapter instance: {uid}")
                _validate_adapter_instance_name(uid)
                if uid in DEFAULT_ADAPTERS:
                    raise ValueError(
                        f"cannot create reserved adapter instance name: {uid}"
                    )

                kind = str(raw_instance.get("type", kind_filter)).strip()
                if kind != kind_filter:
                    raise ValueError(
                        f"adapter {uid} must use type {kind_filter!r}, not {kind!r}"
                    )
                current_options: dict[str, Any] = {}
                enabled = bool(raw_instance.get("enabled", False))
            else:
                current = self.config.adapters[uid]
                kind = current.kind or uid
                if kind not in {"midi", "rtp_midi"}:
                    raise ValueError(f"adapter {uid} is not a MIDI adapter")
                if kind_filter is not None and kind != kind_filter:
                    raise ValueError(
                        f"adapter {uid} is not a {kind_filter} adapter instance"
                    )
                current_options = current.options
                enabled = bool(raw_instance.get("enabled", current.enabled))

            if kind == "midi":
                options = self._normalized_midi_options(
                    raw_instance,
                    current_options,
                    adapter_name=uid,
                )
            else:
                options = self._normalized_rtp_midi_options(
                    raw_instance,
                    current_options,
                    enabled=enabled,
                )

            updated = AdapterConfig(
                enabled=enabled,
                options=options,
                kind=kind,
                name=display_name,
            )
            updates[uid] = updated
            self.config.adapters[uid] = updated

        removed_names = [*deleted_names]

        persisted = False
        persist_error = ""
        if self.config_path is not None and (updates or removed_names):
            try:
                if updates:
                    save_midi_adapter_configs(self.config_path, updates)
                if removed_names:
                    remove_midi_adapter_configs(self.config_path, removed_names)
                persisted = True
            except OSError as exc:
                persist_error = str(exc)
                LOGGER.warning(
                    "MIDI adapter config applied at runtime but could not be persisted to %s: %s",
                    self.config_path,
                    exc,
                )
        elif self.config_path is None and (updates or removed_names):
            persist_error = "no config path available"

        if self.rtp_midi_manager is not None:
            await self.rtp_midi_manager.start()
            for name in deleted_rtp_names:
                await self.rtp_midi_manager.remove_instance(name)
            for name, updated in updates.items():
                if updated.kind == "rtp_midi":
                    await self.rtp_midi_manager.apply_instance(name, updated)

        for name, updated in updates.items():
            if updated.kind != "midi":
                continue
            await self._apply_midi_runtime_adapter(name, updated)

        previous_device_uids = set(self.config.devices.keys())
        object.__setattr__(
            self.config,
            "devices",
            normalize_device_libraries(
                supplement_devices(
                    dict(self.config.devices),
                    self.config.adapters,
                    suppressed_adapters=self.config.runtime.suppressed_inferred_device_adapters,
                ),
                self.config.adapters,
            ),
        )
        self.device_registry.reload_from_config(self.config)
        await self._refresh_device_datapoints_after_config_change(previous_device_uids)

        response = self.midi_adapters_config_payload()
        response.update({"persisted": persisted, "persist_error": persist_error})
        return response

    def osc_adapters_config_payload(self) -> dict[str, Any]:
        libraries = list_osc_libraries()
        return {
            "available_osc_libraries": [
                {"id": library.id, "label": library.name}
                for library in libraries
            ],
            "instances": [
                self._osc_instance_payload(name, adapter)
                for name, adapter in sorted(self.config.adapters.items())
                if self._should_list_osc_instance(name, adapter)
            ],
        }

    async def apply_osc_adapters_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("OSC adapter config payload must be an object")

        raw_instances = payload.get("instances")
        if not isinstance(raw_instances, list):
            raise ValueError("OSC adapter config requires an instances list")

        raw_deleted = payload.get("deleted", [])
        if not isinstance(raw_deleted, list):
            raise ValueError("deleted must be a list")

        deleted_names: list[str] = []
        for raw_name in raw_deleted:
            name = str(raw_name).strip()
            if not name:
                continue
            if name not in self.config.adapters:
                raise ValueError(f"unknown OSC adapter instance: {name}")
            adapter_kind = self.config.adapters[name].kind or name
            if adapter_kind != "osc":
                raise ValueError(f"adapter {name} is not an OSC adapter")
            deleted_names.append(name)

        for name in deleted_names:
            adapter = self.osc_adapters.pop(name, None)
            if adapter is not None:
                if adapter.running:
                    await adapter.stop()
                self._unregister_runtime_adapter(adapter)
            self.config.adapters.pop(name, None)
            await self._clear_osc_datapoints(name)

        updates: dict[str, AdapterConfig] = {}
        for raw_instance in raw_instances:
            if not isinstance(raw_instance, dict):
                raise ValueError("each OSC adapter instance must be an object")
            uid, display_name = self._adapter_instance_identity(raw_instance)

            if uid not in self.config.adapters:
                _validate_adapter_instance_name(uid)
                kind = str(raw_instance.get("type", "osc")).strip()
                if kind != "osc":
                    raise ValueError(f"adapter {uid} must use type 'osc', not {kind!r}")
                current_options: dict[str, Any] = {}
                enabled = bool(raw_instance.get("enabled", False))
            else:
                current = self.config.adapters[uid]
                kind = current.kind or uid
                if kind != "osc":
                    raise ValueError(f"adapter {uid} is not an OSC adapter")
                current_options = current.options
                enabled = bool(raw_instance.get("enabled", current.enabled))

            options = self._normalized_osc_options(raw_instance, current_options)
            updated = AdapterConfig(
                enabled=enabled,
                options=options,
                kind="osc",
                name=display_name,
            )
            updates[uid] = updated
            self.config.adapters[uid] = updated

        self._validate_osc_listen_ports()

        removed_names = [*deleted_names]

        persisted = False
        persist_error = ""
        if self.config_path is not None and (updates or removed_names):
            try:
                if updates:
                    save_osc_adapter_configs(self.config_path, updates)
                if removed_names:
                    remove_osc_adapter_configs(self.config_path, removed_names)
                persisted = True
            except OSError as exc:
                persist_error = str(exc)
                LOGGER.warning(
                    "OSC adapter config applied at runtime but could not be persisted to %s: %s",
                    self.config_path,
                    exc,
                )
        elif self.config_path is None and (updates or removed_names):
            persist_error = "no config path available"

        for name, updated in updates.items():
            await self._apply_osc_runtime_adapter(name, updated)
            if updated.enabled:
                await self._refresh_osc_datapoints(name)
            else:
                await self._clear_osc_datapoints(name)

        response = self.osc_adapters_config_payload()
        response.update({"persisted": persisted, "persist_error": persist_error})
        return response

    def wing_native_adapters_config_payload(self) -> dict[str, Any]:
        libraries = list_osc_libraries()
        return {
            "available_wing_libraries": [
                {"id": library.id, "label": library.name}
                for library in libraries
                if desk_mode_for_library(library.id) == "wing"
            ],
            "instances": [
                self._wing_native_instance_payload(name, adapter)
                for name, adapter in sorted(self.config.adapters.items())
                if self._should_list_wing_native_instance(name, adapter)
            ],
        }

    async def apply_wing_native_adapters_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Wing native adapter config payload must be an object")

        raw_instances = payload.get("instances")
        if not isinstance(raw_instances, list):
            raise ValueError("Wing native adapter config requires an instances list")

        raw_deleted = payload.get("deleted", [])
        if not isinstance(raw_deleted, list):
            raise ValueError("deleted must be a list")

        deleted_names: list[str] = []
        for raw_name in raw_deleted:
            name = str(raw_name).strip()
            if not name:
                continue
            if name not in self.config.adapters:
                raise ValueError(f"unknown Wing native adapter instance: {name}")
            adapter_kind = self.config.adapters[name].kind or name
            if adapter_kind != "wing_native":
                raise ValueError(f"adapter {name} is not a Wing native adapter")
            deleted_names.append(name)

        for name in deleted_names:
            adapter = self.wing_native_adapters.pop(name, None)
            if adapter is not None:
                if adapter.running:
                    await adapter.stop()
                self._unregister_runtime_adapter(adapter)
            self.config.adapters.pop(name, None)
            await self._clear_wing_native_datapoints(name)

        updates: dict[str, AdapterConfig] = {}
        for raw_instance in raw_instances:
            if not isinstance(raw_instance, dict):
                raise ValueError("each Wing native adapter instance must be an object")
            uid, display_name = self._adapter_instance_identity(raw_instance)

            if uid not in self.config.adapters:
                _validate_adapter_instance_name(uid)
                kind = str(raw_instance.get("type", "wing_native")).strip()
                if kind != "wing_native":
                    raise ValueError(
                        f"adapter {uid} must use type 'wing_native', not {kind!r}"
                    )
                current_options: dict[str, Any] = {}
                enabled = bool(raw_instance.get("enabled", False))
            else:
                current = self.config.adapters[uid]
                kind = current.kind or uid
                if kind != "wing_native":
                    raise ValueError(f"adapter {uid} is not a Wing native adapter")
                current_options = current.options
                enabled = bool(raw_instance.get("enabled", current.enabled))

            options = self._normalized_wing_native_options(
                raw_instance,
                current_options,
                adapter_name=uid,
            )
            updated = AdapterConfig(
                enabled=enabled,
                options=options,
                kind="wing_native",
                name=display_name,
            )
            updates[uid] = updated
            self.config.adapters[uid] = updated

        removed_names = [*deleted_names]

        persisted = False
        persist_error = ""
        if self.config_path is not None and (updates or removed_names):
            try:
                if updates:
                    save_wing_native_adapter_configs(self.config_path, updates)
                if removed_names:
                    remove_wing_native_adapter_configs(self.config_path, removed_names)
                persisted = True
            except OSError as exc:
                persist_error = str(exc)
                LOGGER.warning(
                    "Wing native adapter config applied at runtime but could not be persisted to %s: %s",
                    self.config_path,
                    exc,
                )
        elif self.config_path is None and (updates or removed_names):
            persist_error = "no config path available"

        for name, updated in updates.items():
            await self._apply_wing_native_runtime_adapter(name, updated)
            if updated.enabled:
                await self._refresh_wing_native_datapoints(name)
            else:
                await self._clear_wing_native_datapoints(name)

        response = self.wing_native_adapters_config_payload()
        response.update({"persisted": persisted, "persist_error": persist_error})
        return response

    def master_clock_config_payload(self) -> dict[str, Any]:
        config = self.master_clock.config
        selected_outputs = set(config.output_targets)
        return {
            "enabled": config.enabled,
            "bpm": self.master_clock.bpm,
            "bpm_min": config.bpm_min,
            "bpm_max": config.bpm_max,
            "auto_start": config.auto_start,
            "output_targets": config.output_targets,
            "available_output_targets": self._available_adapter_targets(
                {"midi", "rtp_midi"},
                selected_outputs,
                require_enabled_for_selection=True,
            ),
            "send_transport": config.send_transport,
            "click_enabled": config.click_enabled,
            "click_wav": config.click_wav,
            "click_interval": config.click_interval,
            "tap_tempo_min_taps": config.tap_tempo_min_taps,
            "bpm_step": config.bpm_step,
            "bpm_huge_step": config.bpm_huge_step,
            "click_audio_device": normalize_alsa_output_device(
                config.click_audio_device,
            ),
            "click_audio_resolved_device": self._resolved_audio_device(
                config.click_audio_device,
            ),
            "available_audio_devices": self._audio_devices(config.click_audio_device),
            "available_click_wavs": self._click_wavs(config.click_wav),
            "name": config.name,
            "beat_flash_ms": config.beat_flash_ms,
            "running": self.master_clock.running,
            "position_ticks": self.master_clock.position_ticks,
            "parameters": self.master_clock.parameters.as_controls(),
        }

    async def apply_master_clock_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Master clock config payload must be an object")
        config = self._normalized_master_clock_config(payload)
        alsa_config_error = ""
        if self.alsa_config_path is not None:
            try:
                write_master_clock_pcm_config(
                    self.alsa_config_path,
                    resolve_alsa_output_device(config.click_audio_device),
                )
            except OSError as exc:
                alsa_config_error = str(exc)
                LOGGER.warning(
                    "Master clock config applied but ALSA dmix config could not be written to %s: %s",
                    self.alsa_config_path,
                    exc,
                )
        await self.master_clock.configure(config)

        persisted = False
        persist_error = ""
        if self.config_path is not None:
            try:
                save_master_clock_config(
                    self.config_path,
                    config,
                    datapoint_routing=self.config.runtime.datapoint_routing,
                )
                persisted = True
            except OSError as exc:
                persist_error = str(exc)
                LOGGER.warning(
                    "Master clock config applied at runtime but could not be persisted to %s: %s",
                    self.config_path,
                    exc,
                )
        else:
            persist_error = "no config path available"

        response = self.master_clock_config_payload()
        response.update(
            {
                "persisted": persisted,
                "persist_error": persist_error,
                "alsa_config_error": alsa_config_error,
            }
        )
        await self.broadcast_status()
        return response

    def rotary_display_config_payload(self) -> dict[str, Any]:
        config = self.config.rotary_display
        device = config.device
        push_status = (
            self._rotary_display_module.device_push_status()
            if self._rotary_display_module is not None
            else {
                "serial_connected": False,
                "last_pushed_fingerprint": None,
                "current_fingerprint": None,
                "push_pending": True,
            }
        )
        return {
            "enabled": config.enabled,
            "transport": config.transport,
            "feedback_host": config.feedback_host,
            "feedback_port": config.feedback_port,
            "serial_port": config.serial_port,
            "serial_baud": config.serial_baud,
            "device": {
                "transport": device.transport,
                "wifi_enabled": device.wifi_enabled,
                "wifi_ssid": device.wifi_ssid,
                "wifi_pass": device.wifi_pass,
                "host": device.host,
                "port": device.port,
                "listen_port": device.listen_port,
                "pulse_enabled": device.pulse_enabled,
                "bpm_step": device.bpm_step,
            },
            "push": push_status,
        }

    async def apply_rotary_display_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("rotary display config payload must be an object")

        config = self._normalized_rotary_display_config(payload)
        previous_serial_port = self.config.rotary_display.serial_port
        self.config = replace(self.config, rotary_display=config)

        push_result: dict[str, Any] = {"pushed": False, "reason": "module unavailable"}
        if self._rotary_display_module is not None:
            self._rotary_display_module.update_config(config)
            push_result = await self._rotary_display_module.push_device_config(force=True)
            await self._rotary_display_module.apply_runtime_config(config)

        persisted = False
        persist_error = ""
        if self.config_path is not None:
            try:
                save_rotary_display_config(self.config_path, config)
                persisted = True
            except OSError as exc:
                persist_error = str(exc)
                LOGGER.warning(
                    "Rotary display config applied at runtime but could not be persisted to %s: %s",
                    self.config_path,
                    exc,
                )
        else:
            persist_error = "no config path available"

        response = self.rotary_display_config_payload()
        response.update(
            {
                "persisted": persisted,
                "persist_error": persist_error,
                "restart_required": config.serial_port != previous_serial_port,
                "push_result": push_result,
            }
        )
        return response

    async def apply_rotary_display_push(self) -> dict[str, Any]:
        if self._rotary_display_module is None:
            raise ValueError("rotary display module is not enabled")
        push_result = await self._rotary_display_module.push_device_config(force=True)
        response = self.rotary_display_config_payload()
        response["push_result"] = push_result
        return response

    def _normalized_rotary_display_config(self, payload: dict[str, Any]) -> RotaryDisplayConfig:
        current = self.config.rotary_display
        device_payload = payload.get("device", {})
        if device_payload is not None and not isinstance(device_payload, dict):
            raise ValueError("rotary display device config must be an object")

        raw_device = dict(current.device.__dict__)
        if isinstance(device_payload, dict):
            if "transport" in device_payload:
                transport = str(device_payload["transport"]).strip().lower()
                if transport not in {"serial", "wifi", "both"}:
                    raise ValueError("device.transport must be serial, wifi, or both")
                raw_device["transport"] = transport
            if "wifi_enabled" in device_payload:
                raw_device["wifi_enabled"] = bool(device_payload["wifi_enabled"])
            if "wifi_ssid" in device_payload:
                raw_device["wifi_ssid"] = str(device_payload["wifi_ssid"]).strip()
            if "wifi_pass" in device_payload:
                raw_device["wifi_pass"] = str(device_payload["wifi_pass"])
            if "host" in device_payload:
                host = str(device_payload["host"]).strip()
                if not host:
                    raise ValueError("device.host must not be empty")
                raw_device["host"] = host
            if "port" in device_payload:
                port = int(device_payload["port"])
                if port <= 0 or port > 65535:
                    raise ValueError("device.port must be between 1 and 65535")
                raw_device["port"] = port
            if "listen_port" in device_payload:
                listen_port = int(device_payload["listen_port"])
                if listen_port <= 0 or listen_port > 65535:
                    raise ValueError("device.listen_port must be between 1 and 65535")
                raw_device["listen_port"] = listen_port
            if "pulse_enabled" in device_payload:
                raw_device["pulse_enabled"] = bool(device_payload["pulse_enabled"])
            if "bpm_step" in device_payload:
                bpm_step = float(device_payload["bpm_step"])
                if bpm_step <= 0:
                    raise ValueError("device.bpm_step must be positive")
                raw_device["bpm_step"] = bpm_step

        device = RotaryDisplayDeviceConfig(**raw_device)

        transport = str(payload.get("transport", current.transport)).strip().lower()
        if transport not in {"osc", "serial", "both"}:
            raise ValueError("transport must be osc, serial, or both")

        feedback_port = int(payload.get("feedback_port", current.feedback_port))
        if feedback_port <= 0 or feedback_port > 65535:
            raise ValueError("feedback_port must be between 1 and 65535")

        serial_baud = int(payload.get("serial_baud", current.serial_baud))
        if serial_baud <= 0:
            raise ValueError("serial_baud must be positive")

        return RotaryDisplayConfig(
            enabled=bool(payload.get("enabled", current.enabled)),
            transport=transport,
            feedback_host=str(payload.get("feedback_host", current.feedback_host)).strip(),
            feedback_port=feedback_port,
            serial_port=str(payload.get("serial_port", current.serial_port)).strip(),
            serial_baud=serial_baud,
            hello_osc_address=str(
                payload.get("hello_osc_address", current.hello_osc_address)
            ),
            sync_osc_address=str(payload.get("sync_osc_address", current.sync_osc_address)),
            beat_osc_address=str(payload.get("beat_osc_address", current.beat_osc_address)),
            device=device,
        )

    def bandhelper_config_payload(self) -> dict[str, Any]:
        config = self.config.bandhelper
        snapshot = self.datapoint_store.snapshot() if self.datapoint_store is not None else {}
        link_tempo = snapshot.get("song.link_tempo", {})
        link_peers = snapshot.get("song.link_peers", {})
        key_root = snapshot.get("song.key_root", {})
        key_minor = snapshot.get("song.key_minor", {})
        return {
            "enabled": config.enabled,
            "link_enabled": config.link_enabled,
            "start_bpm": config.start_bpm,
            "min_bpm_delta": config.min_bpm_delta,
            "follow_when_running": config.follow_when_running,
            "quantize_step": config.quantize_step,
            "poll_interval_ms": config.poll_interval_ms,
            "key_osc_address": config.key_osc_address,
            "key_root_osc_address": config.key_root_osc_address,
            "key_mode_osc_address": config.key_mode_osc_address,
            "module_active": self._bandhelper_module is not None,
            "status": {
                "link_tempo": link_tempo.get("float_value"),
                "link_peers": link_peers.get("int_value"),
                "key_root": key_root.get("int_value"),
                "key_minor": key_minor.get("bool_value"),
            },
        }

    async def apply_bandhelper_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("bandhelper config payload must be an object")

        config = self._normalized_bandhelper_config(payload)
        previous_enabled = self.config.bandhelper.enabled
        self.config = replace(self.config, bandhelper=config)

        if self._bandhelper_module is not None:
            self._bandhelper_module.update_config(config)

        persisted = False
        persist_error = ""
        if self.config_path is not None:
            try:
                save_bandhelper_config(self.config_path, config)
                persisted = True
            except OSError as exc:
                persist_error = str(exc)
                LOGGER.warning(
                    "BandHelper config applied at runtime but could not be persisted to %s: %s",
                    self.config_path,
                    exc,
                )
        else:
            persist_error = "no config path available"

        response = self.bandhelper_config_payload()
        response.update(
            {
                "persisted": persisted,
                "persist_error": persist_error,
                "restart_required": config.enabled != previous_enabled,
            }
        )
        return response

    def _normalized_bandhelper_config(self, payload: dict[str, Any]) -> BandHelperConfig:
        current = self.config.bandhelper
        start_bpm = float(payload.get("start_bpm", current.start_bpm))
        if start_bpm <= 0:
            raise ValueError("start_bpm must be positive")

        min_bpm_delta = float(payload.get("min_bpm_delta", current.min_bpm_delta))
        if min_bpm_delta < 0:
            raise ValueError("min_bpm_delta must be >= 0")

        quantize_step = float(payload.get("quantize_step", current.quantize_step))
        if quantize_step <= 0:
            raise ValueError("quantize_step must be positive")

        poll_interval_ms = int(payload.get("poll_interval_ms", current.poll_interval_ms))
        if poll_interval_ms <= 0:
            raise ValueError("poll_interval_ms must be positive")

        return BandHelperConfig(
            enabled=bool(payload.get("enabled", current.enabled)),
            link_enabled=bool(payload.get("link_enabled", current.link_enabled)),
            start_bpm=start_bpm,
            min_bpm_delta=min_bpm_delta,
            follow_when_running=bool(
                payload.get("follow_when_running", current.follow_when_running)
            ),
            quantize_step=quantize_step,
            poll_interval_ms=poll_interval_ms,
            key_osc_address=str(
                payload.get("key_osc_address", current.key_osc_address)
            ).strip(),
            key_root_osc_address=str(
                payload.get("key_root_osc_address", current.key_root_osc_address)
            ).strip(),
            key_mode_osc_address=str(
                payload.get("key_mode_osc_address", current.key_mode_osc_address)
            ).strip(),
        )

    def gamepi_config_payload(self) -> dict[str, Any]:
        from midijuggler.web.gamepi_brightness import brightness_status_payload

        config = self.config.gamepi
        brightness = brightness_status_payload()
        return {
            "enabled": config.enabled,
            "brightness_state_path": config.brightness_state_path,
            "brightness_poll_sec": config.brightness_poll_sec,
            "kiosk_url": config.kiosk_url,
            "module_active": self._gamepi_module is not None,
            "brightness": brightness,
        }

    async def apply_gamepi_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("gamepi config payload must be an object")

        config = self._normalized_gamepi_config(payload)
        previous = self.config.gamepi
        self.config = replace(self.config, gamepi=config)

        if self._gamepi_module is not None:
            self._gamepi_module.update_config(config)

        persisted = False
        persist_error = ""
        if self.config_path is not None:
            try:
                save_gamepi_config(self.config_path, config)
                persisted = True
            except OSError as exc:
                persist_error = str(exc)
                LOGGER.warning(
                    "GamePi config applied at runtime but could not be persisted to %s: %s",
                    self.config_path,
                    exc,
                )
        else:
            persist_error = "no config path available"

        response = self.gamepi_config_payload()
        response.update(
            {
                "persisted": persisted,
                "persist_error": persist_error,
                "restart_required": (
                    config.enabled != previous.enabled
                    or config.brightness_state_path != previous.brightness_state_path
                    or config.brightness_poll_sec != previous.brightness_poll_sec
                ),
            }
        )
        return response

    def _normalized_gamepi_config(self, payload: dict[str, Any]) -> GamePiConfig:
        current = self.config.gamepi
        brightness_poll_sec = float(
            payload.get("brightness_poll_sec", current.brightness_poll_sec)
        )
        if brightness_poll_sec <= 0:
            raise ValueError("brightness_poll_sec must be positive")

        brightness_state_path = str(
            payload.get("brightness_state_path", current.brightness_state_path)
        ).strip()
        if not brightness_state_path:
            raise ValueError("brightness_state_path must not be empty")

        kiosk_url = str(payload.get("kiosk_url", current.kiosk_url)).strip()
        if not kiosk_url:
            raise ValueError("kiosk_url must not be empty")

        return GamePiConfig(
            enabled=bool(payload.get("enabled", current.enabled)),
            brightness_state_path=brightness_state_path,
            brightness_poll_sec=brightness_poll_sec,
            kiosk_url=kiosk_url,
        )

    async def apply_tap_tempo(self, timestamp: float | None = None) -> dict[str, Any]:
        now = time.monotonic() if timestamp is None else timestamp
        return await self.apply_clock_trigger("tap_tempo", timestamp=now)

    async def apply_clock_trigger(
        self,
        point: str,
        timestamp: float | None = None,
    ) -> dict[str, Any]:
        if point not in CLOCK_TRIGGER_POINTS:
            raise ValueError(f"unknown clock trigger point: {point}")
        if not self.master_clock.config.enabled:
            raise ValueError("master clock is disabled")
        now = time.monotonic() if timestamp is None else timestamp
        if self.datapoint_store is not None:
            trigger = DataPointId("clock", point)
            await self.datapoint_store.write(
                DataPointValue(
                    point_id=trigger,
                    value_type=ValueType.TRIGGER,
                    bool_value=False,
                    timestamp=now,
                )
            )
            await self.datapoint_store.write(
                DataPointValue(
                    point_id=trigger,
                    value_type=ValueType.TRIGGER,
                    bool_value=True,
                    timestamp=now,
                )
            )
        else:
            await self._apply_clock_trigger_direct(point, timestamp=now)
        payload = self._status_payload()
        if point == "tap_tempo":
            payload["tap_count"] = self.master_clock.tap_count
        await self.broadcast_status()
        return payload

    async def _apply_clock_trigger_direct(
        self,
        point: str,
        *,
        timestamp: float | None = None,
    ) -> None:
        clock = self.master_clock
        config = clock.config

        def stepped_bpm(delta: float) -> float:
            stepped = quantize_bpm(clock.bpm + delta, step=TAP_TEMPO_BPM_QUANTIZE_STEP)
            return min(max(stepped, config.bpm_min), config.bpm_max)

        if point == "bpm_up":
            await clock.handle_command(
                MasterClockCommandEvent(
                    source="clock",
                    command="set_bpm",
                    value=stepped_bpm(config.bpm_step),
                )
            )
        elif point == "bpm_down":
            await clock.handle_command(
                MasterClockCommandEvent(
                    source="clock",
                    command="set_bpm",
                    value=stepped_bpm(-config.bpm_step),
                )
            )
        elif point == "bpm_huge_up":
            await clock.handle_command(
                MasterClockCommandEvent(
                    source="clock",
                    command="set_bpm",
                    value=stepped_bpm(config.bpm_huge_step),
                )
            )
        elif point == "bpm_huge_down":
            await clock.handle_command(
                MasterClockCommandEvent(
                    source="clock",
                    command="set_bpm",
                    value=stepped_bpm(-config.bpm_huge_step),
                )
            )
        elif point == "start":
            await clock.handle_command(
                MasterClockCommandEvent(source="clock", command="start")
            )
        elif point == "stop":
            await clock.handle_command(
                MasterClockCommandEvent(source="clock", command="stop")
            )
        elif point == "start_stop":
            await clock.toggle_transport()
        elif point == "tap_tempo":
            await clock.register_tap_tempo(timestamp)
        elif point == "click_toggle":
            await clock.toggle_click_enabled()
        else:
            raise ValueError(f"unknown clock trigger point: {point}")

    async def apply_master_clock_transport(self, action: str) -> dict[str, Any]:
        if not self.master_clock.config.enabled:
            raise ValueError("master clock is disabled")
        if action == "toggle":
            await self.master_clock.toggle_transport()
        elif action == "start":
            if not self.master_clock.running:
                await self.master_clock.start_transport(reset_position=True)
        elif action == "stop":
            await self.master_clock.stop_transport()
        elif action == "continue":
            await self.master_clock.continue_transport()
        else:
            raise ValueError("action must be toggle, start, stop or continue")
        payload = self._status_payload()
        await self.broadcast_status()
        return payload

    def _midi_instance_payload(
        self,
        name: str,
        adapter: AdapterConfig,
        available_input_ports: list[dict[str, str]],
        available_output_ports: list[dict[str, str]],
    ) -> dict[str, Any]:
        kind = adapter.kind or name
        options = adapter.options
        runtime_adapter = (
            self.midi_adapters.get(name)
            if kind == "midi"
            else self.rtp_midi_adapters.get(name)
        )
        payload: dict[str, Any] = {
            "uid": name,
            "name": adapter.display_name(name),
            "type": kind,
            "enabled": adapter.enabled,
            "runtime_active": runtime_adapter is not None and runtime_adapter.running,
        }
        runtime_connection = self._adapter_runtime_connection(name)
        if runtime_connection is not None:
            payload["runtime_connection"] = runtime_connection
        if kind == "midi":
            input_port = normalize_midi_port_id(
                str(options.get("input_port", "")),
                inputs=True,
                ports=available_input_ports,
            )
            output_port = normalize_midi_port_id(
                str(options.get("output_port", "")),
                inputs=False,
                ports=available_output_ports,
            )
            input_match = lookup_midi_port(
                input_port,
                inputs=True,
                ports=available_input_ports,
            )
            output_match = lookup_midi_port(
                output_port,
                inputs=False,
                ports=available_output_ports,
            )
            payload.update(
                {
                    "input_port": input_port,
                    "output_port": output_port,
                    "resolved_input_address": (
                        input_match.get("address", "") if input_match is not None else ""
                    ),
                    "resolved_output_address": (
                        output_match.get("address", "") if output_match is not None else ""
                    ),
                    "echo_guard_ms": int(
                        options.get("echo_guard_ms", DEFAULT_ECHO_GUARD_MS)
                        or DEFAULT_ECHO_GUARD_MS
                    ),
                    **self._adapter_device_payload_fields(name),
                    "available_input_ports": self._midi_port_choices(
                        available_input_ports,
                        input_port,
                        inputs=True,
                    ),
                    "available_output_ports": self._midi_port_choices(
                        available_output_ports,
                        output_port,
                        inputs=False,
                    ),
                }
            )
        else:
            role = str(options.get("role", "host"))
            join_target = str(options.get("join_target", ""))
            joinable = (
                self.rtp_midi_manager.joinable_sessions()
                if self.rtp_midi_manager is not None
                else []
            )
            output_port = normalize_midi_port_id(
                str(options.get("output_port", "")),
                inputs=False,
                ports=available_output_ports,
            )
            output_match = lookup_midi_port(
                output_port,
                inputs=False,
                ports=available_output_ports,
            )
            payload.update(
                {
                    "role": role,
                    "session_name": str(options.get("session_name", "")),
                    "port": int(options.get("port", 5004)),
                    "join_target": join_target,
                    "output_port": output_port,
                    "resolved_output_address": (
                        output_match.get("address", "") if output_match is not None else ""
                    ),
                    "available_output_ports": self._midi_port_choices(
                        available_output_ports,
                        output_port,
                        inputs=False,
                    ),
                    "available_rtp_sessions": self._rtp_session_choices(
                        joinable,
                        join_target,
                    ),
                }
            )
        return payload

    def _rtp_session_choices(
        self,
        discovered: list[dict[str, Any]],
        selected_target: str,
    ) -> list[dict[str, str]]:
        choices = [
            {"id": session["id"], "label": session["label"]}
            for session in discovered
        ]
        if selected_target and selected_target not in {choice["id"] for choice in choices}:
            choices.append(
                {
                    "id": selected_target,
                    "label": f"{selected_target} (configured)",
                }
            )
        return choices

    def _midi_port_choices(
        self,
        ports: list[dict[str, str]],
        selected_port: str,
        *,
        inputs: bool,
    ) -> list[dict[str, str]]:
        normalized_selected = normalize_midi_port_id(
            selected_port,
            inputs=inputs,
            ports=ports,
        )
        port_ids = {port["id"] for port in ports}
        choices = [enrich_midi_port_choice(port) for port in ports]
        if normalized_selected and normalized_selected not in port_ids:
            matched = lookup_midi_port(
                normalized_selected,
                inputs=inputs,
                ports=ports,
            )
            label = f"{normalized_selected} (configured)"
            if matched is not None:
                label = (
                    f"{matched.get('client', matched['id'])} / {matched['id']} "
                    f"(current {matched.get('address', '')})"
                )
            choices.append(
                enrich_midi_port_choice(
                    {
                        "id": normalized_selected,
                        "label": label,
                        "client": matched.get("client", "") if matched is not None else "",
                        "address": matched.get("address", "") if matched is not None else "",
                    }
                )
            )
        return choices

    def _normalized_midi_options(
        self,
        payload: dict[str, Any],
        current: dict[str, Any],
        *,
        adapter_name: str = "",
    ) -> dict[str, Any]:
        available_input_ports = list_midi_input_ports()
        available_output_ports = list_midi_output_ports()
        midi_library = self._resolved_midi_library_id(adapter_name, payload, current)
        options = {
            "input_port": normalize_midi_port_id(
                str(payload.get("input_port", current.get("input_port", ""))).strip(),
                inputs=True,
                ports=available_input_ports,
            ),
            "output_port": normalize_midi_port_id(
                str(payload.get("output_port", current.get("output_port", ""))).strip(),
                inputs=False,
                ports=available_output_ports,
            ),
        }
        if midi_library:
            known_libraries = {library.id for library in list_midi_libraries()}
            if midi_library not in known_libraries:
                raise ValueError(f"unknown MIDI library: {midi_library}")
        options["echo_guard_ms"] = parse_echo_guard_ms(
            payload.get("echo_guard_ms", current.get("echo_guard_ms", DEFAULT_ECHO_GUARD_MS))
        )
        return options

    def _normalized_rtp_midi_options(
        self,
        payload: dict[str, Any],
        current: dict[str, Any],
        *,
        enabled: bool,
    ) -> dict[str, Any]:
        from midijuggler.rtp_midi.manager import RTP_ROLES

        role = str(payload.get("role", current.get("role", "host"))).strip().lower()
        if role not in RTP_ROLES:
            raise ValueError("rtp_midi role must be host, listen, or join")

        port = int(payload.get("port", current.get("port", 5004)))
        if not 1 <= port <= 65535:
            raise ValueError("rtp_midi port must be between 1 and 65535")

        session_name = str(
            payload.get("session_name", current.get("session_name", ""))
        ).strip()
        join_target = str(payload.get("join_target", current.get("join_target", ""))).strip()
        output_port = normalize_midi_port_id(
            str(payload.get("output_port", current.get("output_port", ""))).strip(),
            inputs=False,
            ports=list_midi_output_ports(),
        )

        if role in {"host", "listen"}:
            if enabled and not session_name:
                raise ValueError(
                    "rtp_midi session_name must not be empty in host or listen mode"
                )
            return {
                "role": role,
                "session_name": session_name,
                "port": port,
                "output_port": output_port,
            }

        if enabled and not join_target:
            raise ValueError("rtp_midi join_target must be selected in join mode")

        discovered_ids = {
            session["id"]
            for session in (
                self.rtp_midi_manager.discovered_sessions()
                if self.rtp_midi_manager is not None
                else []
            )
        }
        current_target = str(current.get("join_target", "")).strip()
        if (
            join_target
            and join_target not in discovered_ids
            and join_target != current_target
        ):
            raise ValueError(f"unknown discovered RTP-MIDI session: {join_target}")

        return {
            "role": role,
            "join_target": join_target,
            "port": port,
            "output_port": output_port,
        }

    def _gpio_options(self) -> dict[str, Any]:
        if self.gpio_adapter is not None:
            return self.gpio_adapter.config_payload()
        raw_options = self.config.adapters["gpio"].options
        return {
            "pins": [int(pin) for pin in raw_options.get("pins", [])],
            "active_low": bool(raw_options.get("active_low", True)),
            "bounce_ms": int(float(raw_options.get("bounce_ms", 25))),
            "poll_interval_ms": int(float(raw_options.get("poll_interval_ms", 5))),
        }

    def _normalized_gpio_options(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed_pins = set(RASPBERRY_PI_HEADER_BCM_PINS)
        raw_pins = payload.get("pins")
        if not isinstance(raw_pins, list):
            raise ValueError("GPIO config requires a pins list")
        pins = sorted({int(pin) for pin in raw_pins})
        invalid_pins = [pin for pin in pins if pin not in allowed_pins]
        if invalid_pins:
            raise ValueError(f"unsupported BCM GPIO pins: {invalid_pins}")
        if not pins:
            raise ValueError("at least one GPIO pin must be enabled")

        current = self._gpio_options()
        return {
            "pins": pins,
            "active_low": bool(payload.get("active_low", current["active_low"])),
            "bounce_ms": int(float(payload.get("bounce_ms", current["bounce_ms"]))),
            "poll_interval_ms": int(
                float(payload.get("poll_interval_ms", current["poll_interval_ms"]))
            ),
        }

    def _normalized_master_clock_config(self, payload: dict[str, Any]) -> MasterClockConfig:
        current = self.master_clock.config
        datapoint_routing = self.config.runtime.datapoint_routing
        available_targets = {
            name
            for name, adapter in self.config.adapters.items()
            if adapter.enabled and (adapter.kind or name) in {"midi", "rtp_midi"}
        }
        raw_targets = payload.get("output_targets", current.output_targets)
        if not isinstance(raw_targets, list):
            raise ValueError("Master clock output_targets must be a list")
        output_targets = [str(target) for target in raw_targets]
        unknown_targets = [target for target in output_targets if target not in available_targets]
        if unknown_targets:
            raise ValueError(f"unknown MIDI clock output targets: {unknown_targets}")

        if datapoint_routing:
            midi_input_targets: list[str] | None = []
            osc_input_targets: list[str] | None = []
            bpm_osc_address = current.bpm_osc_address
            click_interval_osc_address = current.click_interval_osc_address
            bpm_msb_cc = current.bpm_msb_cc
            bpm_lsb_cc = current.bpm_lsb_cc
            click_interval_cc = current.click_interval_cc
            midi_channel = current.midi_channel
        else:
            midi_input_targets = self._normalized_input_targets(
                payload,
                "midi_input_targets",
                current.midi_input_targets,
                {"midi", "rtp_midi"},
            )
            osc_input_targets = self._normalized_input_targets(
                payload,
                "osc_input_targets",
                current.osc_input_targets,
                {"osc"},
            )
            bpm_osc_address = str(payload.get("bpm_osc_address", current.bpm_osc_address))
            click_interval_osc_address = str(
                payload.get(
                    "click_interval_osc_address",
                    current.click_interval_osc_address,
                )
            )
            bpm_msb_cc = _validate_midi_7bit(
                payload.get("bpm_msb_cc", current.bpm_msb_cc),
                "bpm_msb_cc",
            )
            bpm_lsb_cc = _validate_midi_7bit(
                payload.get("bpm_lsb_cc", current.bpm_lsb_cc),
                "bpm_lsb_cc",
            )
            click_interval_cc = _validate_midi_7bit(
                payload.get("click_interval_cc", current.click_interval_cc),
                "click_interval_cc",
            )
            midi_channel = int(payload.get("midi_channel", current.midi_channel))
            if not 1 <= midi_channel <= 16:
                raise ValueError("midi_channel must be between 1 and 16")

        click_interval = str(payload.get("click_interval", current.click_interval))
        if click_interval not in CLICK_INTERVALS:
            raise ValueError(
                "click_interval must be " + ", ".join(CLICK_INTERVALS)
            )

        bpm_min = float(payload.get("bpm_min", current.bpm_min))
        bpm_max = float(payload.get("bpm_max", current.bpm_max))
        bpm = float(payload.get("bpm", current.bpm))
        if bpm_min <= 0 or bpm_max <= 0 or bpm_min >= bpm_max:
            raise ValueError("bpm_min/bpm_max must be positive and ordered")
        if not bpm_min <= bpm <= bpm_max:
            raise ValueError("bpm must be inside bpm_min/bpm_max")

        tap_tempo_min_taps = _validate_tap_tempo_min_taps(
            payload.get("tap_tempo_min_taps", current.tap_tempo_min_taps),
            "tap_tempo_min_taps",
        )
        bpm_step = _validate_bpm_step(
            payload.get("bpm_step", current.bpm_step),
            "bpm_step",
        )
        bpm_huge_step = _validate_bpm_step(
            payload.get("bpm_huge_step", current.bpm_huge_step),
            "bpm_huge_step",
        )
        beat_flash_ms = _validate_beat_flash_ms(
            payload.get("beat_flash_ms", current.beat_flash_ms),
            "beat_flash_ms",
        )
        display_name = validate_device_name(
            str(payload.get("name", current.name)),
            field_name="name",
        )

        return MasterClockConfig(
            enabled=bool(payload.get("enabled", current.enabled)),
            bpm=bpm,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            auto_start=bool(payload.get("auto_start", current.auto_start)),
            output_targets=output_targets,
            midi_input_targets=midi_input_targets,
            osc_input_targets=osc_input_targets,
            send_transport=bool(payload.get("send_transport", current.send_transport)),
            bpm_osc_address=bpm_osc_address,
            click_interval_osc_address=click_interval_osc_address,
            bpm_msb_cc=bpm_msb_cc,
            bpm_lsb_cc=bpm_lsb_cc,
            click_interval_cc=click_interval_cc,
            midi_channel=midi_channel,
            click_enabled=bool(payload.get("click_enabled", current.click_enabled)),
            click_wav=str(payload.get("click_wav", current.click_wav)),
            click_interval=click_interval,
            click_command="aplay",
            click_audio_device=normalize_alsa_output_device(
                str(payload.get("click_audio_device", current.click_audio_device)),
            ),
            tap_tempo_min_taps=tap_tempo_min_taps,
            bpm_step=bpm_step,
            bpm_huge_step=bpm_huge_step,
            name=display_name,
            beat_flash_ms=beat_flash_ms,
        )

    def _available_adapter_targets(
        self,
        kinds: set[str],
        selected: set[str] | None,
        *,
        require_enabled_for_selection: bool,
    ) -> list[dict[str, Any]]:
        targets: list[dict[str, Any]] = []
        for name, adapter in self.config.adapters.items():
            adapter_kind = adapter.kind or name
            if adapter_kind not in kinds:
                continue
            if selected is None:
                is_selected = adapter.enabled
            else:
                is_selected = name in selected
            if require_enabled_for_selection:
                is_selected = adapter.enabled and is_selected
            targets.append(
                {
                    "name": name,
                    "type": adapter_kind,
                    "enabled": adapter.enabled,
                    "selected": is_selected,
                }
            )
        return targets

    def _normalized_input_targets(
        self,
        payload: dict[str, Any],
        field_name: str,
        current: list[str] | None,
        kinds: set[str],
    ) -> list[str] | None:
        if field_name not in payload:
            return current

        raw_targets = payload[field_name]
        if raw_targets is None:
            return None
        if not isinstance(raw_targets, list):
            raise ValueError(f"Master clock {field_name} must be a list")

        available_targets = {
            name
            for name, adapter in self.config.adapters.items()
            if adapter.enabled and (adapter.kind or name) in kinds
        }
        input_targets = [str(target) for target in raw_targets]
        unknown_targets = [target for target in input_targets if target not in available_targets]
        if unknown_targets:
            raise ValueError(f"unknown master clock {field_name}: {unknown_targets}")
        return input_targets

    def _resolved_audio_device(self, selected_device: str) -> str:
        matched = lookup_alsa_output_device(selected_device)
        if matched is None:
            return ""
        return str(matched.get("resolved_device", ""))

    def _audio_devices(self, selected_device: str) -> list[dict[str, str]]:
        devices = list_alsa_output_devices()
        normalized_selected = normalize_alsa_output_device(
            selected_device,
            devices=devices,
        )
        ids = {device["id"] for device in devices}
        if normalized_selected and normalized_selected not in ids:
            matched = lookup_alsa_output_device(normalized_selected, devices=devices)
            label = f"{normalized_selected} (configured)"
            if matched is not None:
                label = (
                    f"{matched.get('card_name', normalized_selected)} / "
                    f"{matched.get('device_name', '')} "
                    f"(current {matched.get('resolved_device', '')})"
                ).strip()
            devices.append(
                {
                    "id": normalized_selected,
                    "label": label,
                    "mode": matched.get("mode", "dmix") if matched is not None else "dmix",
                    "resolved_device": (
                        matched.get("resolved_device", "") if matched is not None else ""
                    ),
                }
            )
        return devices

    def _click_wavs(self, selected_wav: str) -> list[dict[str, str]]:
        wavs = list_click_wavs()
        paths = {wav["path"] for wav in wavs}
        if selected_wav and selected_wav not in paths:
            wavs.append({"path": selected_wav, "label": f"{Path(selected_wav).name} (configured)"})
        return wavs


def _validate_midi_7bit(value: Any, field_name: str) -> int:
    parsed = int(value)
    if not 0 <= parsed <= 127:
        raise ValueError(f"{field_name} must be between 0 and 127")
    return parsed


class _QuietAccessPathsFilter(logging.Filter):
    """Drop high-frequency status/brightness access logs."""

    _QUIET_PREFIXES = (
        '"GET /api/status ',
        '"GET /api/gamepi/brightness ',
        '"POST /api/gamepi/brightness ',
        '"POST /api/gamepi/brightness/refresh ',
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(prefix in message for prefix in self._QUIET_PREFIXES)


def _configure_access_logging() -> logging.Logger:
    access_logger = logging.getLogger("aiohttp.access")
    if not any(isinstance(item, _QuietAccessPathsFilter) for item in access_logger.filters):
        access_logger.addFilter(_QuietAccessPathsFilter())
    return access_logger


async def run_web_server(interface: WebInterface) -> web.AppRunner:
    app = interface.create_app()
    runner = web.AppRunner(app, access_log=_configure_access_logging())
    await runner.setup()
    site = web.TCPSite(runner, interface.config.web.host, interface.config.web.port)
    await site.start()
    return runner


async def stop_web_server(runner: web.AppRunner) -> None:
    await asyncio.shield(runner.cleanup())
