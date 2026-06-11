from midijuggler.osc.discovery import (
    _parse_ipv4_interfaces_from_ip_output,
    ipv4_interfaces,
    parse_wing_discovery_response,
    parse_x32_info_response,
    wing_broadcast_targets,
)
from midijuggler.osc.protocol import encode_message


def test_parse_wing_discovery_response() -> None:
    payload = b"WING,192.168.1.62,FOH Desk,ngc-full,SN123,4.12.0"

    desk = parse_wing_discovery_response(payload)

    assert desk is not None
    assert desk.protocol == "wing"
    assert desk.ip == "192.168.1.62"
    assert desk.name == "FOH Desk"
    assert desk.model == "ngc-full"
    assert desk.serial == "SN123"
    assert desk.firmware == "4.12.0"


def test_parse_wing_discovery_response_prefers_source_ip() -> None:
    payload = b"WING,0.0.0.0,FOH Desk,wing-compact,SN123,4.12.0"

    desk = parse_wing_discovery_response(payload, source_ip="192.168.10.48")

    assert desk is not None
    assert desk.ip == "192.168.10.48"


def test_parse_ipv4_interfaces_from_ip_output() -> None:
    interfaces = _parse_ipv4_interfaces_from_ip_output(
        "2: eth0    inet 192.168.10.23/24 brd 192.168.10.255 scope global eth0\n"
        "3: wlan0   inet 10.0.0.5/8 brd 10.255.255.255 scope global wlan0\n"
    )

    assert len(interfaces) == 2
    assert str(interfaces[0].address) == "192.168.10.23"
    assert str(interfaces[0].broadcast) == "192.168.10.255"
    assert str(interfaces[1].network) == "10.0.0.0/8"


def test_wing_broadcast_targets_use_interface_broadcast(monkeypatch) -> None:
    monkeypatch.setattr(
        "midijuggler.osc.discovery.ipv4_interfaces",
        lambda: _parse_ipv4_interfaces_from_ip_output(
            "2: eth0 inet 192.168.10.23/24 brd 192.168.10.255 scope global eth0\n"
        ),
    )

    targets = wing_broadcast_targets()

    assert ("192.168.10.255", 2222) in targets
    assert ("255.255.255.255", 2222) in targets


def test_ipv4_interfaces_falls_back_when_ip_command_missing(monkeypatch) -> None:
    def fail_run(*_args, **_kwargs):
        raise OSError("missing ip")

    monkeypatch.setattr("midijuggler.osc.discovery.subprocess.run", fail_run)
    monkeypatch.setattr(
        "midijuggler.osc.discovery._ipv4_interfaces_from_hostname",
        lambda: _parse_ipv4_interfaces_from_ip_output(
            "2: eth0 inet 192.168.1.50/24 brd 192.168.1.255 scope global eth0\n"
        ),
    )

    interfaces = ipv4_interfaces()

    assert str(interfaces[0].address) == "192.168.1.50"


def test_parse_x32_info_response() -> None:
    payload = encode_message("/info", ["V2.05", "osc-server", "X32", "4.06"])

    desk = parse_x32_info_response(payload, "192.168.1.64")

    assert desk is not None
    assert desk.protocol == "x32"
    assert desk.ip == "192.168.1.64"
    assert desk.model == "V2.05"
    assert desk.name == "X32"
