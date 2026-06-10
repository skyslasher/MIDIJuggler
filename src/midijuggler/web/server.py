"""aiohttp web interface for monitoring MIDIJuggler."""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import time
import tomllib
from importlib import resources
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web

from midijuggler.adapters.gpio import GpioAdapter, RASPBERRY_PI_HEADER_BCM_PINS
from midijuggler.alsa import write_master_clock_pcm_config
from midijuggler.clock import ClockBpmTracker
from midijuggler.config import (
    AdapterConfig,
    AppConfig,
    MasterClockConfig,
    parse_config,
    save_gpio_adapter_options,
    save_master_clock_config,
    save_midi_adapter_configs,
)
from midijuggler.eventbus import EventBus
from midijuggler.events import Event
from midijuggler.midi_library import get_midi_library, list_midi_libraries
from midijuggler.master_clock import MasterClock
from midijuggler.rtp_midi.manager import RtpMidiManager
from midijuggler.osc_library import get_osc_library, list_osc_libraries
from midijuggler.system_info import (
    list_alsa_output_devices,
    list_click_wavs,
    list_midi_ports,
)

LOGGER = logging.getLogger(__name__)


class WebInterface:
    """HTTP API, static UI and WebSocket event monitor."""

    def __init__(
        self,
        config: AppConfig,
        bus: EventBus,
        clock: ClockBpmTracker,
        master_clock: MasterClock,
        gpio_adapter: GpioAdapter | None = None,
        rtp_midi_manager: RtpMidiManager | None = None,
        config_path: str | Path | None = None,
        alsa_config_path: str | Path | None = None,
    ) -> None:
        self.config = config
        self.bus = bus
        self.clock = clock
        self.master_clock = master_clock
        self.gpio_adapter = gpio_adapter
        self.rtp_midi_manager = rtp_midi_manager
        self.config_path = Path(config_path) if config_path is not None else None
        self.alsa_config_path = (
            Path(alsa_config_path) if alsa_config_path is not None else None
        )
        self.learn_mode = False
        self._tap_times: list[float] = []
        self._websockets: set[web.WebSocketResponse] = set()
        self.bus.subscribe("*", self._broadcast_event)

    def create_app(self) -> web.Application:
        app = web.Application()
        app["web_interface"] = self
        app.router.add_get("/", self.index)
        app.router.add_get("/static/{filename}", self.static_asset)
        app.router.add_get("/api/status", self.status)
        app.router.add_get("/api/config/export", self.export_config)
        app.router.add_post("/api/config/import", self.import_config)
        app.router.add_get("/api/gpio", self.gpio_config)
        app.router.add_post("/api/gpio", self.set_gpio_config)
        app.router.add_get("/api/midi-adapters", self.midi_adapters_config)
        app.router.add_post("/api/midi-adapters", self.set_midi_adapters_config)
        app.router.add_get("/api/master-clock", self.master_clock_config)
        app.router.add_post("/api/master-clock", self.set_master_clock_config)
        app.router.add_post("/api/master-clock/tap", self.tap_master_clock)
        app.router.add_post("/api/master-clock/transport", self.master_clock_transport)
        app.router.add_get("/api/midi-libraries", self.midi_libraries)
        app.router.add_get("/api/midi-libraries/{library_id}", self.midi_library)
        app.router.add_get("/api/osc-libraries", self.osc_libraries)
        app.router.add_get("/api/osc-libraries/{library_id}", self.osc_library)
        app.router.add_post("/api/learn", self.set_learn_mode)
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

    async def status(self, request: web.Request) -> web.Response:
        return web.json_response(self._status_payload())

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
        parse_config(tomllib.loads(content))
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

    async def midi_adapters_config(self, request: web.Request) -> web.Response:
        return web.json_response(self.midi_adapters_config_payload())

    async def set_midi_adapters_config(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            response = await self.apply_midi_adapters_config(payload)
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
        self.learn_mode = bool(payload.get("enabled", False))
        return web.json_response(self._status_payload())

    async def monitor_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        self._websockets.add(ws)
        await ws.send_json({"type": "status", "payload": self._status_payload()})
        for event in self.bus.history_dicts():
            await ws.send_json({"type": "event", "payload": event})

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
            self.learn_mode = bool(payload.get("enabled", False))
            await self._broadcast_payload({"type": "status", "payload": self._status_payload()})

    async def _broadcast_event(self, event: Event) -> None:
        await self._broadcast_payload({"type": "event", "payload": event.as_dict()})

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
            "bpm": self.clock.bpm,
            "master_clock": {
                "enabled": self.master_clock.config.enabled,
                "bpm": self.master_clock.bpm,
                "running": self.master_clock.running,
                "position_ticks": self.master_clock.position_ticks,
                "click_interval": self.master_clock.click_interval,
                "parameters": self.master_clock.parameters.as_controls(),
            },
            "learn_mode": self.learn_mode,
            "mappings": [rule.__dict__ for rule in self.config.mappings],
            "adapters": {
                name: {
                    "type": adapter.kind or name,
                    "enabled": adapter.enabled,
                    "options": adapter.options,
                }
                for name, adapter in self.config.adapters.items()
            },
        }

    def gpio_config_payload(self) -> dict[str, Any]:
        options = self._gpio_options()
        configured_pins = set(options["pins"])
        return {
            "enabled": self.config.adapters["gpio"].enabled,
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
        persisted = False
        persist_error = ""

        if self.gpio_adapter is not None:
            await self.gpio_adapter.configure_options(options)
        else:
            self.config.adapters["gpio"].options.clear()
            self.config.adapters["gpio"].options.update(options)

        if self.config_path is not None:
            try:
                save_gpio_adapter_options(self.config_path, options)
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

    def midi_adapters_config_payload(self) -> dict[str, Any]:
        available_ports = list_midi_ports()
        port_ids = {port["id"] for port in available_ports}
        libraries = list_midi_libraries()
        discovered_sessions = (
            self.rtp_midi_manager.discovered_sessions()
            if self.rtp_midi_manager is not None
            else []
        )
        return {
            "available_ports": available_ports,
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
            "instances": [
                self._midi_instance_payload(name, adapter, port_ids)
                for name, adapter in sorted(self.config.adapters.items())
                if (adapter.kind or name) in {"usb_midi", "rtp_midi"}
            ],
        }

    async def apply_midi_adapters_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("MIDI adapter config payload must be an object")

        raw_instances = payload.get("instances")
        if not isinstance(raw_instances, list):
            raise ValueError("MIDI adapter config requires an instances list")

        updates: dict[str, AdapterConfig] = {}
        for raw_instance in raw_instances:
            if not isinstance(raw_instance, dict):
                raise ValueError("each MIDI adapter instance must be an object")
            name = str(raw_instance.get("name", "")).strip()
            if not name:
                raise ValueError("each MIDI adapter instance requires a name")
            if name not in self.config.adapters:
                raise ValueError(f"unknown MIDI adapter instance: {name}")

            current = self.config.adapters[name]
            kind = current.kind or name
            if kind not in {"usb_midi", "rtp_midi"}:
                raise ValueError(f"adapter {name} is not a MIDI adapter")

            enabled = bool(raw_instance.get("enabled", current.enabled))
            if kind == "usb_midi":
                options = self._normalized_usb_midi_options(raw_instance, current.options)
            else:
                options = self._normalized_rtp_midi_options(
                    raw_instance,
                    current.options,
                    enabled=enabled,
                )

            updated = AdapterConfig(enabled=enabled, options=options, kind=kind)
            updates[name] = updated
            self.config.adapters[name] = updated

        persisted = False
        persist_error = ""
        if self.config_path is not None and updates:
            try:
                save_midi_adapter_configs(self.config_path, updates)
                persisted = True
            except OSError as exc:
                persist_error = str(exc)
                LOGGER.warning(
                    "MIDI adapter config applied at runtime but could not be persisted to %s: %s",
                    self.config_path,
                    exc,
                )
        elif self.config_path is None:
            persist_error = "no config path available"

        if self.rtp_midi_manager is not None:
            await self.rtp_midi_manager.start()
            for name, updated in updates.items():
                if updated.kind == "rtp_midi":
                    await self.rtp_midi_manager.apply_instance(name, updated)

        response = self.midi_adapters_config_payload()
        response.update({"persisted": persisted, "persist_error": persist_error})
        return response

    def master_clock_config_payload(self) -> dict[str, Any]:
        config = self.master_clock.config
        selected_outputs = set(config.output_targets)
        selected_midi_inputs = (
            None if config.midi_input_targets is None else set(config.midi_input_targets)
        )
        selected_osc_inputs = (
            None if config.osc_input_targets is None else set(config.osc_input_targets)
        )
        return {
            "enabled": config.enabled,
            "bpm": config.bpm,
            "bpm_min": config.bpm_min,
            "bpm_max": config.bpm_max,
            "auto_start": config.auto_start,
            "output_targets": config.output_targets,
            "midi_input_targets": config.midi_input_targets,
            "osc_input_targets": config.osc_input_targets,
            "available_output_targets": self._available_adapter_targets(
                {"usb_midi", "rtp_midi"},
                selected_outputs,
                require_enabled_for_selection=True,
            ),
            "available_midi_input_targets": self._available_adapter_targets(
                {"usb_midi", "rtp_midi"},
                selected_midi_inputs,
                require_enabled_for_selection=False,
            ),
            "available_osc_input_targets": self._available_adapter_targets(
                {"osc"},
                selected_osc_inputs,
                require_enabled_for_selection=False,
            ),
            "send_transport": config.send_transport,
            "bpm_osc_address": config.bpm_osc_address,
            "click_interval_osc_address": config.click_interval_osc_address,
            "bpm_msb_cc": config.bpm_msb_cc,
            "bpm_lsb_cc": config.bpm_lsb_cc,
            "click_interval_cc": config.click_interval_cc,
            "midi_channel": config.midi_channel,
            "click_enabled": config.click_enabled,
            "click_wav": config.click_wav,
            "click_interval": config.click_interval,
            "click_audio_device": config.click_audio_device,
            "available_audio_devices": self._audio_devices(config.click_audio_device),
            "available_click_wavs": self._click_wavs(config.click_wav),
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
                    config.click_audio_device,
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
                save_master_clock_config(self.config_path, config)
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
        return response

    async def apply_tap_tempo(self, timestamp: float | None = None) -> dict[str, Any]:
        now = time.monotonic() if timestamp is None else timestamp
        if self._tap_times and now - self._tap_times[-1] > 2.5:
            self._tap_times.clear()
        self._tap_times.append(now)
        self._tap_times = self._tap_times[-5:]

        if len(self._tap_times) >= 2:
            intervals = [
                later - earlier
                for earlier, later in zip(self._tap_times, self._tap_times[1:])
                if later > earlier
            ]
            if intervals:
                bpm = _quantize_bpm(60.0 / (sum(intervals) / len(intervals)))
                await self.master_clock.set_bpm(
                    min(
                        max(bpm, self.master_clock.config.bpm_min),
                        self.master_clock.config.bpm_max,
                    )
                )

        payload = self._status_payload()
        payload["tap_count"] = len(self._tap_times)
        return payload

    async def apply_master_clock_transport(self, action: str) -> dict[str, Any]:
        if not self.master_clock.config.enabled:
            raise ValueError("master clock is disabled")
        if action == "toggle":
            action = "stop" if self.master_clock.running else "start"
        if action == "start":
            await self.master_clock.start_transport(reset_position=True)
        elif action == "stop":
            await self.master_clock.stop_transport()
        elif action == "continue":
            await self.master_clock.continue_transport()
        else:
            raise ValueError("action must be toggle, start, stop or continue")
        return self._status_payload()

    def _midi_instance_payload(
        self,
        name: str,
        adapter: AdapterConfig,
        port_ids: set[str],
    ) -> dict[str, Any]:
        kind = adapter.kind or name
        options = adapter.options
        payload: dict[str, Any] = {
            "name": name,
            "type": kind,
            "enabled": adapter.enabled,
            "runtime_active": False,
        }
        if kind == "usb_midi":
            input_port = str(options.get("input_port", ""))
            output_port = str(options.get("output_port", ""))
            payload.update(
                {
                    "input_port": input_port,
                    "output_port": output_port,
                    "midi_library": str(options.get("midi_library", "")),
                    "available_input_ports": self._midi_port_choices(
                        port_ids,
                        input_port,
                    ),
                    "available_output_ports": self._midi_port_choices(
                        port_ids,
                        output_port,
                    ),
                }
            )
        else:
            role = str(options.get("role", "host"))
            join_target = str(options.get("join_target", ""))
            discovered = (
                self.rtp_midi_manager.discovered_sessions()
                if self.rtp_midi_manager is not None
                else []
            )
            payload.update(
                {
                    "role": role,
                    "session_name": str(options.get("session_name", "")),
                    "port": int(options.get("port", 5004)),
                    "join_target": join_target,
                    "available_rtp_sessions": self._rtp_session_choices(
                        discovered,
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
        port_ids: set[str],
        selected_port: str,
    ) -> list[dict[str, str]]:
        ports = list_midi_ports()
        choices = list(ports)
        if selected_port and selected_port not in port_ids:
            choices.append(
                {
                    "id": selected_port,
                    "label": f"{selected_port} (configured)",
                    "client": "",
                }
            )
        return choices

    def _normalized_usb_midi_options(
        self,
        payload: dict[str, Any],
        current: dict[str, Any],
    ) -> dict[str, Any]:
        midi_library = str(payload.get("midi_library", current.get("midi_library", ""))).strip()
        options = {
            "input_port": str(payload.get("input_port", current.get("input_port", ""))).strip(),
            "output_port": str(
                payload.get("output_port", current.get("output_port", ""))
            ).strip(),
        }
        if midi_library:
            known_libraries = {library.id for library in list_midi_libraries()}
            if midi_library not in known_libraries:
                raise ValueError(f"unknown MIDI library: {midi_library}")
            options["midi_library"] = midi_library
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
            raise ValueError("rtp_midi role must be host or join")

        port = int(payload.get("port", current.get("port", 5004)))
        if not 1 <= port <= 65535:
            raise ValueError("rtp_midi port must be between 1 and 65535")

        session_name = str(
            payload.get("session_name", current.get("session_name", ""))
        ).strip()
        join_target = str(payload.get("join_target", current.get("join_target", ""))).strip()

        if role == "host":
            if enabled and not session_name:
                raise ValueError("rtp_midi session_name must not be empty in host mode")
            return {"role": role, "session_name": session_name, "port": port}

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

        return {"role": role, "join_target": join_target, "port": port}

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
        available_targets = {
            name
            for name, adapter in self.config.adapters.items()
            if adapter.enabled and (adapter.kind or name) in {"usb_midi", "rtp_midi"}
        }
        raw_targets = payload.get("output_targets", current.output_targets)
        if not isinstance(raw_targets, list):
            raise ValueError("Master clock output_targets must be a list")
        output_targets = [str(target) for target in raw_targets]
        unknown_targets = [target for target in output_targets if target not in available_targets]
        if unknown_targets:
            raise ValueError(f"unknown MIDI clock output targets: {unknown_targets}")

        midi_input_targets = self._normalized_input_targets(
            payload,
            "midi_input_targets",
            current.midi_input_targets,
            {"usb_midi", "rtp_midi"},
        )
        osc_input_targets = self._normalized_input_targets(
            payload,
            "osc_input_targets",
            current.osc_input_targets,
            {"osc"},
        )

        click_interval = str(payload.get("click_interval", current.click_interval))
        if click_interval not in {"eighth", "quarter", "half", "whole"}:
            raise ValueError("click_interval must be eighth, quarter, half or whole")

        bpm_min = float(payload.get("bpm_min", current.bpm_min))
        bpm_max = float(payload.get("bpm_max", current.bpm_max))
        bpm = float(payload.get("bpm", current.bpm))
        if bpm_min <= 0 or bpm_max <= 0 or bpm_min >= bpm_max:
            raise ValueError("bpm_min/bpm_max must be positive and ordered")
        if not bpm_min <= bpm <= bpm_max:
            raise ValueError("bpm must be inside bpm_min/bpm_max")

        bpm_msb_cc = _validate_midi_7bit(payload.get("bpm_msb_cc", current.bpm_msb_cc), "bpm_msb_cc")
        bpm_lsb_cc = _validate_midi_7bit(payload.get("bpm_lsb_cc", current.bpm_lsb_cc), "bpm_lsb_cc")
        click_interval_cc = _validate_midi_7bit(
            payload.get("click_interval_cc", current.click_interval_cc),
            "click_interval_cc",
        )
        midi_channel = int(payload.get("midi_channel", current.midi_channel))
        if not 1 <= midi_channel <= 16:
            raise ValueError("midi_channel must be between 1 and 16")

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
            bpm_osc_address=str(payload.get("bpm_osc_address", current.bpm_osc_address)),
            click_interval_osc_address=str(
                payload.get(
                    "click_interval_osc_address",
                    current.click_interval_osc_address,
                )
            ),
            bpm_msb_cc=bpm_msb_cc,
            bpm_lsb_cc=bpm_lsb_cc,
            click_interval_cc=click_interval_cc,
            midi_channel=midi_channel,
            click_enabled=bool(payload.get("click_enabled", current.click_enabled)),
            click_wav=str(payload.get("click_wav", current.click_wav)),
            click_interval=click_interval,
            click_command="aplay",
            click_audio_device=str(payload.get("click_audio_device", current.click_audio_device)),
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

    def _audio_devices(self, selected_device: str) -> list[dict[str, str]]:
        devices = list_alsa_output_devices()
        ids = {device["id"] for device in devices}
        if selected_device and selected_device not in ids:
            devices.append({"id": selected_device, "label": f"{selected_device} (configured)"})
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


def _quantize_bpm(bpm: float, step: float = 0.5) -> float:
    return round(bpm / step) * step


async def run_web_server(interface: WebInterface) -> web.AppRunner:
    app = interface.create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, interface.config.web.host, interface.config.web.port)
    await site.start()
    return runner


async def stop_web_server(runner: web.AppRunner) -> None:
    await asyncio.shield(runner.cleanup())
