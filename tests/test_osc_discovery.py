from midijuggler.osc.discovery import (
    parse_wing_discovery_response,
    parse_x32_info_response,
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


def test_parse_x32_info_response() -> None:
    payload = encode_message("/info", ["V2.05", "osc-server", "X32", "4.06"])

    desk = parse_x32_info_response(payload, "192.168.1.64")

    assert desk is not None
    assert desk.protocol == "x32"
    assert desk.ip == "192.168.1.64"
    assert desk.model == "V2.05"
    assert desk.name == "X32"
