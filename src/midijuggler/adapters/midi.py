"""MIDI adapter using mido/python-rtmidi on Linux."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from midijuggler.adapters.base import Adapter, MIDI_TIMING_CLOCK
from midijuggler.config import AdapterConfig, AppConfig
from midijuggler.datapoint.store import DataPointStore
from midijuggler.eventbus import EventBus
from midijuggler.events import (
    AdapterStatusEvent,
    ControlEvent,
    MidiClockEvent,
    MidiMessageEvent,
)
from midijuggler.midi.echo_guard import (
    MidiEchoGuard,
    parse_echo_guard_ms,
)
from midijuggler.midi.mido_io import (
    MidoUnavailableError,
    close_mido_port,
    is_mido_port_listed,
    mido_available,
    mido_message_to_status_data,
    open_mido_input,
    poll_mido_input,
)
from midijuggler.midi.output import send_midi_message_to_port
from midijuggler.events import MappedEvent
from midijuggler.midi.library_match import (
    MidiSourceIndex,
    build_source_index,
    resolve_incoming_controls,
    resolve_library_port,
)
from midijuggler.device.lookup import device_id_for_adapter
from midijuggler.device.registry import DeviceRegistry
from midijuggler.midi.target_encode import encode_mapped_midi_target
from midijuggler.midi.xtouch_feedback import (
    XTouchFeedbackRefresh,
    is_layer_program_change,
    uses_xtouch_feedback_refresh,
)
from midijuggler.midi_library import get_midi_library
from midijuggler.system_info import (
    resolve_midi_input_port_address,
    resolve_midi_output_port_address,
)

LOGGER = logging.getLogger(__name__)
PORT_WAIT_INTERVAL_SECONDS = 2.0
INPUT_RECONNECT_DELAY_SECONDS = 1.0


class MidiAdapter(Adapter):
    protocol = "MIDI"

    def __init__(
        self,
        name: str,
        config: AdapterConfig,
        bus: EventBus,
        app_config: AppConfig | None = None,
    ) -> None:
        super().__init__(name, config, bus)
        self._app_config = app_config
        self._input_address: str | None = None
        self._output_address: str | None = None
        self._input_task: asyncio.Task[None] | None = None
        self._input_port: object | None = None
        self._source_index: MidiSourceIndex | None = None
        self._last_connection_detail: str | None = None
        self._feedback_refresh: XTouchFeedbackRefresh | None = None
        self._echo_guard = MidiEchoGuard()
        self._datapoint_store: DataPointStore | None = None

    def bind_datapoint_store(self, store: DataPointStore) -> None:
        self._datapoint_store = store

    def _configure_echo_guard(self) -> None:
        self._echo_guard.configure(
            parse_echo_guard_ms(self.config.options.get("echo_guard_ms"))
        )

    async def start(self) -> None:
        if not self.config.enabled:
            self.running = False
            await self.bus.publish(
                AdapterStatusEvent(
                    source=self.name,
                    adapter=self.name,
                    status="stopped",
                    detail="MIDI adapter disabled",
                    connection_phase="idle",
                )
            )
            return

        self._source_index = self._load_source_index()
        self._configure_echo_guard()
        self._last_connection_detail = None
        input_port = str(self.config.options.get("input_port", "")).strip()
        output_port = str(self.config.options.get("output_port", "")).strip()
        has_input = bool(input_port)
        has_output = bool(output_port or input_port)

        if not has_input and not has_output:
            self.running = True
            await self.bus.publish(
                AdapterStatusEvent(
                    source=self.name,
                    adapter=self.name,
                    status="started",
                    detail="MIDI adapter active without configured ALSA ports",
                    connection_phase="idle",
                )
            )
            return

        self._refresh_port_addresses()

        if has_input and not mido_available():
            LOGGER.error(
                "MIDI adapter %s needs mido and python-rtmidi to read input port %s",
                self.name,
                input_port,
            )
            self.running = True
            await self.bus.publish(
                AdapterStatusEvent(
                    source=self.name,
                    adapter=self.name,
                    status="started",
                    detail=(
                        "MIDI input unavailable: install midijuggler[midi] "
                        "(mido and python-rtmidi)"
                    ),
                    connection_phase="unavailable",
                )
            )
            return

        self.running = True
        if has_input:
            self._input_task = asyncio.create_task(
                self._input_loop(),
                name=f"midi-input-{self.name}",
            )

        await self._publish_connection_status("started", force=True)
        await self._start_feedback_refresh()

    async def _start_feedback_refresh(self) -> None:
        if self._feedback_refresh is not None:
            await self._feedback_refresh.stop()
            self._feedback_refresh = None
        device = self._resolve_device()
        if not uses_xtouch_feedback_refresh(
            self.config,
            library_id=self._resolve_midi_library_id(),
            device=device,
        ):
            return
        self._feedback_refresh = XTouchFeedbackRefresh(self, self._app_config)
        self._feedback_refresh.configure(
            self.config,
            self._app_config,
            device,
            library_id=self._resolve_midi_library_id(),
            store=self._datapoint_store,
            device_id=device.id if device is not None else "",
        )
        await self._feedback_refresh.start(self.config)

    async def reload(self, config: AdapterConfig) -> None:
        """Restart MIDI listeners after a configuration change."""

        self.config = config
        if self.running:
            await self.stop()
        if config.enabled:
            await self.start()

    async def stop(self) -> None:
        self.running = False
        if self._feedback_refresh is not None:
            await self._feedback_refresh.stop()
        if self._input_task is not None:
            self._input_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._input_task
            self._input_task = None

        if self._input_port is not None:
            await asyncio.to_thread(close_mido_port, self._input_port)
            self._input_port = None

        self._source_index = None
        self._last_connection_detail = None
        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status="stopped",
                detail="MIDI adapter stopped",
                connection_phase="stopped",
            )
        )

    def _resolve_device(self) -> DeviceConfig | None:
        if self._app_config is None:
            return None
        return DeviceRegistry.from_config(self._app_config).device_for_adapter(self.name)

    def _resolve_midi_library_id(self) -> str:
        if self._app_config is not None:
            library_id = DeviceRegistry.from_config(self._app_config).device_library_for_adapter(
                self.name
            )
            if library_id:
                return library_id
        return str(self.config.options.get("midi_library", "")).strip()

    def _load_source_index(self) -> MidiSourceIndex | None:
        library_id = self._resolve_midi_library_id()
        if not library_id:
            return None

        try:
            library = get_midi_library(library_id)
        except KeyError:
            LOGGER.warning(
                "MIDI adapter %s uses unknown midi_library %r",
                self.name,
                library_id,
            )
            return None

        return build_source_index(
            library,
            resolve_library_port(self.config),
            adapter=self.config,
            device=self._resolve_device(),
        )

    def _refresh_port_addresses(self) -> None:
        """Re-resolve MIDI port names from configured port labels."""

        input_port = str(self.config.options.get("input_port", "")).strip()
        output_port = str(self.config.options.get("output_port", "")).strip()
        previous_input = self._input_address
        self._input_address = (
            resolve_midi_input_port_address(input_port) if input_port else None
        )
        self._output_address = (
            self._resolve_output_address() if output_port or input_port else None
        )

        if previous_input and self._input_address and previous_input != self._input_address:
            LOGGER.info(
                "MIDI adapter %s input port %r moved from %s to %s",
                self.name,
                input_port,
                previous_input,
                self._input_address,
            )
        elif input_port and self._input_address is None and previous_input is not None:
            LOGGER.warning(
                "MIDI adapter %s lost input port %r (was %s)",
                self.name,
                input_port,
                previous_input,
            )
        elif input_port and self._input_address is None and previous_input is None:
            LOGGER.debug(
                "MIDI adapter %s still waiting for input port %r",
                self.name,
                input_port,
            )

    def _connection_detail(self, phase: str) -> str:
        input_port = str(self.config.options.get("input_port", "")).strip()
        output_port = str(self.config.options.get("output_port", "")).strip()

        if phase == "waiting" and input_port:
            return f"MIDI adapter waiting for input {input_port}"
        if phase == "reconnecting" and input_port:
            return f"MIDI adapter reconnecting input {input_port}"

        parts: list[str] = []
        if input_port:
            if self._input_address:
                parts.append(f"input {input_port} ({self._input_address})")
            else:
                parts.append(f"input {input_port} (unavailable)")
        if output_port:
            if self._output_address:
                parts.append(f"output {output_port} ({self._output_address})")
            else:
                parts.append(f"output {output_port} (unavailable)")
        elif (
            input_port
            and self._output_address
            and self._output_address != self._input_address
        ):
            parts.append(f"output {input_port} ({self._output_address})")

        if not parts:
            return "MIDI adapter active without configured ALSA ports"
        prefix = "MIDI adapter listening on"
        if phase in {"waiting", "reconnecting"}:
            prefix = "MIDI adapter active on"
        return prefix + " " + ", ".join(parts)

    async def _publish_connection_status(self, phase: str, *, force: bool = False) -> None:
        detail = self._connection_detail(phase)
        if not force and detail == self._last_connection_detail:
            return
        self._last_connection_detail = detail
        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status="started",
                detail=detail,
                connection_phase=phase,
            )
        )

    async def _input_loop(self) -> None:
        while self.running:
            self._refresh_port_addresses()
            if self._input_address is None:
                await self._publish_connection_status("waiting")
                await asyncio.sleep(PORT_WAIT_INTERVAL_SECONDS)
                continue

            try:
                await self._run_mido_input(self._input_address)
            except asyncio.CancelledError:
                raise
            except MidoUnavailableError:
                LOGGER.error("MIDI adapter %s cannot use mido backend", self.name)
                self.running = False
                raise
            except OSError:
                LOGGER.warning(
                    "MIDI adapter %s could not open input %s",
                    self.name,
                    self._input_address,
                    exc_info=True,
                )
            except Exception:
                LOGGER.exception(
                    "MIDI adapter %s input loop failed for %s",
                    self.name,
                    self._input_address,
                )
            if self.running:
                await self._publish_connection_status("reconnecting")
                await asyncio.sleep(INPUT_RECONNECT_DELAY_SECONDS)

    async def _run_mido_input(self, port_name: str) -> None:
        port = await asyncio.to_thread(open_mido_input, port_name)
        self._input_port = port
        await self._publish_connection_status("connected")
        last_presence_check = time.monotonic()
        try:
            while self.running:
                now = time.monotonic()
                if now - last_presence_check >= PORT_WAIT_INTERVAL_SECONDS:
                    listed = await asyncio.to_thread(
                        is_mido_port_listed,
                        port_name,
                        inputs=True,
                    )
                    if not listed:
                        LOGGER.warning(
                            "MIDI adapter %s input port %r disappeared",
                            self.name,
                            port_name,
                        )
                        break
                    last_presence_check = now

                message = await asyncio.to_thread(poll_mido_input, port, 0.1)
                if message is None:
                    continue

                parsed = mido_message_to_status_data(message)
                if parsed is None:
                    continue
                status, data = parsed
                await self._handle_input_message(status, data)
        finally:
            await asyncio.to_thread(close_mido_port, port)
            if self._input_port is port:
                self._input_port = None

    async def _handle_input_message(self, status: int, data: tuple[int, ...]) -> None:
        if status == MIDI_TIMING_CLOCK:
            await self.bus.publish(MidiClockEvent(source=self.name))
            return

        if self._echo_guard.is_echo(status, data):
            LOGGER.debug(
                "MIDI adapter %s ignored echo input status=0x%02X data=%s",
                self.name,
                status,
                data,
            )
            return

        if (
            self._feedback_refresh is not None
            and is_layer_program_change(
                self.config,
                status,
                data,
                library_id=self._resolve_midi_library_id(),
                device=self._resolve_device(),
            )
        ):
            await self._feedback_refresh.resend_all()

        await self.bus.publish(
            MidiMessageEvent(
                source=self.name,
                status=status,
                data=data,
                direction="input",
            )
        )
        for match in resolve_incoming_controls(self._source_index, status, data):
            await self.bus.publish(
                ControlEvent(
                    source=self.name,
                    control=match.control_id,
                    value=match.value,
                )
            )

    def _cached_output_address(self) -> str | None:
        if self._output_address is not None:
            return self._output_address
        output_port = str(self.config.options.get("output_port", "")).strip()
        input_port = str(self.config.options.get("input_port", "")).strip()
        if not output_port and not input_port:
            return None
        self._refresh_port_addresses()
        return self._output_address

    def _resolve_output_address(self) -> str | None:
        output_port = str(self.config.options.get("output_port", "")).strip()
        input_port = str(self.config.options.get("input_port", "")).strip()
        if not output_port and not input_port:
            return None

        return resolve_midi_output_port_address(
            output_port,
            input_port_name=input_port or None,
        )

    async def send_midi_message(self, event: MidiMessageEvent) -> None:
        output_address = self._cached_output_address()
        if output_address is None:
            if event.status == MIDI_TIMING_CLOCK:
                return
            LOGGER.warning(
                "MIDI adapter %s has no output_port configured; dropped %s",
                self.name,
                event.as_dict(),
            )
            return

        await self._emit_midi_output(output_address, event)

    def remember_feedback_value(self, point: str, value: float) -> None:
        if self._feedback_refresh is not None:
            self._feedback_refresh.remember(point, value)

    async def send_feedback_target(self, point: str, value: float) -> None:
        if self._app_config is None:
            raise ValueError(
                f"MIDI adapter {self.name} cannot send feedback without app config"
            )
        device_id = device_id_for_adapter(self._app_config, self.name)
        registry = DeviceRegistry.from_config(self._app_config)
        status, data = encode_mapped_midi_target(
            self._app_config,
            registry,
            device_id,
            point,
            value,
        )
        await self.send_midi_message(
            MidiMessageEvent(
                source=self.name,
                status=status,
                data=data,
                target=f"{self.name}:{point}",
                direction="output",
                feedback_refresh=True,
            )
        )

    async def send(self, event: MappedEvent) -> None:
        module, separator, point = event.target.partition(":")
        if not separator or module != self.name:
            await super().send(event)
            return
        if self._app_config is None:
            LOGGER.warning(
                "MIDI adapter %s cannot send mapped event without app config: %s",
                self.name,
                event.target,
            )
            return
        try:
            device_id = device_id_for_adapter(self._app_config, self.name)
            registry = DeviceRegistry.from_config(self._app_config)
            status, data = encode_mapped_midi_target(
                self._app_config,
                registry,
                device_id,
                point,
                event.value,
            )
        except ValueError:
            LOGGER.warning(
                "MIDI adapter %s cannot encode mapped target %s",
                self.name,
                event.target,
            )
            return
        self.remember_feedback_value(point, event.value)
        await self.send_midi_message(
            MidiMessageEvent(
                source=self.name,
                status=status,
                data=data,
                target=event.target,
                direction="output",
            )
        )

    async def send_test_message(
        self,
        status: int,
        data: tuple[int, ...],
        *,
        feedback_point: str | None = None,
        feedback_value: float | None = None,
    ) -> None:
        output_address = self._cached_output_address()
        if output_address is None:
            output_port = str(self.config.options.get("output_port", "")).strip()
            input_port = str(self.config.options.get("input_port", "")).strip()
            if output_port or input_port:
                raise OSError(
                    f"MIDI adapter {self.name} cannot resolve a writable MIDI output port "
                    f"for {output_port or input_port!r}; re-select the output port in the web UI"
                )
            raise OSError(
                f"MIDI adapter {self.name} has no output_port configured for sending"
            )

        try:
            await self._emit_midi_output(
                output_address,
                MidiMessageEvent(
                    source=self.name,
                    status=status,
                    data=data,
                    direction="output",
                ),
            )
        except OSError as exc:
            input_port = str(self.config.options.get("input_port", "")).strip()
            raise OSError(
                f"{exc} (resolved output address {output_address!r} "
                f"from output_port={self.config.options.get('output_port', '')!r}, "
                f"input_port={input_port!r})"
            ) from exc
        if feedback_point is not None and feedback_value is not None:
            self.remember_feedback_value(feedback_point, feedback_value)

    async def _emit_midi_output(
        self,
        output_address: str,
        event: MidiMessageEvent,
    ) -> None:
        await send_midi_message_to_port(output_address, event.status, event.data)
        self._echo_guard.record(event.status, event.data)
        await self.bus.publish(
            MidiMessageEvent(
                source=self.name,
                status=event.status,
                data=event.data,
                target=event.target,
                direction="output",
                feedback_refresh=event.feedback_refresh,
            )
        )
