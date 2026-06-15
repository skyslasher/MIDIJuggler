import asyncio

import pytest

from midijuggler.adapters.hid import (
    EV_ABS,
    EV_KEY,
    HidAdapter,
    HidInput,
    HidRawEvent,
    parse_hid_inputs,
)
from midijuggler.config import AdapterConfig
from midijuggler.datapoint.bridge import EventToDataPointBridge
from midijuggler.datapoint.store import DataPointStore
from midijuggler.eventbus import EventBus
from midijuggler.events import ControlEvent, HidEvent


@pytest.fixture
def fake_evdev_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    mapping = {
        "BTN_A": (EV_KEY, 304),
        "BTN_B": (EV_KEY, 305),
        "ABS_X": (EV_ABS, 0),
    }

    def resolve(name: str) -> tuple[int, int]:
        normalized = str(name).strip().upper()
        if normalized not in mapping:
            raise ValueError(f"unknown evdev code: {name!r}")
        return mapping[normalized]

    monkeypatch.setattr("midijuggler.adapters.hid.resolve_evdev_code", resolve)


class FakeHidReader:
    def __init__(
        self,
        *,
        initial: dict[tuple[int, int], int] | None = None,
        events: list[HidRawEvent] | None = None,
    ) -> None:
        self._initial = dict(initial or {})
        self._events = list(events or [])
        self.closed = False

    def read_one(self) -> HidRawEvent | None:
        if not self._events:
            return None
        return self._events.pop(0)

    def close(self) -> None:
        self.closed = True

    def initial_values(self) -> dict[tuple[int, int], int]:
        return dict(self._initial)


def test_parse_hid_inputs_uses_codes_as_control_names(
    fake_evdev_codes: None,
) -> None:
    inputs = parse_hid_inputs({"codes": ["BTN_A", "ABS_X"]})

    assert [hid_input.control for hid_input in inputs] == ["btn_a", "abs_x"]
    assert inputs[0].event_type == EV_KEY
    assert inputs[1].event_type == EV_ABS


def test_parse_hid_inputs_accepts_explicit_tables(fake_evdev_codes: None) -> None:
    inputs = parse_hid_inputs(
        {
            "inputs": [
                {"code": "BTN_A", "control": "button_a", "value_max": 1.0},
                {
                    "code": "ABS_X",
                    "control": "stick_x",
                    "value_min": -1.0,
                    "value_max": 1.0,
                },
            ]
        }
    )

    assert [(hid_input.control, hid_input.value_min, hid_input.value_max) for hid_input in inputs] == [
        ("button_a", 0.0, 1.0),
        ("stick_x", -1.0, 1.0),
    ]


def test_parse_hid_inputs_returns_empty_list_without_codes(fake_evdev_codes: None) -> None:
    assert parse_hid_inputs({}) == []


def test_hid_adapter_publishes_initial_events_on_start(fake_evdev_codes: None) -> None:
    async def scenario() -> list[HidEvent]:
        bus = EventBus()
        events: list[HidEvent] = []
        bus.subscribe(HidEvent, lambda event: events.append(event))

        reader = FakeHidReader(initial={(EV_KEY, 304): 1})
        adapter = HidAdapter(
            name="gamepad",
            config=AdapterConfig(
                enabled=True,
                options={"device": "/dev/input/event0", "codes": ["BTN_A"]},
            ),
            bus=bus,
            reader_factory=lambda _device_path, _inputs: reader,
        )

        await adapter.start()
        await adapter.stop()
        return events

    events = asyncio.run(scenario())

    assert len(events) == 1
    assert events[0].source == "gamepad"
    assert events[0].control == "btn_a"
    assert events[0].code == "BTN_A"
    assert events[0].value == pytest.approx(1.0)
    assert events[0].initial is True


def test_hid_adapter_publishes_control_events_for_button_press(
    fake_evdev_codes: None,
) -> None:
    async def scenario() -> tuple[list[object], FakeHidReader]:
        bus = EventBus()
        events: list[object] = []
        bus.subscribe(HidEvent, lambda event: events.append(event))
        bus.subscribe(ControlEvent, lambda event: events.append(event))

        reader = FakeHidReader(
            initial={(EV_KEY, 304): 0},
            events=[HidRawEvent(EV_KEY, 304, 1)],
        )
        adapter = HidAdapter(
            name="gamepad",
            config=AdapterConfig(
                enabled=True,
                options={"device": "/dev/input/event0", "codes": ["BTN_A"]},
            ),
            bus=bus,
            reader_factory=lambda _device_path, _inputs: reader,
        )

        await adapter.start()
        for _ in range(50):
            hid_count = sum(1 for event in events if isinstance(event, HidEvent))
            if hid_count >= 2:
                break
            await asyncio.sleep(0.002)
        await adapter.stop()
        return events, reader

    events, reader = asyncio.run(scenario())

    assert reader.closed is True
    hid_events = [event for event in events if isinstance(event, HidEvent)]
    control_events = [event for event in events if isinstance(event, ControlEvent)]

    assert len(hid_events) == 2
    assert hid_events[0].initial is True
    assert hid_events[1].initial is False
    assert hid_events[1].value == pytest.approx(1.0)
    assert len(control_events) == 2
    assert control_events[1].control == "btn_a"


def test_hid_adapter_normalizes_axis_values(fake_evdev_codes: None) -> None:
    bus = EventBus()
    adapter = HidAdapter(
        name="gamepad",
        config=AdapterConfig(
            enabled=True,
            options={"device": "/dev/input/event0", "codes": ["ABS_X"]},
        ),
        bus=bus,
        reader_factory=lambda _device_path, _inputs: FakeHidReader(),
    )
    adapter._abs_ranges[(EV_ABS, 0)] = (0, 255)
    hid_input = adapter.inputs[0]

    assert adapter._normalize_value(hid_input, 0) == pytest.approx(0.0)
    assert adapter._normalize_value(hid_input, 128) == pytest.approx(128 / 255, rel=1e-3)
    assert adapter._normalize_value(hid_input, 255) == pytest.approx(1.0)


def test_hid_adapter_starts_without_mapped_inputs(fake_evdev_codes: None) -> None:
    async def scenario() -> None:
        bus = EventBus()
        adapter = HidAdapter(
            name="gamepad",
            config=AdapterConfig(
                enabled=True,
                options={"device": "/dev/input/event0"},
            ),
            bus=bus,
            reader_factory=lambda _device_path, _inputs: FakeHidReader(),
        )
        await adapter.start()
        assert adapter.running is True
        assert adapter.inputs == []
        await adapter.stop()

    asyncio.run(scenario())


def test_hid_adapter_publishes_learn_events(fake_evdev_codes: None) -> None:
    async def scenario() -> list[HidLearnEvent]:
        from midijuggler.events import HidLearnEvent

        bus = EventBus()
        events: list[HidLearnEvent] = []
        bus.subscribe(HidLearnEvent, lambda event: events.append(event))

        reader = FakeHidReader(events=[HidRawEvent(EV_KEY, 304, 1)])
        adapter = HidAdapter(
            name="gamepad",
            config=AdapterConfig(
                enabled=True,
                options={
                    "device": "/dev/input/event0",
                    "inputs": [{"code": "BTN_B", "control": "btn_b"}],
                },
            ),
            bus=bus,
            reader_factory=lambda _device_path, _inputs: reader,
        )

        await adapter.start()
        await adapter.set_learn_active(True)
        for _ in range(50):
            if events:
                break
            await asyncio.sleep(0.002)
        await adapter.set_learn_active(False)
        await adapter.stop()
        return events

    events = asyncio.run(scenario())
    assert len(events) == 1
    assert events[0].code == "type1_code304"
    assert events[0].suggested_control == "type1_code304"


def test_hid_control_events_update_datapoint_store(fake_evdev_codes: None) -> None:
    async def scenario() -> float | None:
        bus = EventBus()
        store = DataPointStore()
        bridge = EventToDataPointBridge(store, bus)
        bridge.attach()

        reader = FakeHidReader(
            initial={(EV_KEY, 304): 0},
            events=[HidRawEvent(EV_KEY, 304, 1)],
        )
        adapter = HidAdapter(
            name="gamepad",
            config=AdapterConfig(
                enabled=True,
                options={"device": "/dev/input/event0", "codes": ["BTN_A"]},
            ),
            bus=bus,
            reader_factory=lambda _device_path, _inputs: reader,
        )

        await adapter.start()
        for _ in range(50):
            value = store.float_value("gamepad.btn_a")
            if value == pytest.approx(1.0):
                break
            await asyncio.sleep(0.002)
        await adapter.stop()
        return store.float_value("gamepad.btn_a")

    value = asyncio.run(scenario())
    assert value == pytest.approx(1.0)
