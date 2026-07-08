import asyncio

import pytest

from midijuggler.config import parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.eventbus import EventBus
from midijuggler.events import OscMessageEvent
from midijuggler.master_clock import MasterClock
from midijuggler.modules.interface.bandhelper.key import (
    parse_key,
    parse_key_mode,
    parse_key_root,
)
from midijuggler.modules.interface.bandhelper.module import BandHelperModule, SONG_MODULE


def test_parse_bandhelper_config() -> None:
    config = parse_config(
        {
            "bandhelper": {
                "enabled": True,
                "link_enabled": True,
                "start_bpm": 96.0,
                "min_bpm_delta": 1.0,
                "key_osc_address": "/midijuggler/song/key",
            }
        }
    )
    assert config.bandhelper.enabled is True
    assert config.bandhelper.start_bpm == 96.0
    assert config.bandhelper.min_bpm_delta == 1.0


@pytest.mark.parametrize(
    ("value", "root", "minor"),
    [
        ("C", 0, False),
        ("Am", 9, True),
        ("Bb", 10, False),
        ("F# minor", 6, True),
        ("Db major", 1, False),
    ],
)
def test_parse_key(value: str, root: int, minor: bool) -> None:
    parsed = parse_key(value)
    assert parsed is not None
    assert parsed.root == root
    assert parsed.minor is minor


def test_parse_key_root_and_mode_helpers() -> None:
    assert parse_key_root("Bb") == 10
    assert parse_key_root(6) == 6
    assert parse_key_mode("minor") is True
    assert parse_key_mode(0) is False


def test_bandhelper_module_publishes_key_from_osc() -> None:
    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "bandhelper": {"enabled": True, "link_enabled": False},
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = BandHelperModule(store, config.bandhelper, master_clock, bus)

    async def scenario() -> None:
        await module.start()
        await module._on_osc_message(
            OscMessageEvent(
                source="osc",
                address="/midijuggler/song/key",
                arguments=("Am",),
                direction="input",
            )
        )
        await module.stop()

    asyncio.run(scenario())

    snapshot = store.snapshot()
    assert snapshot[str(f"{SONG_MODULE}.key_root")]["int_value"] == 9
    assert snapshot[str(f"{SONG_MODULE}.key_minor")]["bool_value"] is True


def test_bandhelper_module_applies_link_tempo(monkeypatch: pytest.MonkeyPatch) -> None:
    config = parse_config(
        {
            "master_clock": {"enabled": True, "bpm": 120.0},
            "bandhelper": {
                "enabled": True,
                "link_enabled": False,
                "min_bpm_delta": 0.5,
            },
        }
    )
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = BandHelperModule(store, config.bandhelper, master_clock, bus)

    async def scenario() -> None:
        await module.start()
        await module._handle_link_tempo(132.4)
        await module.stop()

    asyncio.run(scenario())

    assert master_clock.bpm == 132.0
    snapshot = store.snapshot()
    assert snapshot[str(f"{SONG_MODULE}.link_tempo")]["float_value"] == pytest.approx(132.4)


def test_bandhelper_module_registers_datapoints() -> None:
    config = parse_config({"bandhelper": {"enabled": True}})
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    specs = {str(spec.id): spec for spec in BandHelperModule(store, config.bandhelper, master_clock, bus).datapoints()}
    assert f"{SONG_MODULE}.key_root" in specs
    assert f"{SONG_MODULE}.link_tempo" in specs
