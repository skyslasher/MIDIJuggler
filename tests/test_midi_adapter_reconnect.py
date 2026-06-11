import asyncio

from midijuggler.adapters.midi import (
    INPUT_RECONNECT_DELAY_SECONDS,
    PORT_WAIT_INTERVAL_SECONDS,
    MidiAdapter,
)
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import AdapterStatusEvent


def test_refresh_port_addresses_tracks_replugged_client(monkeypatch) -> None:
    addresses = iter(["20:0", None, "24:0"])

    monkeypatch.setattr(
        "midijuggler.adapters.midi.resolve_midi_input_port_address",
        lambda _name: next(addresses, None),
    )
    monkeypatch.setattr(
        "midijuggler.adapters.midi.MidiAdapter._resolve_output_address",
        lambda self: self._input_address,
    )

    adapter = MidiAdapter(
        "xtouch",
        AdapterConfig(
            enabled=True,
            kind="midi",
            options={"input_port": "X-TOUCH MINI MIDI 1"},
        ),
        EventBus(),
    )

    adapter._refresh_port_addresses()
    assert adapter._input_address == "20:0"

    adapter._refresh_port_addresses()
    assert adapter._input_address is None

    adapter._refresh_port_addresses()
    assert adapter._input_address == "24:0"


def test_start_supervises_input_even_when_port_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "midijuggler.adapters.midi.resolve_midi_input_port_address",
        lambda _name: None,
    )
    monkeypatch.setattr("midijuggler.adapters.midi.mido_available", lambda: True)

    async def scenario() -> MidiAdapter:
        adapter = MidiAdapter(
            "xtouch",
            AdapterConfig(
                enabled=True,
                kind="midi",
                options={"input_port": "X-TOUCH MINI MIDI 1"},
            ),
            EventBus(),
        )
        await adapter.start()
        return adapter

    adapter = asyncio.run(scenario())

    assert adapter.running is True
    assert adapter._input_task is not None
    asyncio.run(adapter.stop())


def test_input_loop_waits_then_connects(monkeypatch) -> None:
    resolve_calls = 0
    run_calls: list[str] = []

    def fake_resolve(_name: str) -> str | None:
        nonlocal resolve_calls
        resolve_calls += 1
        if resolve_calls < 3:
            return None
        return "24:0"

    async def fake_run(self, address: str) -> None:
        run_calls.append(address)
        self.running = False

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(
        "midijuggler.adapters.midi.resolve_midi_input_port_address",
        fake_resolve,
    )
    monkeypatch.setattr(
        "midijuggler.adapters.midi.MidiAdapter._run_mido_input",
        fake_run,
    )
    monkeypatch.setattr("midijuggler.adapters.midi.asyncio.sleep", fake_sleep)

    adapter = MidiAdapter(
        "xtouch",
        AdapterConfig(
            enabled=True,
            kind="midi",
            options={"input_port": "X-TOUCH MINI MIDI 1"},
        ),
        EventBus(),
    )
    adapter.running = True

    asyncio.run(adapter._input_loop())

    assert resolve_calls >= 3
    assert run_calls == ["24:0"]
    assert PORT_WAIT_INTERVAL_SECONDS in sleeps
    assert INPUT_RECONNECT_DELAY_SECONDS not in sleeps


def test_input_loop_reconnects_after_process_exit(monkeypatch) -> None:
    run_calls: list[str] = []

    monkeypatch.setattr(
        "midijuggler.adapters.midi.resolve_midi_input_port_address",
        lambda _name: "20:0",
    )

    async def fake_run(self, address: str) -> None:
        run_calls.append(address)
        if len(run_calls) >= 2:
            self.running = False

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(
        "midijuggler.adapters.midi.MidiAdapter._run_mido_input",
        fake_run,
    )
    monkeypatch.setattr("midijuggler.adapters.midi.asyncio.sleep", fake_sleep)

    adapter = MidiAdapter(
        "xtouch",
        AdapterConfig(
            enabled=True,
            kind="midi",
            options={"input_port": "X-TOUCH MINI MIDI 1"},
        ),
        EventBus(),
    )
    adapter.running = True

    asyncio.run(adapter._input_loop())

    assert run_calls == ["20:0", "20:0"]
    assert INPUT_RECONNECT_DELAY_SECONDS in sleeps


def test_publish_connection_status_avoids_duplicate_events() -> None:
    async def scenario() -> list[str]:
        statuses: list[str] = []

        bus = EventBus()
        phases: list[str] = []

        def capture(event: AdapterStatusEvent) -> None:
            statuses.append(event.detail)
            phases.append(event.connection_phase)

        bus.subscribe(AdapterStatusEvent, capture)

        adapter = MidiAdapter(
            "xtouch",
            AdapterConfig(
                enabled=True,
                kind="midi",
                options={"input_port": "X-TOUCH MINI MIDI 1"},
            ),
            bus,
        )
        adapter._input_address = None

        await adapter._publish_connection_status("waiting", force=True)
        await adapter._publish_connection_status("waiting")
        await adapter._publish_connection_status("reconnecting")
        return statuses, phases

    statuses, phases = asyncio.run(scenario())

    assert statuses == [
        "MIDI adapter waiting for input X-TOUCH MINI MIDI 1",
        "MIDI adapter reconnecting input X-TOUCH MINI MIDI 1",
    ]
    assert phases == ["waiting", "reconnecting"]
