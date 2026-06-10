import asyncio
from pathlib import Path

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import load_config, parse_config
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface


def test_osc_adapters_config_payload_lists_instances() -> None:
    config = parse_config(
        {
            "adapters": {
                "osc": {
                    "enabled": True,
                    "listen_port": 9000,
                },
                "x32_foh": {
                    "type": "osc",
                    "enabled": True,
                    "listen_host": "0.0.0.0",
                    "listen_port": 9100,
                    "remote_host": "192.168.10.32",
                    "remote_port": 10023,
                    "osc_library": "behringer_x32",
                },
                "midi": {"enabled": False},
            }
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    payload = interface.osc_adapters_config_payload()

    assert [instance["name"] for instance in payload["instances"]] == ["osc", "x32_foh"]
    x32 = next(instance for instance in payload["instances"] if instance["name"] == "x32_foh")
    assert x32["remote_host"] == "192.168.10.32"
    assert x32["remote_port"] == 10023
    assert x32["osc_library"] == "behringer_x32"
    assert payload["available_osc_libraries"]
    x32 = next(instance for instance in payload["instances"] if instance["name"] == "x32_foh")
    assert x32["desk_mode"] == "x32"
    assert x32["osc_port"] == 10023


def test_apply_osc_adapters_config_normalizes_desk_ports(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.wing_foh]
        type = "osc"
        enabled = false
        listen_host = "0.0.0.0"
        listen_port = 9101
        remote_host = "192.168.10.48"
        remote_port = 2223
        osc_library = "behringer_wing"
        desk_proxy_mode = true
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
        interface.apply_osc_adapters_config(
            {
                "instances": [
                    {
                        "name": "wing_foh",
                        "enabled": True,
                        "listen_host": "0.0.0.0",
                        "osc_port": 2223,
                        "remote_host": "192.168.10.48",
                        "osc_library": "behringer_wing",
                        "desk_proxy_mode": True,
                        "desk_sync_on_connect": True,
                    }
                ]
            }
        )
    )

    wing = next(instance for instance in result["instances"] if instance["name"] == "wing_foh")
    saved = load_config(config_file)

    assert wing["listen_port"] == 2223
    assert wing["remote_port"] == 2223
    assert wing["desk_proxy_mode"] is True
    assert wing["desk_sync_on_connect"] is True
    assert saved.adapters["wing_foh"].options["desk_proxy_mode"] is True


def test_apply_osc_adapters_config_persists_sections(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.osc]
        enabled = true
        listen_port = 9000

        [adapters.x32_foh]
        type = "osc"
        enabled = false
        listen_host = "0.0.0.0"
        listen_port = 9100
        remote_host = "192.168.10.32"
        remote_port = 10023
        osc_library = "behringer_x32"
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
        interface.apply_osc_adapters_config(
            {
                "instances": [
                    {
                        "name": "x32_foh",
                        "enabled": True,
                        "listen_host": "127.0.0.1",
                        "listen_port": 9200,
                        "remote_host": "10.0.0.32",
                        "remote_port": 10024,
                        "osc_library": "behringer_x32",
                    }
                ]
            }
        )
    )

    saved = load_config(config_file)
    saved_text = config_file.read_text(encoding="utf-8")

    assert result["persisted"] is True
    assert saved.adapters["x32_foh"].enabled is True
    assert saved.adapters["x32_foh"].options["listen_host"] == "127.0.0.1"
    assert saved.adapters["x32_foh"].options["listen_port"] == 9200
    assert saved.adapters["x32_foh"].options["remote_host"] == "10.0.0.32"
    assert 'listen_host = "127.0.0.1"' in saved_text


def test_apply_osc_adapters_config_can_add_and_delete_instances(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.osc]
        enabled = true
        listen_port = 9000
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

    asyncio.run(
        interface.apply_osc_adapters_config(
            {
                "instances": [
                    {
                        "name": "desk_b",
                        "type": "osc",
                        "enabled": True,
                        "listen_host": "0.0.0.0",
                        "listen_port": 9300,
                        "remote_host": "192.168.1.50",
                        "remote_port": 10023,
                        "osc_library": "behringer_x32",
                    }
                ]
            }
        )
    )
    assert "desk_b" in load_config(config_file).adapters

    asyncio.run(
        interface.apply_osc_adapters_config(
            {
                "instances": [],
                "deleted": ["desk_b"],
            }
        )
    )

    reloaded = load_config(config_file)
    assert "desk_b" not in reloaded.adapters


def test_apply_osc_adapters_config_can_rename_instance(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.osc]
        enabled = true
        listen_port = 9000

        [adapters.x32_foh]
        type = "osc"
        enabled = true
        listen_host = "0.0.0.0"
        osc_port = 10023
        remote_host = "192.168.10.32"
        osc_library = "behringer_x32"
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
        interface.apply_osc_adapters_config(
            {
                "instances": [
                    {
                        "name": "foh_x32",
                        "previous_name": "x32_foh",
                        "enabled": True,
                        "listen_host": "0.0.0.0",
                        "osc_port": 10023,
                        "remote_host": "192.168.10.32",
                        "osc_library": "behringer_x32",
                    }
                ]
            }
        )
    )

    saved = load_config(config_file)
    saved_text = config_file.read_text(encoding="utf-8")

    assert result["persisted"] is True
    assert "x32_foh" not in saved.adapters
    assert saved.adapters["foh_x32"].enabled is True
    assert "[adapters.foh_x32]" in saved_text
    assert "[adapters.x32_foh]" not in saved_text
