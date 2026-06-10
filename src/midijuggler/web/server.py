"""aiohttp web interface for monitoring MIDIJuggler."""

from __future__ import annotations

import asyncio
import json
import mimetypes
from importlib import resources
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web

from midijuggler.adapters.gpio import GpioAdapter, RASPBERRY_PI_HEADER_BCM_PINS
from midijuggler.clock import ClockBpmTracker
from midijuggler.config import AppConfig, save_gpio_adapter_options
from midijuggler.eventbus import EventBus
from midijuggler.events import Event
from midijuggler.midi_library import get_midi_library, list_midi_libraries
from midijuggler.master_clock import MasterClock
from midijuggler.osc_library import get_osc_library, list_osc_libraries


class WebInterface:
    """HTTP API, static UI and WebSocket event monitor."""

    def __init__(
        self,
        config: AppConfig,
        bus: EventBus,
        clock: ClockBpmTracker,
        master_clock: MasterClock,
        gpio_adapter: GpioAdapter | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        self.config = config
        self.bus = bus
        self.clock = clock
        self.master_clock = master_clock
        self.gpio_adapter = gpio_adapter
        self.config_path = Path(config_path) if config_path is not None else None
        self.learn_mode = False
        self._websockets: set[web.WebSocketResponse] = set()
        self.bus.subscribe("*", self._broadcast_event)

    def create_app(self) -> web.Application:
        app = web.Application()
        app["web_interface"] = self
        app.router.add_get("/", self.index)
        app.router.add_get("/static/{filename}", self.static_asset)
        app.router.add_get("/api/status", self.status)
        app.router.add_get("/api/gpio", self.gpio_config)
        app.router.add_post("/api/gpio", self.set_gpio_config)
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

    async def gpio_config(self, request: web.Request) -> web.Response:
        return web.json_response(self.gpio_config_payload())

    async def set_gpio_config(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            response = await self.apply_gpio_config(payload)
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
                "enabled": self.config.master_clock.enabled,
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

        if self.gpio_adapter is not None:
            await self.gpio_adapter.configure_options(options)
        else:
            self.config.adapters["gpio"].options.clear()
            self.config.adapters["gpio"].options.update(options)

        if self.config_path is not None:
            save_gpio_adapter_options(self.config_path, options)

        return self.gpio_config_payload()

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


async def run_web_server(interface: WebInterface) -> web.AppRunner:
    app = interface.create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, interface.config.web.host, interface.config.web.port)
    await site.start()
    return runner


async def stop_web_server(runner: web.AppRunner) -> None:
    await asyncio.shield(runner.cleanup())
