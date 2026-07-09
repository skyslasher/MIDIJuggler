"""Rotary display feedback and USB-serial command ingress."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from midijuggler.config import RotaryDisplayConfig
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    DataPointDirection,
    DataPointId,
    DataPointSpec,
    DataPointValue,
    ValueType,
    float_value,
    trigger_value,
)
from midijuggler.eventbus import EventBus
from midijuggler.events import MasterClockCommandEvent, OscMessageEvent
from midijuggler.master_clock import (
    MasterClock,
    click_interval_from_set_value,
    click_interval_to_set_value,
)
from midijuggler.modules.base import InterfaceModule
from midijuggler.modules.interface.rotary_display.device_config import (
    build_device_config_commands,
    device_config_fingerprint,
    push_device_config_sync,
)
from midijuggler.datapoint.rotary_module_feedback import (
    ROTARY_FEEDBACK_POINTS,
    ROTARY_MODULE,
)
from midijuggler.modules.interface.rotary_display.protocol import (
    RotarySyncState,
    format_beat_line,
    format_sync_line,
    parse_hello_osc,
    parse_serial_line,
    serial_command_to_clock_event,
)
from midijuggler.osc.protocol import encode_message
from midijuggler.rotary_mdns import (
    invalidate_mdns_cache,
    is_mdns_hostname,
    resolve_mdns_ipv4,
    resolve_udp_host,
)

LOGGER = logging.getLogger(__name__)

DEVICE_SET_BPM_TAP_TEMPO_COOLDOWN_S = 3.0


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
        self._feedback_host_ip: str | None = None
        self._serial_connected = False
        self._serial_port: Any | None = None
        self._serial_task: asyncio.Task[None] | None = None
        self._last_sync: RotarySyncState | None = None
        self._last_beat: float | None = None
        self._beat_pulse_active = False
        self._beat_send_lock = asyncio.Lock()
        self._beat_send_task: asyncio.Task[None] | None = None
        self._beat_outbox: deque[float] = deque()
        self._pending_beat_value: float | None = None
        self._beat_send_in_flight = False
        self._last_device_set_bpm_at: float | None = None
        self._last_pushed_fingerprint: str | None = None
        self._serial_lock = asyncio.Lock()
        self._use_osc = config.transport in {"osc", "both"}
        self._use_serial = config.transport in {"serial", "both"}
        self._feedback_registration_handler: Callable[[str, int], None] | None = None

    def datapoints(self) -> list[DataPointSpec]:
        bpm_min = self.master_clock.config.bpm_min
        bpm_max = self.master_clock.config.bpm_max
        specs = [
            DataPointSpec(
                id=DataPointId(ROTARY_MODULE, "bpm"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.OUTPUT,
                label="Feedback BPM",
                value_min=bpm_min,
                value_max=bpm_max,
                protocol="rotary_display",
                category="feedback",
            ),
            DataPointSpec(
                id=DataPointId(ROTARY_MODULE, "running"),
                value_type=ValueType.BOOL,
                direction=DataPointDirection.OUTPUT,
                label="Feedback transport running",
                protocol="rotary_display",
                category="feedback",
            ),
            DataPointSpec(
                id=DataPointId(ROTARY_MODULE, "click_enabled"),
                value_type=ValueType.BOOL,
                direction=DataPointDirection.OUTPUT,
                label="Feedback audio click enabled",
                protocol="rotary_display",
                category="feedback",
            ),
            DataPointSpec(
                id=DataPointId(ROTARY_MODULE, "click_interval"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.OUTPUT,
                label="Feedback click interval (0=whole .. 4=sixteenth)",
                value_min=0.0,
                value_max=4.0,
                protocol="rotary_display",
                category="feedback",
            ),
            DataPointSpec(
                id=DataPointId(ROTARY_MODULE, "beat"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.OUTPUT,
                label="Feedback beat pulse",
                value_min=0.0,
                value_max=1.0,
                protocol="rotary_display",
                category="feedback",
            ),
        ]
        return specs

    async def start(self) -> None:
        await super().start()
        for point in ROTARY_FEEDBACK_POINTS:
            if point == "beat":
                self.store.subscribe(DataPointId("clock", "beat"), self._on_feedback)
                continue
            self.store.subscribe(DataPointId(ROTARY_MODULE, point), self._on_feedback)
        self.bus.subscribe(OscMessageEvent, self._on_osc_message)
        self._start_serial_loop_if_needed()
        self._apply_configured_feedback_target()
        if self._use_osc and self._feedback_host and self._feedback_port > 0:
            await self._prime_feedback_host_ip(self._feedback_host)
            await self._send_sync(force=True)

    def set_feedback_registration_handler(
        self,
        handler: Callable[[str, int], None] | None,
    ) -> None:
        self._feedback_registration_handler = handler
        self._apply_configured_feedback_target()

    def _apply_configured_feedback_target(self) -> None:
        if self._feedback_registration_handler is None:
            return
        if not self.config.feedback_host:
            return
        self._feedback_registration_handler(
            self.config.feedback_host,
            self.config.feedback_port,
        )

    def _register_feedback_target(self, host: str, port: int) -> None:
        self._feedback_host = host
        self._feedback_port = port
        self._feedback_host_ip = None
        if self._feedback_registration_handler is not None:
            self._feedback_registration_handler(host, port)

    async def _prime_feedback_host_ip(self, host: str) -> None:
        if not is_mdns_hostname(host):
            return
        try:
            resolved = await asyncio.to_thread(resolve_mdns_ipv4, host)
        except OSError as exc:
            LOGGER.warning(
                "could not pre-resolve rotary display feedback target %s: %s",
                host,
                exc,
            )
            return
        if resolved is not None:
            self._feedback_host_ip = resolved
            LOGGER.debug(
                "resolved rotary display feedback target %s -> %s",
                host,
                resolved,
            )

    async def stop(self) -> None:
        await self._stop_serial()
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
        host, port = parsed
        changed = host != self._feedback_host or port != self._feedback_port
        self._register_feedback_target(host, port)
        await self._prime_feedback_host_ip(host)
        if changed:
            LOGGER.info(
                "rotary display registered at %s:%s",
                self._feedback_host,
                self._feedback_port,
            )
        else:
            LOGGER.debug(
                "rotary display re-registered at %s:%s",
                self._feedback_host,
                self._feedback_port,
            )
        await self._send_sync(force=True)

    async def _on_feedback(self, value: DataPointValue) -> None:
        if value.point_id.point == "beat":
            if value.float_value is None:
                return
            beat = float(value.float_value)
            active = beat > 0.5
            if active:
                if self.master_clock.running and (
                    value.force_notify or not self._beat_pulse_active
                ):
                    self._schedule_beat_send(beat)
                self._beat_pulse_active = True
                self._last_beat = beat
            else:
                self._beat_pulse_active = False
                self._last_beat = beat
            return
        if value.point_id.point == "running" and value.bool_value is False:
            await self._cancel_beat_delivery(send_off=True)
        await self._send_sync(force=True)

    def _current_sync_state(self) -> RotarySyncState:
        snapshot = self.store.snapshot()
        bpm_value = snapshot.get(str(DataPointId(ROTARY_MODULE, "bpm")))
        running_value = snapshot.get(str(DataPointId(ROTARY_MODULE, "running")))
        click_value = snapshot.get(str(DataPointId(ROTARY_MODULE, "click_enabled")))
        interval_value = snapshot.get(str(DataPointId(ROTARY_MODULE, "click_interval")))

        bpm = self.master_clock.bpm
        if bpm_value is not None and bpm_value.get("float_value") is not None:
            store_bpm = float(bpm_value["float_value"])
            if abs(store_bpm - bpm) <= 1e-3:
                bpm = store_bpm

        running = self.master_clock.running
        if running_value is not None and running_value.get("bool_value") is not None:
            running = bool(running_value["bool_value"])

        click_enabled = self.master_clock.config.click_enabled
        if click_value is not None and click_value.get("bool_value") is not None:
            click_enabled = bool(click_value["bool_value"])

        click_interval = self.master_clock.click_interval
        if interval_value is not None and interval_value.get("float_value") is not None:
            click_interval = click_interval_from_set_value(float(interval_value["float_value"]))

        return RotarySyncState(
            bpm=bpm,
            running=running,
            click_enabled=click_enabled,
            click_interval=click_interval,
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

    def _clear_pending_beats(self) -> None:
        self._beat_outbox.clear()
        self._pending_beat_value = None
        self._beat_send_in_flight = False
        if self._beat_send_task is not None and not self._beat_send_task.done():
            self._beat_send_task.cancel()
        self._beat_send_task = None

    async def _cancel_beat_delivery(self, *, send_off: bool = False) -> None:
        self._clear_pending_beats()
        self._beat_pulse_active = False
        if send_off:
            await self._send_beat(0.0)

    def _schedule_beat_send(self, value: float) -> None:
        if not self.running or not self.master_clock.running or value <= 0.5:
            return
        if self._beat_send_in_flight:
            self._pending_beat_value = value
            return
        self._beat_outbox.append(value)
        if self._beat_send_task is None or self._beat_send_task.done():
            self._beat_send_task = asyncio.create_task(
                self._drain_pending_beat_sends(),
                name="rotary-display-beat",
            )

    def _dequeue_beat_send_value(self) -> float | None:
        if self._pending_beat_value is not None:
            value = self._pending_beat_value
            self._pending_beat_value = None
            self._beat_outbox.clear()
            return value
        if not self._beat_outbox:
            return None
        return self._beat_outbox.popleft()

    async def _drain_pending_beat_sends(self) -> None:
        try:
            while self._beat_outbox or self._pending_beat_value is not None:
                if not self.master_clock.running:
                    break
                async with self._beat_send_lock:
                    if not self.master_clock.running:
                        break
                    value = self._dequeue_beat_send_value()
                    if value is None:
                        break
                    self._beat_send_in_flight = True
                    try:
                        await self._send_beat(value)
                    finally:
                        self._beat_send_in_flight = False
        finally:
            self._beat_send_task = None

    async def _send_beat(self, value: float) -> None:
        # Beats are timing-critical: never duplicate on OSC and serial when both are enabled.
        if self._use_osc and self._feedback_host and self._feedback_port > 0:
            # UDP beats are fire-and-forget; awaiting thread-pool sends drops edges at high BPM.
            asyncio.create_task(
                self._send_osc(self.config.beat_osc_address, [value]),
                name="rotary-display-beat-osc",
            )
            return
        await self._send_serial(format_beat_line(value) + "\n")

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

            async with self._serial_lock:
                await asyncio.to_thread(write_and_flush)
        except OSError:
            LOGGER.exception("rotary display serial write failed")
            self._serial_connected = False

    def update_config(self, config: RotaryDisplayConfig) -> None:
        previous_fingerprint = device_config_fingerprint(self.config.device)
        self.config = config
        self._use_osc = config.transport in {"osc", "both"}
        self._use_serial = config.transport in {"serial", "both"}
        if device_config_fingerprint(config.device) != previous_fingerprint:
            self._last_pushed_fingerprint = None

    async def apply_runtime_config(self, config: RotaryDisplayConfig) -> None:
        """Apply config at runtime and reconcile serial transport state."""

        previous_use_serial = self._use_serial
        previous_serial_port = self.config.serial_port
        self.update_config(config)

        serial_needed = self._serial_transport_enabled()
        serial_was_needed = previous_use_serial and bool(previous_serial_port.strip())
        serial_port_changed = previous_serial_port != config.serial_port

        if not serial_needed:
            await self._stop_serial()
            return

        if (
            not serial_was_needed
            or serial_port_changed
            or self._serial_task is None
            or self._serial_task.done()
        ):
            await self._stop_serial()
            self._start_serial_loop_if_needed()

    def _serial_transport_enabled(self) -> bool:
        return self._use_serial and bool(self.config.serial_port.strip())

    def _start_serial_loop_if_needed(self) -> None:
        if not self.running or not self._use_serial:
            return
        if not self.config.serial_port.strip():
            LOGGER.error(
                "rotary_display serial transport enabled but serial_port is empty; "
                "set serial_port in config (macOS: /dev/cu.usbmodem*)"
            )
            return
        if self._serial_task is not None and not self._serial_task.done():
            return
        self._serial_task = asyncio.create_task(
            self._serial_loop(),
            name="rotary-display-serial",
        )

    async def _stop_serial(self) -> None:
        if self._serial_task is not None:
            self._serial_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._serial_task
            self._serial_task = None
        if self._serial_port is not None:
            with contextlib.suppress(Exception):
                self._serial_port.close()
            self._serial_port = None
        self._serial_connected = False

    async def _ensure_serial_ready(self, *, timeout_s: float = 8.0) -> bool:
        if not self._serial_transport_enabled():
            return False
        self._start_serial_loop_if_needed()
        if self._serial_connected and self._serial_port is not None:
            return True

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._serial_connected and self._serial_port is not None:
                return True
            await asyncio.sleep(0.1)
        return self._serial_connected and self._serial_port is not None

    def _device_push_serial_available(self) -> bool:
        return bool(self.config.serial_port.strip())

    async def _ensure_serial_push_ready(self, *, timeout_s: float = 8.0) -> bool:
        """Prepare USB serial for device config push, independent of host transport."""

        if not self._device_push_serial_available():
            return False
        if self._serial_connected and self._serial_port is not None:
            return True
        if self._serial_transport_enabled():
            return await self._ensure_serial_ready(timeout_s=timeout_s)

        if not self.running:
            return False
        if self._serial_task is None or self._serial_task.done():
            self._serial_task = asyncio.create_task(
                self._serial_loop(),
                name="rotary-display-serial-push",
            )

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._serial_connected and self._serial_port is not None:
                return True
            await asyncio.sleep(0.1)
        return self._serial_connected and self._serial_port is not None

    def device_push_status(self) -> dict[str, Any]:
        fingerprint = device_config_fingerprint(self.config.device)
        return {
            "serial_connected": self._serial_connected,
            "host_uses_serial": self._serial_transport_enabled(),
            "last_pushed_fingerprint": self._last_pushed_fingerprint,
            "current_fingerprint": fingerprint,
            "push_pending": self._last_pushed_fingerprint != fingerprint,
        }

    async def push_device_config(self, *, force: bool = False) -> dict[str, Any]:
        fingerprint = device_config_fingerprint(self.config.device)
        if not force and fingerprint == self._last_pushed_fingerprint:
            return {
                "pushed": False,
                "reason": "unchanged",
                "fingerprint": fingerprint,
            }
        if not self._device_push_serial_available():
            return {
                "pushed": False,
                "reason": "serial port not configured",
                "fingerprint": fingerprint,
            }
        await self._ensure_serial_push_ready()
        if not self._serial_connected or self._serial_port is None:
            return {
                "pushed": False,
                "reason": "serial not connected",
                "fingerprint": fingerprint,
            }

        commands = build_device_config_commands(self.config.device)

        async with self._serial_lock:
            result = await asyncio.to_thread(
                push_device_config_sync,
                self._serial_port,
                commands,
            )

        if result.get("ok"):
            self._last_pushed_fingerprint = fingerprint
            LOGGER.info("rotary display device config pushed (%d commands)", len(commands))
            if self._use_osc:
                # Device re-sends hello after transport changes; prime sync once registered.
                await self._send_sync(force=True)
            return {
                "pushed": True,
                "fingerprint": fingerprint,
                "commands": commands,
                "responses": result.get("responses", []),
            }

        LOGGER.warning(
            "rotary display device config push failed: %s",
            result.get("failed_command") or result.get("error") or result.get("responses"),
        )
        return {
            "pushed": False,
            "reason": result.get("reason") or "device rejected config",
            "fingerprint": fingerprint,
            "commands": commands,
            **result,
        }

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
                fallback_ip=self._feedback_host_ip,
            )
        except OSError as exc:
            LOGGER.error(
                "rotary display OSC send failed for %s -> %s:%s: %s",
                address,
                self._feedback_host,
                self._feedback_port,
                exc,
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
                    async with self._serial_lock:
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
            push_result = await self.push_device_config()
            if push_result.get("pushed"):
                LOGGER.info("rotary display config pushed on hello")
            elif push_result.get("reason") not in {"unchanged", "serial not connected"}:
                LOGGER.warning("rotary display config push on hello failed: %s", push_result)
            await self._send_sync(force=True)
            return
        event = serial_command_to_clock_event(command, args)
        if event is None:
            LOGGER.debug("ignored rotary serial line: %s", line.strip())
            return
        if event.command == "set_bpm":
            self._last_device_set_bpm_at = time.monotonic()
        elif (
            event.command == "tap_tempo"
            and self._last_device_set_bpm_at is not None
            and time.monotonic() - self._last_device_set_bpm_at
            < DEVICE_SET_BPM_TAP_TEMPO_COOLDOWN_S
        ):
            LOGGER.debug(
                "ignored rotary tap_tempo within %.1fs of device set_bpm",
                DEVICE_SET_BPM_TAP_TEMPO_COOLDOWN_S,
            )
            return
        LOGGER.info("rotary display serial command: %s", line.strip())
        if self.master_clock._datapoint_sink is not None:
            await self._route_clock_command_to_store(event)
        else:
            await self.master_clock.handle_command(event)
        if event.command in {"set_bpm", "tap_tempo"}:
            await self.master_clock.flush_bpm_notifications()
        await self._send_sync(force=True)

    async def _route_clock_command_to_store(
        self,
        event: MasterClockCommandEvent,
    ) -> None:
        if event.command == "set_bpm":
            await self.store.write(
                float_value(
                    DataPointId("clock", "bpm_set"),
                    float(event.value),
                    force_notify=True,
                )
            )
            return
        if event.command == "set_click_interval":
            await self.store.write(
                float_value(
                    DataPointId("clock", "click_interval_set"),
                    click_interval_to_set_value(str(event.value)),
                    force_notify=True,
                )
            )
            return
        trigger_points = {
            "start_stop": "start_stop",
            "tap_tempo": "tap_tempo",
            "toggle_click": "click_toggle",
        }
        point = trigger_points.get(event.command)
        if point is not None:
            point_id = DataPointId("clock", point)
            await self.store.write(trigger_value(point_id, True))
            await self.store.write(trigger_value(point_id, False))
            return
        await self.master_clock.handle_command(event)


def _udp_send(
    payload: bytes,
    host: str,
    port: int,
    *,
    fallback_ip: str | None = None,
) -> None:
    target = host.strip()

    def send_to(resolved_host: str) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(payload, (resolved_host, port))

    try:
        send_to(resolve_udp_host(target, fallback_ip=fallback_ip))
    except OSError:
        if not is_mdns_hostname(target):
            raise
        invalidate_mdns_cache(target)
        send_to(
            resolve_udp_host(
                target,
                fallback_ip=fallback_ip,
                force=True,
            )
        )
