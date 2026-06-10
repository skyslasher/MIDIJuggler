"""GPIO footswitch adapter."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from midijuggler.adapters.base import Adapter
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import AdapterStatusEvent, ControlEvent


class GpioPinReader(Protocol):
    """Read one physical GPIO pin as a raw high/low value."""

    def read(self) -> bool:
        """Return True for electrical high, False for electrical low."""

    def close(self) -> None:
        """Release resources held by this reader."""


@dataclass(frozen=True)
class GpioInput:
    """Runtime configuration for one GPIO footswitch input."""

    pin: int
    control: str
    active_low: bool
    bounce_seconds: float


@dataclass
class _DebounceState:
    stable: bool
    candidate: bool
    candidate_since: float


class SysfsGpioPinReader:
    """GPIO reader using Linux's sysfs GPIO interface.

    The interface is deprecated by the kernel in favor of character-device GPIO,
    but it remains widely available on lightweight Raspberry Pi installations and
    keeps this initial adapter dependency-free.
    """

    def __init__(self, pin: int, base_path: Path = Path("/sys/class/gpio")) -> None:
        self.pin = pin
        self.base_path = base_path
        self.gpio_path = self.base_path / f"gpio{pin}"
        self._exported_by_us = False

        if not self.gpio_path.exists():
            self._write_control("export", str(pin))
            self._exported_by_us = True
            deadline = time.monotonic() + 1.0
            while not self.gpio_path.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not self.gpio_path.exists():
                raise RuntimeError(f"GPIO sysfs path was not created for pin {pin}")

        direction_path = self.gpio_path / "direction"
        if direction_path.exists():
            direction_path.write_text("in", encoding="ascii")

    def read(self) -> bool:
        value = (self.gpio_path / "value").read_text(encoding="ascii").strip()
        if value not in {"0", "1"}:
            raise RuntimeError(f"unexpected GPIO value for pin {self.pin}: {value!r}")
        return value == "1"

    def close(self) -> None:
        if self._exported_by_us:
            with contextlib.suppress(OSError):
                self._write_control("unexport", str(self.pin))

    def _write_control(self, name: str, value: str) -> None:
        try:
            (self.base_path / name).write_text(value, encoding="ascii")
        except OSError as exc:
            raise RuntimeError(
                f"cannot access GPIO sysfs {name!r}; check DietPi GPIO support "
                "and service permissions"
            ) from exc


PinReaderFactory = Callable[[GpioInput], GpioPinReader]


class GpioAdapter(Adapter):
    """Poll configured GPIO pins and publish normalized control events."""

    protocol = "GPIO"

    def __init__(
        self,
        name: str,
        config: AdapterConfig,
        bus: EventBus,
        reader_factory: PinReaderFactory | None = None,
    ) -> None:
        super().__init__(name=name, config=config, bus=bus)
        self.inputs = parse_gpio_inputs(config.options)
        self.poll_interval_seconds = _milliseconds_to_seconds(
            config.options.get("poll_interval_ms", 5), "poll_interval_ms"
        )
        self._reader_factory = reader_factory or (
            lambda gpio_input: SysfsGpioPinReader(gpio_input.pin)
        )
        self._readers: dict[int, GpioPinReader] = {}
        self._states: dict[int, _DebounceState] = {}
        self._poll_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._readers = {
            gpio_input.pin: self._reader_factory(gpio_input)
            for gpio_input in self.inputs
        }
        now = asyncio.get_running_loop().time()
        self._states = {}
        for gpio_input in self.inputs:
            logical_value = self._logical_value(gpio_input)
            self._states[gpio_input.pin] = _DebounceState(
                stable=logical_value,
                candidate=logical_value,
                candidate_since=now,
            )

        self.running = True
        self._poll_task = asyncio.create_task(self._poll_loop(), name="gpio-poll")
        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status="started",
                detail=f"watching GPIO pins {', '.join(str(i.pin) for i in self.inputs)}",
            )
        )

    async def stop(self) -> None:
        self.running = False
        if self._poll_task is not None:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None

        for reader in self._readers.values():
            reader.close()
        self._readers.clear()
        self._states.clear()

        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status="stopped",
                detail="GPIO adapter stopped",
            )
        )

    async def _poll_loop(self) -> None:
        while self.running:
            await self._poll_once()
            await asyncio.sleep(self.poll_interval_seconds)

    async def _poll_once(self) -> None:
        now = asyncio.get_running_loop().time()
        for gpio_input in self.inputs:
            state = self._states[gpio_input.pin]
            logical_value = self._logical_value(gpio_input)

            if logical_value != state.candidate:
                state.candidate = logical_value
                state.candidate_since = now
                continue

            if (
                logical_value != state.stable
                and now - state.candidate_since >= gpio_input.bounce_seconds
            ):
                state.stable = logical_value
                await self.bus.publish(
                    ControlEvent(
                        source=self.name,
                        control=gpio_input.control,
                        value=1.0 if logical_value else 0.0,
                    )
                )

    def _logical_value(self, gpio_input: GpioInput) -> bool:
        raw_high = self._readers[gpio_input.pin].read()
        return not raw_high if gpio_input.active_low else raw_high


def parse_gpio_inputs(options: dict[str, Any]) -> list[GpioInput]:
    """Parse GPIO input configuration.

    Supported compact form:

    ``pins = [17, 27, 22]``

    Supported explicit form:

    ``inputs = [{ pin = 17, control = "footswitch_a" }]``
    """

    default_active_low = bool(options.get("active_low", True))
    default_bounce_seconds = _milliseconds_to_seconds(
        options.get("bounce_ms", 25), "bounce_ms"
    )

    if "inputs" in options:
        raw_inputs = options["inputs"]
        if not isinstance(raw_inputs, list):
            raise ValueError("GPIO option 'inputs' must be a list")
        inputs = [
            _parse_explicit_input(raw_input, index, default_active_low, default_bounce_seconds)
            for index, raw_input in enumerate(raw_inputs, start=1)
        ]
    else:
        raw_pins = options.get("pins", [])
        if not isinstance(raw_pins, list):
            raise ValueError("GPIO option 'pins' must be a list")
        inputs = [
            _parse_compact_input(
                pin,
                index,
                default_active_low,
                default_bounce_seconds,
            )
            for index, pin in enumerate(raw_pins)
        ]

    if not inputs:
        raise ValueError("GPIO adapter requires at least one configured pin")

    controls = [gpio_input.control for gpio_input in inputs]
    if len(controls) != len(set(controls)):
        raise ValueError("GPIO controls must be unique")

    pins = [gpio_input.pin for gpio_input in inputs]
    if len(pins) != len(set(pins)):
        raise ValueError("GPIO pins must be unique")

    return inputs


def _parse_compact_input(
    raw_pin: Any,
    index: int,
    default_active_low: bool,
    default_bounce_seconds: float,
) -> GpioInput:
    pin = _parse_pin(raw_pin, f"pins[{index}]")
    return GpioInput(
        pin=pin,
        control=f"pin{pin}",
        active_low=default_active_low,
        bounce_seconds=default_bounce_seconds,
    )


def _parse_explicit_input(
    raw_input: Any,
    index: int,
    default_active_low: bool,
    default_bounce_seconds: float,
) -> GpioInput:
    if not isinstance(raw_input, dict):
        raise ValueError(f"GPIO inputs[{index}] must be a table")
    if "pin" not in raw_input:
        raise ValueError(f"GPIO inputs[{index}] missing required field: pin")

    pin = _parse_pin(raw_input["pin"], f"inputs[{index}].pin")
    control = str(raw_input.get("control") or raw_input.get("name") or f"pin{pin}")
    return GpioInput(
        pin=pin,
        control=control,
        active_low=bool(raw_input.get("active_low", default_active_low)),
        bounce_seconds=_milliseconds_to_seconds(
            raw_input.get("bounce_ms", default_bounce_seconds * 1000),
            f"inputs[{index}].bounce_ms",
        ),
    )


def _parse_pin(value: Any, field_name: str) -> int:
    try:
        pin = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"GPIO {field_name} must be an integer") from exc
    if pin < 0:
        raise ValueError(f"GPIO {field_name} must be >= 0")
    return pin


def _milliseconds_to_seconds(value: Any, field_name: str) -> float:
    try:
        milliseconds = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"GPIO {field_name} must be a number") from exc
    if milliseconds < 0:
        raise ValueError(f"GPIO {field_name} must be >= 0")
    return milliseconds / 1000.0
