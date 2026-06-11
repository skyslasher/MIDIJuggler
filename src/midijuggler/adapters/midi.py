"""MIDI adapter using the ALSA sequencer on Linux."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil

from midijuggler.adapters.base import Adapter, MIDI_TIMING_CLOCK
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import (
    AdapterStatusEvent,
    ControlEvent,
    MidiClockEvent,
    MidiMessageEvent,
)
from midijuggler.midi.alsa import parse_aseqdump_line
from midijuggler.midi.output import send_midi_message_to_port
from midijuggler.midi.library_match import (
    MidiSourceIndex,
    build_source_index,
    resolve_incoming_controls,
    resolve_library_port,
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

    def __init__(self, name: str, config: AdapterConfig, bus: EventBus) -> None:
        super().__init__(name, config, bus)
        self._input_address: str | None = None
        self._output_address: str | None = None
        self._input_task: asyncio.Task[None] | None = None
        self._input_process: asyncio.subprocess.Process | None = None
        self._source_index: MidiSourceIndex | None = None
        self._last_connection_detail: str | None = None

    async def start(self) -> None:
        self._source_index = self._load_source_index()
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
                )
            )
            return

        self._refresh_port_addresses()

        if has_input and shutil.which("aseqdump") is None:
            LOGGER.error(
                "MIDI adapter %s needs aseqdump from alsa-utils to read input port %s",
                self.name,
                input_port,
            )
            self.running = True
            await self.bus.publish(
                AdapterStatusEvent(
                    source=self.name,
                    adapter=self.name,
                    status="started",
                    detail="MIDI input unavailable: install alsa-utils (aseqdump)",
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

    async def reload(self, config: AdapterConfig) -> None:
        """Restart ALSA listeners after a configuration change."""

        self.config = config
        if not self.running:
            return
        await self.stop()
        await self.start()

    async def stop(self) -> None:
        self.running = False
        if self._input_task is not None:
            self._input_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._input_task
            self._input_task = None

        if self._input_process is not None:
            if self._input_process.returncode is None:
                self._input_process.terminate()
                with contextlib.suppress(ProcessLookupError):
                    await asyncio.wait_for(self._input_process.wait(), timeout=1.0)
            self._input_process = None

        self._source_index = None
        self._last_connection_detail = None
        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status="stopped",
                detail="MIDI adapter stopped",
            )
        )

    def _load_source_index(self) -> MidiSourceIndex | None:
        library_id = str(self.config.options.get("midi_library", "")).strip()
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

        return build_source_index(library, resolve_library_port(self.config))

    def _refresh_port_addresses(self) -> None:
        """Re-resolve ALSA client:port addresses from configured port labels."""

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
            )
        )

    async def _input_loop(self) -> None:
        while self.running:
            self._refresh_port_addresses()
            if self._input_address is None:
                await self._publish_connection_status("waiting")
                await asyncio.sleep(PORT_WAIT_INTERVAL_SECONDS)
                continue

            await self._publish_connection_status("connected")
            try:
                await self._run_input_process(self._input_address)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception(
                    "MIDI adapter %s input loop failed for %s",
                    self.name,
                    self._input_address,
                )
            if self.running:
                await self._publish_connection_status("reconnecting")
                await asyncio.sleep(INPUT_RECONNECT_DELAY_SECONDS)

    async def _run_input_process(self, address: str) -> None:
        self._input_process = await asyncio.create_subprocess_exec(
            "aseqdump",
            "-p",
            address,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert self._input_process.stdout is not None

        while self.running:
            line = await self._input_process.stdout.readline()
            if not line:
                break
            await self._handle_input_line(line.decode("utf-8", errors="replace"))

        stderr_bytes = b""
        if self._input_process.stderr is not None:
            stderr_bytes = await self._input_process.stderr.read()
        return_code = await self._input_process.wait()
        self._input_process = None
        if return_code not in {0, None} and self.running:
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
            LOGGER.warning(
                "MIDI adapter %s aseqdump exited with code %s%s",
                self.name,
                return_code,
                f": {stderr}" if stderr else "",
            )

    async def _handle_input_line(self, line: str) -> None:
        parsed = parse_aseqdump_line(line)
        if parsed is None:
            return

        status, data = parsed
        if status == MIDI_TIMING_CLOCK:
            await self.bus.publish(MidiClockEvent(source=self.name))
            return

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
        output_address = self._resolve_output_address()
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

    async def send_test_message(self, status: int, data: tuple[int, ...]) -> None:
        output_address = self._resolve_output_address()
        if output_address is None:
            output_port = str(self.config.options.get("output_port", "")).strip()
            input_port = str(self.config.options.get("input_port", "")).strip()
            if output_port or input_port:
                raise OSError(
                    f"MIDI adapter {self.name} cannot resolve a writable ALSA output port "
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

    async def _emit_midi_output(
        self,
        output_address: str,
        event: MidiMessageEvent,
    ) -> None:
        await send_midi_message_to_port(output_address, event.status, event.data)
        await self.bus.publish(
            MidiMessageEvent(
                source=self.name,
                status=event.status,
                data=event.data,
                target=event.target,
                direction="output",
            )
        )
