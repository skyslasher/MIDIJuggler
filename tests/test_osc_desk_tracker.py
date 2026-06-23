import asyncio
from pathlib import Path

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import load_config, parse_config
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.osc.discovery import DiscoveredDesk, desk_identity
from midijuggler.web.server import WebInterface


def test_desk_identity_uses_wing_serial() -> None:
    desk = DiscoveredDesk(
        protocol="wing",
        ip="192.168.10.48",
        name="FOH Desk",
        model="ngc-full",
        serial="SN123",
        firmware="4.12.0",
    )

    assert desk_identity(desk) == "wing:SN123"
    assert desk.as_dict()["identity"] == "wing:SN123"


def test_desk_identity_uses_x32_network_name() -> None:
    desk = DiscoveredDesk(
        protocol="x32",
        ip="192.168.10.32",
        name="X32-02-4A-53",
        model="X32",
        firmware="4.06",
    )

    assert desk_identity(desk) == "x32:X32-02-4A-53"


def test_status_payload_includes_discovered_desks() -> None:
    from midijuggler.osc.desk_tracker import OscDeskDiscoveryManager

    config = parse_config({"adapters": {}})
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )
    tracker = OscDeskDiscoveryManager(interface)
    tracker.remember_desks(
        [
            DiscoveredDesk(
                protocol="wing",
                ip="192.168.10.48",
                name="FOH Desk",
                model="ngc-full",
                serial="SN123",
                firmware="4.12.0",
            )
        ]
    )
    interface.osc_desk_tracker = tracker

    payload = interface._status_payload()

    assert len(payload["osc_discovered_desks"]) == 1
    assert payload["osc_discovered_desks"][0]["identity"] == "wing:SN123"


def test_sync_osc_desk_addresses_relocates_bound_instance(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[web]
host = "127.0.0.1"
port = 8080

[adapters.wing_foh]
type = "osc"
enabled = false
osc_library = "behringer_wing"
remote_host = "192.168.10.48"
desk_identity = "wing:SN123"
listen_host = "0.0.0.0"
listen_port = 2223
remote_port = 2223
osc_port = 2223
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = load_config(config_path)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        config_path=config_path,
    )

    result = asyncio.run(
        interface.sync_osc_desk_addresses(
            [
                DiscoveredDesk(
                    protocol="wing",
                    ip="192.168.10.60",
                    name="FOH Desk",
                    model="ngc-full",
                    serial="SN123",
                    firmware="4.12.0",
                )
            ]
        )
    )

    assert result["updates"] == [
        {"instance": "wing_foh", "identity": "wing:SN123", "ip": "192.168.10.60"}
    ]
    assert config.adapters["wing_foh"].options["remote_host"] == "192.168.10.60"


def test_sync_osc_desk_addresses_auto_binds_matching_ip(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[web]
host = "127.0.0.1"
port = 8080

[adapters.wing_foh]
type = "osc"
enabled = false
osc_library = "behringer_wing"
remote_host = "192.168.10.48"
listen_host = "0.0.0.0"
listen_port = 2223
remote_port = 2223
osc_port = 2223
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = load_config(config_path)
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
        config_path=config_path,
    )

    result = asyncio.run(
        interface.sync_osc_desk_addresses(
            [
                DiscoveredDesk(
                    protocol="wing",
                    ip="192.168.10.48",
                    name="FOH Desk",
                    model="ngc-full",
                    serial="SN123",
                    firmware="4.12.0",
                )
            ]
        )
    )

    assert result["bindings"] == [
        {"instance": "wing_foh", "identity": "wing:SN123", "ip": "192.168.10.48"}
    ]
    assert config.adapters["wing_foh"].options["desk_identity"] == "wing:SN123"
