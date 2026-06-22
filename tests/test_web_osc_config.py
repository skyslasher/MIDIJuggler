import asyncio
import socket
from pathlib import Path

import pytest

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import load_config, parse_config
from midijuggler.datapoint.store import DataPointStore
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


def test_apply_osc_adapters_config_accepts_desk_mode_selection(tmp_path: Path) -> None:
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

    result = asyncio.run(
        interface.apply_osc_adapters_config(
            {
                "instances": [
                    {
                        "name": "wing_foh",
                        "enabled": True,
                        "desk_mode": "wing",
                        "remote_host": "192.168.10.48",
                        "desk_proxy_mode": True,
                    }
                ]
            }
        )
    )

    wing = next(instance for instance in result["instances"] if instance["name"] == "wing_foh")
    saved = load_config(config_file)

    assert wing["desk_mode"] == "wing"
    assert wing["osc_library"] == "behringer_wing"
    assert wing["listen_port"] == 2223
    assert saved.adapters["wing_foh"].options["osc_library"] == "behringer_wing"


def test_apply_osc_adapters_config_rejects_duplicate_listen_ports() -> None:
    config = parse_config(
        {
            "adapters": {
                "osc": {
                    "enabled": True,
                    "listen_port": 9000,
                },
                "wing_foh": {
                    "type": "osc",
                    "enabled": True,
                    "listen_port": 2223,
                    "remote_host": "192.168.10.48",
                    "remote_port": 2223,
                    "osc_library": "behringer_wing",
                },
                "wing_mon": {
                    "type": "osc",
                    "enabled": False,
                    "listen_port": 2223,
                    "remote_host": "192.168.10.48",
                    "remote_port": 2223,
                    "osc_library": "behringer_wing",
                },
            }
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    with pytest.raises(ValueError, match="OSC listen port 2223"):
        asyncio.run(
            interface.apply_osc_adapters_config(
                {
                    "instances": [
                        {
                            "name": "wing_mon",
                            "enabled": True,
                            "osc_port": 2223,
                            "remote_host": "192.168.10.48",
                            "osc_library": "behringer_wing",
                        }
                    ]
                }
            )
        )


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


def test_apply_osc_adapters_config_can_delete_default_osc_instance(tmp_path: Path) -> None:
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

    async def delete_default_osc() -> dict:
        return await interface.apply_osc_adapters_config(
            {
                "instances": [],
                "deleted": ["osc"],
            }
        )

    result = asyncio.run(delete_default_osc())

    assert result["instances"] == []
    assert "osc" not in interface.config.adapters
    assert "[adapters.osc]" not in config_file.read_text(encoding="utf-8")


def test_osc_adapters_config_hides_implicit_default_osc_instance() -> None:
    config = parse_config({"adapters": {}})
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    payload = interface.osc_adapters_config_payload()

    assert payload["instances"] == []


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_apply_osc_adapters_config_starts_new_enabled_instance() -> None:
    listen_port = _free_udp_port()
    runtime_adapters = []
    config = parse_config({"adapters": {}})
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        runtime_adapters=runtime_adapters,
    )

    result = asyncio.run(
        interface.apply_osc_adapters_config(
            {
                "instances": [
                    {
                        "name": "wing_foh",
                        "enabled": True,
                        "desk_mode": "wing",
                        "listen_host": "127.0.0.1",
                        "osc_port": listen_port,
                        "remote_host": "192.168.10.48",
                    }
                ]
            }
        )
    )

    wing = next(instance for instance in result["instances"] if instance["name"] == "wing_foh")

    assert wing["runtime_active"] is True
    assert interface.osc_adapters["wing_foh"].running
    assert len(runtime_adapters) == 1


def test_apply_osc_adapters_config_registers_datapoints_for_enabled_instance() -> None:
    listen_port = _free_udp_port()
    store = DataPointStore()
    runtime_adapters = []
    config = parse_config({"adapters": {}})
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        runtime_adapters=runtime_adapters,
        datapoint_store=store,
    )
    io_modules: dict[str, object] = {}
    interface.bind_osc_io_modules(io_modules)  # type: ignore[arg-type]

    asyncio.run(
        interface.apply_osc_adapters_config(
            {
                "instances": [
                    {
                        "name": "wing_foh",
                        "enabled": True,
                        "desk_mode": "wing",
                        "listen_host": "127.0.0.1",
                        "osc_port": listen_port,
                        "remote_host": "192.168.10.48",
                    }
                ]
            }
        )
    )

    specs = store.registry_snapshot()
    assert any(entry["id"].startswith("wing_foh.") for entry in specs)
    assert "wing_foh" in io_modules


def test_apply_osc_adapters_config_stops_disabled_instance() -> None:
    async def scenario() -> tuple[dict, WebInterface]:
        listen_port = _free_udp_port()
        runtime_adapters = []
        config = parse_config({"adapters": {}})
        interface = WebInterface(
            config,
            EventBus(),
            ClockBpmTracker(),
            MasterClock(config.master_clock, EventBus()),
            runtime_adapters=runtime_adapters,
        )

        await interface.apply_osc_adapters_config(
            {
                "instances": [
                    {
                        "name": "wing_foh",
                        "enabled": True,
                        "desk_mode": "wing",
                        "listen_host": "127.0.0.1",
                        "osc_port": listen_port,
                        "remote_host": "192.168.10.48",
                    }
                ]
            }
        )
        result = await interface.apply_osc_adapters_config(
            {
                "instances": [
                    {
                        "name": "wing_foh",
                        "enabled": False,
                        "desk_mode": "wing",
                        "listen_host": "127.0.0.1",
                        "osc_port": listen_port,
                        "remote_host": "192.168.10.48",
                    }
                ]
            }
        )
        return result, interface

    result, interface = asyncio.run(scenario())
    wing = next(instance for instance in result["instances"] if instance["name"] == "wing_foh")

    assert wing["runtime_active"] is False
    assert not interface.osc_adapters["wing_foh"].running


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

    async def add_and_delete_desk_b() -> None:
        await interface.apply_osc_adapters_config(
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
        await interface.apply_osc_adapters_config(
            {
                "instances": [],
                "deleted": ["desk_b"],
            }
        )

    asyncio.run(add_and_delete_desk_b())

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
