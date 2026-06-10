import asyncio
import os
from pathlib import Path

import pytest

import midijuggler.adapters.gpio as gpio_module
from midijuggler.adapters.gpio import (
    GpioAdapter,
    SysfsGpioPinReader,
    _write_sysfs_file,
    parse_gpio_inputs,
)
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import ControlEvent


class FakePinReader:
    def __init__(self, state: bool) -> None:
        self.state = state
        self.closed = False

    def read(self) -> bool:
        return self.state

    def close(self) -> None:
        self.closed = True


def test_parse_gpio_inputs_uses_pin_list_as_configurable_input_count() -> None:
    inputs = parse_gpio_inputs(
        {"pins": [17, 27, 22], "active_low": True, "bounce_ms": 25}
    )

    assert [gpio_input.pin for gpio_input in inputs] == [17, 27, 22]
    assert [gpio_input.control for gpio_input in inputs] == ["pin17", "pin27", "pin22"]
    assert all(gpio_input.active_low for gpio_input in inputs)
    assert inputs[0].bounce_seconds == pytest.approx(0.025)


def test_parse_gpio_inputs_accepts_named_input_tables() -> None:
    inputs = parse_gpio_inputs(
        {
            "inputs": [
                {"pin": 17, "control": "left", "bounce_ms": 10},
                {"pin": 27, "name": "right", "active_low": False},
            ]
        }
    )

    assert [(gpio_input.pin, gpio_input.control) for gpio_input in inputs] == [
        (17, "left"),
        (27, "right"),
    ]
    assert inputs[0].bounce_seconds == pytest.approx(0.010)
    assert inputs[1].active_low is False


def test_parse_gpio_inputs_rejects_missing_pins() -> None:
    with pytest.raises(ValueError, match="at least one"):
        parse_gpio_inputs({})


def test_write_sysfs_file_does_not_open_with_truncate(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, object]] = []

    def fake_open(path: Path, flags: int) -> int:
        calls.append(("open", path, flags))
        return 123

    def fake_write(fd: int, value: bytes) -> int:
        calls.append(("write", fd, value))
        return len(value)

    def fake_close(fd: int) -> None:
        calls.append(("close", fd))

    monkeypatch.setattr(os, "open", fake_open)
    monkeypatch.setattr(os, "write", fake_write)
    monkeypatch.setattr(os, "close", fake_close)

    _write_sysfs_file(Path("/sys/class/gpio/export"), "17")

    assert calls[0] == ("open", Path("/sys/class/gpio/export"), os.O_WRONLY)
    assert calls[0][2] & os.O_TRUNC == 0
    assert calls[1] == ("write", 123, b"17\n")
    assert calls[2] == ("close", 123)


def test_sysfs_reader_falls_back_to_gpiochip_base_for_bcm_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_path = tmp_path / "gpio"
    chip_path = base_path / "gpiochip512"
    chip_path.mkdir(parents=True)
    (chip_path / "base").write_text("512", encoding="ascii")
    (chip_path / "ngpio").write_text("54", encoding="ascii")
    (base_path / "export").write_text("", encoding="ascii")
    (base_path / "unexport").write_text("", encoding="ascii")

    writes: list[tuple[Path, str]] = []

    def fake_write_sysfs_file(path: Path, value: str) -> None:
        writes.append((path, value))
        if path == base_path / "export" and value == "17":
            raise OSError(22, "Invalid argument")
        if path == base_path / "export" and value == "529":
            gpio_path = base_path / "gpio529"
            gpio_path.mkdir()
            (gpio_path / "direction").write_text("", encoding="ascii")
            (gpio_path / "value").write_text("1", encoding="ascii")

    monkeypatch.setattr(gpio_module, "_write_sysfs_file", fake_write_sysfs_file)

    reader = SysfsGpioPinReader(17, base_path=base_path)

    assert reader.sysfs_pin == 529
    assert reader.read() is True
    assert writes == [
        (base_path / "export", "17"),
        (base_path / "export", "529"),
        (base_path / "gpio529" / "direction", "in"),
    ]


def test_sysfs_reader_skips_direction_write_when_already_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_path = tmp_path / "gpio"
    gpio_path = base_path / "gpio17"
    gpio_path.mkdir(parents=True)
    (gpio_path / "direction").write_text("in", encoding="ascii")
    (gpio_path / "value").write_text("0", encoding="ascii")

    def fail_write_sysfs_file(path: Path, value: str) -> None:
        raise AssertionError("direction should not be rewritten")

    monkeypatch.setattr(gpio_module, "_write_sysfs_file", fail_write_sysfs_file)

    reader = SysfsGpioPinReader(17, base_path=base_path)

    assert reader.sysfs_pin == 17
    assert reader.read() is False


def test_sysfs_reader_continues_when_direction_denied_but_value_readable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_path = tmp_path / "gpio"
    gpio_path = base_path / "gpio17"
    gpio_path.mkdir(parents=True)
    (gpio_path / "direction").write_text("out", encoding="ascii")
    (gpio_path / "value").write_text("1", encoding="ascii")

    def fake_write_sysfs_file(path: Path, value: str) -> None:
        if path == gpio_path / "direction":
            raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(gpio_module, "_write_sysfs_file", fake_write_sysfs_file)

    reader = SysfsGpioPinReader(17, base_path=base_path)

    assert reader.sysfs_pin == 17
    assert reader.read() is True


def test_gpio_adapter_publishes_debounced_active_low_events() -> None:
    async def scenario() -> tuple[list[ControlEvent], FakePinReader]:
        bus = EventBus()
        events: list[ControlEvent] = []
        bus.subscribe(ControlEvent, lambda event: events.append(event))

        reader = FakePinReader(state=True)
        adapter = GpioAdapter(
            name="gpio",
            config=AdapterConfig(
                enabled=True,
                options={
                    "pins": [17],
                    "active_low": True,
                    "bounce_ms": 0,
                    "poll_interval_ms": 1,
                },
            ),
            bus=bus,
            reader_factory=lambda gpio_input: reader,
        )

        await adapter.start()
        reader.state = False
        for _ in range(20):
            if events:
                break
            await asyncio.sleep(0.002)
        await adapter.stop()
        return events, reader

    events, reader = asyncio.run(scenario())

    assert reader.closed is True
    assert len(events) == 1
    assert events[0].source == "gpio"
    assert events[0].control == "pin17"
    assert events[0].value == pytest.approx(1.0)


def test_gpio_adapter_can_reconfigure_inputs_at_runtime() -> None:
    async def scenario() -> tuple[GpioAdapter, FakePinReader, FakePinReader]:
        bus = EventBus()
        readers = {
            17: FakePinReader(state=True),
            27: FakePinReader(state=False),
        }
        adapter = GpioAdapter(
            name="gpio",
            config=AdapterConfig(
                enabled=True,
                options={
                    "pins": [17],
                    "active_low": True,
                    "bounce_ms": 25,
                    "poll_interval_ms": 5,
                },
            ),
            bus=bus,
            reader_factory=lambda gpio_input: readers[gpio_input.pin],
        )

        await adapter.start()
        await adapter.configure_options(
            {
                "pins": [27],
                "active_low": False,
                "bounce_ms": 10,
                "poll_interval_ms": 2,
            }
        )
        await adapter.stop()
        return adapter, readers[17], readers[27]

    adapter, old_reader, new_reader = asyncio.run(scenario())

    assert old_reader.closed is True
    assert new_reader.closed is True
    assert [gpio_input.pin for gpio_input in adapter.inputs] == [27]
    assert adapter.config.options["pins"] == [27]
    assert adapter.config.options["active_low"] is False
    assert adapter.config.options["bounce_ms"] == 10
    assert adapter.poll_interval_seconds == pytest.approx(0.002)
