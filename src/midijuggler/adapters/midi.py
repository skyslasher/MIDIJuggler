"""MIDI adapter using the ALSA sequencer on Linux."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil

from midijuggler.adapters.base import Adapter, MIDI_TIMING_CLOCK
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import AdapterStatusEvent, MidiClockEvent, MidiMessageEvent
from midijuggler.midi.alsa import parse_aseqdump_line
from midijuggler.system_info import resolve_midi_port_address

LOGGER = logging.getLogger(__name__)


class MidiAdapter(Adapter):
    protocol = "MIDI"

    def __init__(self, name: str, config: AdapterConfig, bus: EventBus) -> None:
        super().__init__(name, config, bus)
        self._input_address: str | None = None
        self._output_address: str | None = None
        self._input_task: asyncio.Task[None] | None = None
        self._input_process: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        input_port = str(self.config.options.get("input_port", "")).strip()
        output_port = str(self.config.options.get("output_port", "")).strip()
        self._input_address = (
            resolve_midi_port_address(input_port) if input_port else None
        )
        self._output_address = (
            resolve_midi_port_address(output_port) if output_port else None
        )

        if input_port and self._input_address is None:
            LOGGER.warning(
                "MIDI adapter %s cannot resolve input port %r; is the device connected?",
                self.name,
                input_port,
            )
        if output_port and self._output_address is None:
            LOGGER.warning(
                "MIDI adapter %s cannot resolve output port %r; is the device connected?",
                self.name,
                output_port,
            )

        if self._input_address is None and self._output_address is None:
            await self.bus.publish(
                AdapterStatusEvent(
                    source=self.name,
                    adapter=self.name,
                    status="started",
                    detail="MIDI adapter active without configured ALSA ports",
                )
            )
            self.running = True
            return

        if self._input_address is not None and shutil.which("aseqdump") is None:
            LOGGER.error(
                "MIDI adapter %s needs aseqdump from alsa-utils to read input port %s",
                self.name,
                input_port,
            )
            await self.bus.publish(
                AdapterStatusEvent(
                    source=self.name,
                    adapter=self.name,
                    status="started",
                    detail="MIDI input unavailable: install alsa-utils (aseqdump)",
                )
            )
            self.running = True
            return

        self.running = True
        if self._input_address is not None:
            self._input_task = asyncio.create_task(
                self._input_loop(),
                name=f"midi-input-{self.name}",
            )

        detail_parts = []
        if self._input_address is not None:
            detail_parts.append(f"input {input_port} ({self._input_address})")
        if self._output_address is not None:
            detail_parts.append(f"output {output_port} ({self._output_address})")
        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status="started",
                detail="MIDI adapter listening on " + ", ".join(detail_parts),
            )
        )

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

        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status="stopped",
                detail="MIDI adapter stopped",
            )
        )

    async def _input_loop(self) -> None:
        assert self._input_address is not None
        while self.running:
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
                await asyncio.sleep(1.0)

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


    async def send_midi_message(self, event: MidiMessageEvent) -> None:
        if self._output_address is None:
            await super().send_midi_message(event)
            return
        LOGGER.info(
            "MIDI adapter %s output to %s is not implemented yet: %s",
            self.name,
            self._output_address,
            event.as_dict(),
        )
