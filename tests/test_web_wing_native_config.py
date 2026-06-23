import asyncio
from pathlib import Path

import pytest

from midijuggler.adapters.wing_native import WingNativeAdapter
from midijuggler.clock import ClockBpmTracker
from midijuggler.config import load_config, parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface

from conftest import wing_device


def test_wing_native_adapters_config_payload_lists_instances() -> None:
    config = parse_config(
        {
            "adapters": {
                "wing_native_foh": {
                    "type": "wing_native",
                    "enabled": True,
                    "remote_host": "192.168.10.48",
                    "native_port": 2222,
                    "wing_library": "behringer_wing",
                },
                "osc": {"enabled": False},
            }
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    payload = interface.wing_native_adapters_config_payload()

    assert [instance["name"] for instance in payload["instances"]] == ["wing_native_foh"]
    wing = payload["instances"][0]
    assert wing["remote_host"] == "192.168.10.48"
    assert wing["native_port"] == 2222
    assert wing["device_library"] == "behringer_wing"
    assert wing["device_id"] == "wing_native_foh"
    assert "wing_library" not in wing
    assert payload["available_wing_libraries"]


def test_wing_native_instance_payload_includes_bound_device_library() -> None:
    config = parse_config(
        {
            "adapters": {
                "wing_native_foh": {
                    "type": "wing_native",
                    "enabled": True,
                    "remote_host": "192.168.10.48",
                },
            },
            "devices": [wing_device("wing_native_foh")],
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    wing = interface.wing_native_adapters_config_payload()["instances"][0]

    assert wing["device_id"] == "wing_native_foh"
    assert wing["device_library"] == "behringer_wing"


def test_wing_native_adapters_config_hides_implicit_default_instance() -> None:
    config = parse_config({"adapters": {}})
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    payload = interface.wing_native_adapters_config_payload()

    assert payload["instances"] == []


def test_apply_wing_native_adapters_config_persists_sections(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.wing_native_foh]
        type = "wing_native"
        enabled = false
        remote_host = "192.168.10.48"
        native_port = 2222
        wing_library = "behringer_wing"
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
        interface.apply_wing_native_adapters_config(
            {
                "instances": [
                    {
                        "name": "wing_native_foh",
                        "enabled": False,
                        "remote_host": "10.0.0.48",
                        "native_port": 2222,
                        "echo_guard_ms": 50,
                    }
                ]
            }
        )
    )

    saved = load_config(config_file)

    assert result["persisted"] is True
    assert saved.adapters["wing_native_foh"].options["remote_host"] == "10.0.0.48"
    assert saved.adapters["wing_native_foh"].options["echo_guard_ms"] == 50


def test_apply_wing_native_adapters_config_registers_datapoints_for_enabled_instance() -> None:
    store = DataPointStore()
    runtime_adapters = []
    adapter = WingNativeAdapter(
        name="wing_native_foh",
        config=parse_config(
            {
                "adapters": {
                    "wing_native_foh": {
                        "type": "wing_native",
                        "enabled": True,
                        "remote_host": "192.168.10.48",
                    }
                },
                "devices": [wing_device("wing_native_foh")],
            }
        ).adapters["wing_native_foh"],
        bus=EventBus(),
    )
    adapter.running = True

    config = parse_config(
        {
            "adapters": {
                "wing_native_foh": {
                    "type": "wing_native",
                    "enabled": False,
                    "remote_host": "192.168.10.48",
                }
            },
            "devices": [wing_device("wing_native_foh")],
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        runtime_adapters=runtime_adapters,
        datapoint_store=store,
        wing_native_adapters={"wing_native_foh": adapter},
    )
    io_modules: dict[str, object] = {}
    interface.bind_osc_io_modules(io_modules)  # type: ignore[arg-type]

    asyncio.run(
        interface.apply_wing_native_adapters_config(
            {
                "instances": [
                    {
                        "name": "wing_native_foh",
                        "enabled": True,
                        "remote_host": "192.168.10.48",
                        "native_port": 2222,
                    }
                ]
            }
        )
    )

    specs = store.registry_snapshot()
    assert any(entry["id"].startswith("wing_native_foh.") for entry in specs)
    assert "wing_native_foh" in io_modules


def test_apply_wing_native_adapters_config_ignores_payload_wing_library() -> None:
    config = parse_config({"adapters": {}})
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    result = asyncio.run(
        interface.apply_wing_native_adapters_config(
            {
                "instances": [
                    {
                        "name": "wing_native_foh",
                        "enabled": False,
                        "remote_host": "192.168.10.48",
                        "wing_library": "behringer_x32",
                    }
                ]
            }
        )
    )

    saved = interface.config.adapters["wing_native_foh"].options
    assert saved["wing_library"] == "behringer_wing"
    assert result["instances"][0]["device_library"] == ""


def test_apply_wing_native_adapters_config_can_delete_instance(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [adapters.wing_native_foh]
        type = "wing_native"
        enabled = false
        remote_host = "192.168.10.48"
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
        interface.apply_wing_native_adapters_config(
            {
                "instances": [],
                "deleted": ["wing_native_foh"],
            }
        )
    )

    assert result["instances"] == []
    assert "wing_native_foh" not in interface.config.adapters
    assert "[adapters.wing_native_foh]" not in config_file.read_text(encoding="utf-8")
