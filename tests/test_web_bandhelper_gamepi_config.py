import asyncio
from pathlib import Path

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import load_config, parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.modules.interface.bandhelper.module import BandHelperModule
from midijuggler.modules.interface.gamepi_brightness import GamePiBrightnessModule
from midijuggler.web.server import WebInterface


def test_bandhelper_config_payload_includes_status() -> None:
    config = parse_config(
        {
            "bandhelper": {
                "enabled": True,
                "link_enabled": True,
                "start_bpm": 96.0,
            }
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )
    payload = interface.bandhelper_config_payload()
    assert payload["enabled"] is True
    assert payload["start_bpm"] == 96.0
    assert payload["module_active"] is False
    assert "status" in payload


def test_apply_bandhelper_config_persists(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [bandhelper]
        enabled = false
        start_bpm = 120.0
        """,
        encoding="utf-8",
    )
    config = load_config(config_file)
    store = DataPointStore()
    bus = EventBus()
    master_clock = MasterClock(config.master_clock, bus)
    module = BandHelperModule(store, config.bandhelper, master_clock, bus)
    interface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        master_clock,
        config_path=config_file,
    )
    interface.bind_bandhelper_module(module)

    result = asyncio.run(
        interface.apply_bandhelper_config(
            {
                "enabled": True,
                "min_bpm_delta": 1.0,
            }
        )
    )

    saved = load_config(config_file)
    assert result["persisted"] is True
    assert saved.bandhelper.enabled is True
    assert saved.bandhelper.min_bpm_delta == 1.0
    assert module.config.enabled is True


def test_gamepi_config_payload_includes_brightness() -> None:
    config = parse_config(
        {
            "gamepi": {
                "enabled": True,
                "kiosk_url": "http://127.0.0.1:8080/static/clock-gamepi.html",
            }
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )
    payload = interface.gamepi_config_payload()
    assert payload["enabled"] is True
    assert payload["kiosk_url"].endswith("clock-gamepi.html")
    assert "brightness" in payload


def test_apply_gamepi_config_persists_and_updates_module(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [gamepi]
        enabled = true
        brightness_poll_sec = 0.5
        """,
        encoding="utf-8",
    )
    config = load_config(config_file)
    store = DataPointStore()
    module = GamePiBrightnessModule(store, config=config.gamepi)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        config_path=config_file,
    )
    interface.bind_gamepi_module(module)

    result = asyncio.run(
        interface.apply_gamepi_config(
            {
                "brightness_poll_sec": 1.0,
                "kiosk_url": "http://127.0.0.1:8080/static/clock-gamepi.html",
            }
        )
    )

    saved = load_config(config_file)
    assert result["persisted"] is True
    assert saved.gamepi.brightness_poll_sec == 1.0
    assert module.config.brightness_poll_sec == 1.0
