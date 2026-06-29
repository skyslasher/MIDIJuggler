import asyncio
from pathlib import Path

import pytest

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import load_config, parse_config
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface


def test_gpio_config_payload_marks_configured_pins() -> None:
    config = parse_config(
        {
            "adapters": {
                "gpio": {
                    "enabled": True,
                    "pins": [17, 22],
                    "active_low": True,
                    "bounce_ms": 25,
                    "poll_interval_ms": 5,
                }
            }
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    payload = interface.gpio_config_payload()
    enabled_pins = [
        pin["pin"]
        for pin in payload["pins"]
        if pin["enabled"]
    ]

    assert enabled_pins == [17, 22]
    assert payload["name"] == "gpio"
    assert payload["active_low"] is True
    assert payload["bounce_ms"] == 25


def test_apply_gpio_config_persists_gpio_section(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [web]
        port = 8080

        [adapters.gpio]
        enabled = true
        pins = [17]
        active_low = true
        bounce_ms = 25
        poll_interval_ms = 5
        """,
        encoding="utf-8",
    )
    config = load_config(config_file)
    bus = EventBus()
    interface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        MasterClock(config.master_clock, bus),
        config_path=config_file,
    )

    result = asyncio.run(
        interface.apply_gpio_config(
            {
                "pins": [22, 27],
                "active_low": False,
                "bounce_ms": 10,
                "poll_interval_ms": 2,
            }
        )
    )

    saved = load_config(config_file)
    enabled_pins = [pin["pin"] for pin in result["pins"] if pin["enabled"]]

    assert enabled_pins == [22, 27]
    assert saved.adapters["gpio"].options["pins"] == [22, 27]
    assert saved.adapters["gpio"].options["active_low"] is False


def test_apply_gpio_config_persists_display_name(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.gpio]
        enabled = true
        pins = [17]
        """,
        encoding="utf-8",
    )
    config = load_config(config_file)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        config_path=config_file,
    )

    result = asyncio.run(
        interface.apply_gpio_config(
            {
                "name": "Foot switches",
                "pins": [17],
                "active_low": True,
                "bounce_ms": 25,
                "poll_interval_ms": 5,
            }
        )
    )

    saved = load_config(config_file)

    assert result["name"] == "Foot switches"
    assert saved.adapters["gpio"].name == "Foot switches"
    assert 'name = "Foot switches"' in config_file.read_text(encoding="utf-8")


def test_apply_gpio_config_keeps_runtime_change_when_persisting_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.gpio]
        enabled = true
        pins = [17]
        """,
        encoding="utf-8",
    )
    config = load_config(config_file)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        config_path=config_file,
    )

    def deny_persist(path: str | Path, options: dict[str, object], *, name: str = "") -> None:
        raise PermissionError(13, "Permission denied", f"{path}.tmp")

    monkeypatch.setattr("midijuggler.web.server.save_gpio_adapter_options", deny_persist)

    result = asyncio.run(
        interface.apply_gpio_config(
            {
                "pins": [22],
                "active_low": True,
                "bounce_ms": 25,
                "poll_interval_ms": 5,
            }
        )
    )

    assert result["persisted"] is False
    assert "Permission denied" in result["persist_error"]
    assert config.adapters["gpio"].options["pins"] == [22]


def test_apply_gpio_config_rejects_unsupported_pins() -> None:
    config = parse_config({"adapters": {"gpio": {"enabled": True, "pins": [17]}}})
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    with pytest.raises(ValueError, match="unsupported"):
        asyncio.run(interface.apply_gpio_config({"pins": [99]}))
