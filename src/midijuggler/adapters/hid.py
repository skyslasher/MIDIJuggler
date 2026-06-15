"""Linux evdev HID input adapter."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from midijuggler.adapters.base import Adapter
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import AdapterStatusEvent, ControlEvent, HidEvent, HidLearnEvent
from midijuggler.hid.codes import (
    evdev_code_name,
    keyboard_code_name,
    normalize_evdev_code_name,
    resolve_device_path,
    resolve_evdev_code,
)

LOGGER = logging.getLogger(__name__)
DEVICE_WAIT_INTERVAL_SECONDS = 2.0
DEVICE_RECONNECT_DELAY_SECONDS = 2.0

try:
    from evdev import InputDevice, ecodes

    EV_KEY = ecodes.EV_KEY
    EV_ABS = ecodes.EV_ABS
except ImportError:  # pragma: no cover - exercised via injected readers in tests
    InputDevice = None  # type: ignore[misc, assignment]
    ecodes = None  # type: ignore[misc, assignment]
    EV_KEY = 0x01
    EV_ABS = 0x03


@dataclass(frozen=True)
class HidInput:
    """Runtime configuration for one mapped HID control."""

    control: str
    event_type: int
    code: int
    code_name: str
    value_min: float
    value_max: float


@dataclass(frozen=True)
class HidRawEvent:
    event_type: int
    code: int
    value: int


class HidReader(Protocol):
    """Blocking HID reader used from a worker thread."""

    def read_one(self) -> HidRawEvent | None:
        """Return the next event or None when no event is available yet."""

    def close(self) -> None:
        """Release resources held by this reader."""

    def initial_values(self) -> dict[tuple[int, int], int]:
        """Return current values for configured controls."""


class EvdevHidReader:
    """Read HID events from a Linux evdev device node."""

    def __init__(self, device_path: str, *, grab: bool = False) -> None:
        if InputDevice is None:
            raise ImportError(
                "evdev is required for HID adapters. Install with: pip install 'midijuggler[hid]'"
            )
        self.device_path = device_path
        self.device = InputDevice(device_path)
        if grab:
            self.device.grab()

    def read_one(self) -> HidRawEvent | None:
        event = self.device.read_one()
        if event is None:
            return None
        return HidRawEvent(
            event_type=int(event.type),
            code=int(event.code),
            value=int(event.value),
        )

    def close(self) -> None:
        self.device.close()

    def initial_values(self) -> dict[tuple[int, int], int]:
        values: dict[tuple[int, int], int] = {}
        for key_code in self.device.active_keys():
            values[(EV_KEY, int(key_code))] = 1
        for code, absinfo in self.device.capabilities(absinfo=True).get(EV_ABS, []):
            values[(EV_ABS, int(code))] = int(absinfo.value)
        return values


HidReaderFactory = Callable[[str, list[HidInput]], HidReader]


class HidAdapter(Adapter):
    """Read Linux evdev HID devices and publish normalized control events."""

    protocol = "HID"

    def __init__(
        self,
        name: str,
        config: AdapterConfig,
        bus: EventBus,
        reader_factory: HidReaderFactory | None = None,
    ) -> None:
        super().__init__(name=name, config=config, bus=bus)
        self._reader_factory = reader_factory or self._default_reader_factory
        self._reader: HidReader | None = None
        self._read_task: asyncio.Task[None] | None = None
        self._abs_ranges: dict[tuple[int, int], tuple[int, int]] = {}
        self._lock = asyncio.Lock()
        self._learn_active = False
        self._last_connection_detail: str | None = None
        self.keystrokes = False
        self.grab_device = False
        self._apply_options(config.options)

    def _default_reader_factory(
        self,
        device_path: str,
        _inputs: list[HidInput],
    ) -> HidReader:
        return EvdevHidReader(device_path, grab=self.grab_device)

    def _apply_options(self, options: dict[str, Any]) -> None:
        normalized = dict(options)
        self.device_path = resolve_device_path(normalized)
        self.keystrokes = _parse_bool_option(normalized.get("keystrokes"), default=False)
        self.grab_device = _parse_bool_option(
            normalized.get("grab"),
            default=self.keystrokes,
        )
        self.inputs = parse_hid_inputs(normalized)
        self._input_index = {
            (hid_input.event_type, hid_input.code): hid_input for hid_input in self.inputs
        }
        self.config.options.clear()
        self.config.options.update(normalized)

    async def start(self) -> None:
        async with self._lock:
            self._reader = self._reader_factory(self.device_path, self.inputs)
            self._load_abs_ranges()

        self.running = True
        self._last_connection_detail = None
        if self.inputs:
            await self._publish_initial_states()
        self._read_task = asyncio.create_task(self._read_loop(), name=f"hid-{self.name}")
        await self._publish_connection_status("connected", force=True)

    async def stop(self) -> None:
        self.running = False
        self._learn_active = False
        if self._read_task is not None:
            self._read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._read_task
            self._read_task = None

        if self._reader is not None:
            self._reader.close()
            self._reader = None

        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status="stopped",
                detail="HID adapter stopped",
            )
        )

    def _connection_detail(self, phase: str) -> str:
        mapped = len(self.inputs)
        detail = f"HID device {self.device_path}"
        if mapped:
            detail += f" ({mapped} inputs)"
        else:
            detail += " (no inputs mapped yet; use learn mode)"
        if phase == "waiting":
            return f"waiting for {detail}"
        if phase == "reconnecting":
            return f"reconnecting to {detail}"
        return f"reading {detail}"

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

    def _refresh_device_path(self) -> None:
        with contextlib.suppress(ValueError, ImportError):
            self.device_path = resolve_device_path(self.config.options)

    async def _close_reader(self) -> None:
        async with self._lock:
            reader = self._reader
            self._reader = None
        if reader is not None:
            reader.close()

    async def _ensure_reader(self) -> bool:
        async with self._lock:
            if self._reader is not None:
                return True

        self._refresh_device_path()
        loop = asyncio.get_running_loop()
        try:
            reader = await loop.run_in_executor(
                None,
                lambda: self._reader_factory(self.device_path, self.inputs),
            )
        except OSError:
            return False

        async with self._lock:
            if not self.running:
                reader.close()
                return False
            self._reader = reader
            self._load_abs_ranges()

        await self._publish_connection_status("connected", force=True)
        if self.inputs:
            await self._publish_initial_states()
        return True

    async def _read_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while self.running:
            reader = self._reader
            if reader is None:
                if not await self._ensure_reader():
                    await self._publish_connection_status("waiting")
                    await asyncio.sleep(DEVICE_WAIT_INTERVAL_SECONDS)
                continue

            try:
                raw = await loop.run_in_executor(None, reader.read_one)
            except OSError as exc:
                LOGGER.warning(
                    "HID device lost for %s (%s): %s",
                    self.name,
                    self.device_path,
                    exc,
                )
                await self._close_reader()
                await self._publish_connection_status("reconnecting")
                await asyncio.sleep(DEVICE_RECONNECT_DELAY_SECONDS)
                continue

            if raw is None:
                await asyncio.sleep(0.001)
                continue
            await self._handle_raw_event(raw)

    async def set_learn_active(self, active: bool) -> None:
        self._learn_active = active

    async def reload(self, config: AdapterConfig) -> None:
        self.config = config
        if self.running:
            await self.stop()
        self._apply_options(config.options)
        if config.enabled:
            await self.start()

    async def configure_options(self, options: dict[str, Any]) -> None:
        """Apply a new HID configuration at runtime."""

        was_running = self.running
        if was_running:
            await self.stop()
        self._apply_options(options)
        if was_running and self.config.enabled:
            await self.start()
        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status="configured",
                detail=(
                    f"watching HID device {self.device_path} "
                    f"({len(self.inputs)} inputs)"
                ),
            )
        )

    async def _handle_raw_event(self, raw: HidRawEvent) -> None:
        await self._maybe_publish_learn(raw)
        hid_input = self._resolve_hid_input(raw)
        if hid_input is None:
            return
        value = self._normalize_value(hid_input, raw.value)
        await self._publish_input_state(hid_input, value)

    def _resolve_hid_input(self, raw: HidRawEvent) -> HidInput | None:
        hid_input = self._input_index.get((raw.event_type, raw.code))
        if hid_input is not None:
            return hid_input
        if raw.event_type != EV_KEY or raw.value == 0:
            return None
        code_name = keyboard_code_name(raw.event_type, raw.code)
        if code_name is None:
            return None
        if self.keystrokes or self._learn_active:
            return self._ephemeral_input(raw, code_name)
        return None

    def _ephemeral_input(self, raw: HidRawEvent, code_name: str | None = None) -> HidInput:
        resolved_name = code_name or keyboard_code_name(raw.event_type, raw.code)
        if resolved_name is None:
            resolved_name = self._resolve_code_name(raw.event_type, raw.code)
        return HidInput(
            control=_default_control_name(resolved_name),
            event_type=raw.event_type,
            code=raw.code,
            code_name=resolved_name,
            value_min=0.0,
            value_max=1.0,
        )

    async def _maybe_publish_learn(self, raw: HidRawEvent) -> None:
        if not self._learn_active:
            return
        if raw.event_type == EV_KEY and raw.value == 0:
            return

        code_name = self._resolve_code_name(raw.event_type, raw.code)
        suggested_control = _default_control_name(code_name)
        value = float(raw.value)
        if raw.event_type == EV_KEY:
            value = 1.0

        await self.bus.publish(
            HidLearnEvent(
                source=self.name,
                code=code_name,
                event_type=raw.event_type,
                evdev_code=raw.code,
                value=value,
                suggested_control=suggested_control,
            )
        )

    def _resolve_code_name(self, event_type: int, code: int) -> str:
        try:
            return evdev_code_name(event_type, code)
        except ImportError:
            return f"type{event_type}_code{code}"

    async def _publish_initial_states(self) -> None:
        reader = self._reader
        if reader is None:
            return
        for (event_type, code), raw_value in reader.initial_values().items():
            hid_input = self._input_index.get((event_type, code))
            if hid_input is None:
                continue
            value = self._normalize_value(hid_input, raw_value)
            await self._publish_input_state(hid_input, value, initial=True)

    async def _publish_input_state(
        self,
        hid_input: HidInput,
        value: float,
        *,
        initial: bool = False,
    ) -> None:
        await self.bus.publish(
            HidEvent(
                source=self.name,
                control=hid_input.control,
                value=value,
                code=hid_input.code_name,
                initial=initial,
            )
        )
        await self.bus.publish(
            ControlEvent(
                source=self.name,
                control=hid_input.control,
                value=value,
            )
        )

    def _normalize_value(self, hid_input: HidInput, raw_value: int) -> float:
        if hid_input.event_type == EV_KEY:
            return hid_input.value_max if raw_value else hid_input.value_min

        axis_range = self._abs_ranges.get((hid_input.event_type, hid_input.code))
        if axis_range is None:
            return float(raw_value)
        axis_min, axis_max = axis_range
        if axis_max == axis_min:
            return hid_input.value_min
        ratio = (raw_value - axis_min) / (axis_max - axis_min)
        return hid_input.value_min + ratio * (hid_input.value_max - hid_input.value_min)

    def _load_abs_ranges(self) -> None:
        self._abs_ranges.clear()
        if not isinstance(self._reader, EvdevHidReader):
            return
        for code, absinfo in self._reader.device.capabilities(absinfo=True).get(
            EV_ABS,
            [],
        ):
            self._abs_ranges[(EV_ABS, int(code))] = (
                int(absinfo.min),
                int(absinfo.max),
            )

    def config_payload(self) -> dict[str, Any]:
        return {
            "device": self.device_path,
            "keystrokes": self.keystrokes,
            "grab": self.grab_device,
            "inputs": [
                {
                    "code": hid_input.code_name,
                    "control": hid_input.control,
                    "value_min": hid_input.value_min,
                    "value_max": hid_input.value_max,
                }
                for hid_input in self.inputs
            ],
        }


def parse_hid_inputs(options: dict[str, Any]) -> list[HidInput]:
    """Parse HID input configuration.

    Supported compact form::

        codes = ["BTN_A", "ABS_X"]

    Supported explicit form::

        inputs = [{ code = "BTN_A", control = "button_a" }]
    """

    if "inputs" in options:
        raw_inputs = options["inputs"]
        if not isinstance(raw_inputs, list):
            raise ValueError("HID option 'inputs' must be a list")
        inputs = [
            _parse_explicit_input(raw_input, index)
            for index, raw_input in enumerate(raw_inputs, start=1)
        ]
    else:
        raw_codes = options.get("codes", [])
        if not isinstance(raw_codes, list):
            raise ValueError("HID option 'codes' must be a list")
        inputs = [
            _parse_compact_input(code, index) for index, code in enumerate(raw_codes)
        ]

    if not inputs:
        return []

    controls = [hid_input.control for hid_input in inputs]
    if len(controls) != len(set(controls)):
        raise ValueError("HID controls must be unique")

    keys = [(hid_input.event_type, hid_input.code) for hid_input in inputs]
    if len(keys) != len(set(keys)):
        raise ValueError("HID input codes must be unique")

    return inputs


def _parse_compact_input(raw_code: Any, index: int) -> HidInput:
    code_name = normalize_evdev_code_name(str(raw_code))
    if not code_name:
        raise ValueError(f"HID codes[{index}] must not be empty")
    event_type, code = resolve_evdev_code(code_name)
    return HidInput(
        control=_default_control_name(code_name),
        event_type=event_type,
        code=code,
        code_name=code_name,
        value_min=_default_value_min(event_type),
        value_max=_default_value_max(event_type),
    )


def _parse_explicit_input(raw_input: Any, index: int) -> HidInput:
    if not isinstance(raw_input, dict):
        raise ValueError(f"HID inputs[{index}] must be a table")
    if "code" not in raw_input:
        raise ValueError(f"HID inputs[{index}] missing required field: code")

    code_name = normalize_evdev_code_name(str(raw_input["code"]))
    event_type, code = resolve_evdev_code(code_name)
    control = str(raw_input.get("control") or raw_input.get("name") or "").strip()
    if not control:
        control = _default_control_name(code_name)

    value_min = float(raw_input.get("value_min", _default_value_min(event_type)))
    value_max = float(raw_input.get("value_max", _default_value_max(event_type)))
    if value_max < value_min:
        raise ValueError(f"HID inputs[{index}].value_max must be >= value_min")

    return HidInput(
        control=control,
        event_type=event_type,
        code=code,
        code_name=code_name,
        value_min=value_min,
        value_max=value_max,
    )


def _default_control_name(code_name: str) -> str:
    return code_name.lower()


def _default_value_min(event_type: int) -> float:
    if event_type == EV_KEY:
        return 0.0
    return 0.0


def _default_value_max(event_type: int) -> float:
    if event_type == EV_KEY:
        return 1.0
    return 1.0


def _parse_bool_option(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"invalid boolean HID option: {value!r}")
