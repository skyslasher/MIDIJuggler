import asyncio

import pytest

from midijuggler.adapters.gpio import GpioAdapter, parse_gpio_inputs
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
