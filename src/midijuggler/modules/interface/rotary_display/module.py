"""Rotary display feedback and USB-serial command ingress."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
from typing import Any

from midijuggler.config import RotaryDisplayConfig
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import DataPointId, DataPointValue
from midijuggler.eventbus import EventBus
from midijuggler.events import MasterClockCommandEvent, OscMessageEvent
from midijuggler.master_clock import MasterClock
from midijuggler.modules.base import InterfaceModule
from midijuggler.modules.interface.rotary_display.protocol import (
    RotarySyncState,
    format_beat_line,
    format_sync_line,
    parse_hello_osc,
    parse_serial_line,
    serial_command_to_clock_event,
)
from midijuggler.osc.protocol import encode_message

LOGGER = logging.getLogger(__name__)

ROTARY_MODULE = "rotary_display"


class RotaryDisplayModule(InterfaceModule):
    """Push clock sync/beat to a rotary display over OSC and/or USB serial."""

    def __init__(
        self,
        store: DataPointStore,
        config: RotaryDisplayConfig,
        master_clock: MasterClock,
        bus: EventBus,
    ) -> None:
        super().__init__(ROTARY_MODULE, store)
        self.config = config
        self.master_clock = master_clock
        self.bus = bus
        self._feedback_host = config.feedback_host
        self._feedback_port = config.feedback_port
        self._serial_connected = False
        self._serial_port: Any | None = None
        self._serial_task: asyncio.Task[None] | None = None
        self._last_sync: RotarySyncState | None = None
        self._last_beat: float | None = None
        self._use_osc = config.transport in {"osc", "both"}
        self._use_serial = config.transport in {"serial", "both"}

    def datapoints(self) -> list:
        return []

    async def start(self) -> None:
        await super().start()
        self.store.subscribe(DataPointId("clock", "beat"), self._on_beat)
        self.store.subscribe(DataPointId("clock", "bpm"), self._on_clock_state)
        self.store.subscribe(DataPointId("clock", "running"), self._on_clock_state)
        self.store.subscribe(DataPointId("clock", "click_enabled"), self._on_clock_state)
        self.bus.subscribe(OscMessageEvent, self._on_osc_message)
        if self._use_serial and self.config.serial_port:
            self._serial_task = asyncio.create_task(self._serial_loop())
        elif self._use_serial and not self.config.serial_port:
            LOGGER.error(
                "rotary_display serial transport enabled but serial_port is empty; "
                "set serial_port in config (macOS: /dev/cu.usbmodem*)"
            )

    async def stop(self) -> None:
        if self._serial_task is not None:
            self._serial_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._serial_task
            self._serial_task = None
        if self._serial_port is not None:
            with contextlib.suppress(Exception):
                self._serial_port.close()
            self._serial_port = None
        await super().stop()

    async def _on_osc_message(self, event: OscMessageEvent) -> None:
        if event.direction != "input":
            return
        if event.address != self.config.hello_osc_address:
            return
        parsed = parse_hello_osc(tuple(event.arguments))
        if parsed is None:
            LOGGER.warning("ignored rotary hello with invalid arguments: %s", event.arguments)
            return
        self._feedback_host, self._feedback_port = parsed
        LOGGER.info(
            "rotary display registered at %s:%s",
            self._feedback_host,
            self._feedback_port,
        )
        await self._send_sync(force=True)

    async def _on_beat(self, value: DataPointValue) -> None:
        if value.float_value is None:
            return
        beat = float(value.float_value)
        if self._last_beat is not None and abs(self._last_beat - beat) <= 1e-6:
            return
        self._last_beat = beat
        await self._send_beat(beat)

    async def _on_clock_state(self, _value: DataPointValue) -> None:
        await self._send_sync()

    def _current_sync_state(self) -> RotarySyncState:
        return RotarySyncState(
            bpm=self.master_clock.bpm,
            running=self.master_clock.running,
            click_enabled=self.master_clock.config.click_enabled,
            click_interval=self.master_clock.click_interval,
        )

    async def _send_sync(self, *, force: bool = False) -> None:
        state = self._current_sync_state()
        if not force and self._last_sync == state:
            return
        self._last_sync = state
        await self._send_serial(format_sync_line(state) + "\n")
        await self._send_osc(
            self.config.sync_osc_address,
            [state.bpm, 1 if state.running else 0, 1 if state.click_enabled else 0, state.click_interval],
        )

    async def _send_beat(self, value: float) -> None:
        await self._send_serial(format_beat_line(value) + "\n")
        await self._send_osc(self.config.beat_osc_address, [value])

    async def _send_serial(self, payload: str) -> None:
        if not self._use_serial or not self._serial_connected or self._serial_port is None:
            return
        try:
            data = payload.encode("utf-8")

            def write_and_flush() -> None:
                self._serial_port.write(data)
                flush = getattr(self._serial_port, "flush", None)
                if callable(flush):
                    flush()

            await asyncio.to_thread(write_and_flush)
        except OSError:
            LOGGER.exception("rotary display serial write failed")
            self._serial_connected = False

    async def _send_osc(self, address: str, arguments: list[Any]) -> None:
        if not self._use_osc or not self._feedback_host or self._feedback_port <= 0:
            return
        payload = encode_message(address, arguments)
        try:
            await asyncio.to_thread(
                _udp_send,
                payload,
                self._feedback_host,
                self._feedback_port,
            )
        except OSError:
            LOGGER.exception(
                "rotary display OSC send failed for %s -> %s:%s",
                address,
                self._feedback_host,
                self._feedback_port,
            )

    def _open_serial_port(self, port_name: str) -> Any:
        import serial

        # dsrdtr=False avoids toggling DTR on open, which would reset ESP32 USB CDC boards.
        return serial.Serial(
            port_name,
            self.config.serial_baud,
            timeout=0.2,
            dsrdtr=False,
            rtscts=False,
        )

    async def _serial_loop(self) -> None:
        try:
            import serial  # noqa: F401
        except ImportError:
            LOGGER.error(
                "rotary_display serial transport requires pyserial; "
                "install with: pip install pyserial  "
                "(or: pip install 'midijuggler[rotary]')"
            )
            return

        port_name = self.config.serial_port
        while self.running:
            try:
                self._serial_port = await asyncio.to_thread(
                    self._open_serial_port,
                    port_name,
                )
                self._serial_connected = True
                LOGGER.info("rotary display serial connected on %s", port_name)
                # USB CDC boards reboot when the host opens the port; wait for hello.
                await asyncio.sleep(1.5)
                await self._send_sync(force=True)
                while self.running:
                    line = await asyncio.to_thread(self._serial_port.readline)
                    if not line:
                        continue
                    text = line.decode("utf-8", errors="replace")
                    await self._handle_serial_line(text)
            except asyncio.CancelledError:
                raise
            except OSError:
                LOGGER.exception(
                    "rotary display serial error on %s (check port path and close other serial tools)",
                    port_name,
                )
                self._serial_connected = False
                if self._serial_port is not None:
                    with contextlib.suppress(Exception):
                        self._serial_port.close()
                    self._serial_port = None
                await asyncio.sleep(2.0)

    async def _handle_serial_line(self, line: str) -> None:
        parsed = parse_serial_line(line)
        if parsed is None:
            return
        command, args = parsed
        if command == "hello":
            self._serial_connected = True
            LOGGER.info("rotary display hello on serial")
            await self._send_sync(force=True)
            return
        event = serial_command_to_clock_event(command, args)
        if event is None:
            LOGGER.debug("ignored rotary serial line: %s", line.strip())
            return
        LOGGER.info("rotary display serial command: %s", line.strip())
        await self.master_clock.handle_command(event)
        if event.command == "set_bpm":
            await self.master_clock.flush_bpm_notifications()
        await self._send_sync(force=True)


def _udp_send(payload: bytes, host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(payload, (host, port))
