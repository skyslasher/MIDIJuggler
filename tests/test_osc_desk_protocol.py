import pytest

from midijuggler.osc.desk_protocol import (
    apply_desk_options,
    desk_mode_for_library,
    desk_protocol_for_library,
    desk_subscribe_address,
    osc_library_for_desk_mode,
    sync_query_addresses,
)
from midijuggler.osc.protocol import decode_messages, encode_message


def test_apply_desk_options_couples_ports_for_x32() -> None:
    options = apply_desk_options(
        {
            "osc_library": "behringer_x32",
            "listen_host": "0.0.0.0",
            "listen_port": 9100,
            "remote_host": "192.168.1.32",
            "remote_port": 10023,
        }
    )

    assert options["desk_mode"] == "x32"
    assert options["listen_port"] == 10023
    assert options["remote_port"] == 10023
    assert options["osc_port"] == 10023


def test_apply_desk_options_rejects_proxy_for_x32() -> None:
    with pytest.raises(ValueError, match="behringer_wing"):
        apply_desk_options(
            {
                "osc_library": "behringer_x32",
                "desk_proxy_mode": True,
            }
        )


def test_apply_desk_options_allows_wing_proxy_mode() -> None:
    options = apply_desk_options(
        {
            "osc_library": "behringer_wing",
            "desk_proxy_mode": True,
            "remote_host": "192.168.1.48",
        }
    )

    assert options["desk_proxy_mode"] is True
    assert options["desk_mode"] == "wing"
    assert options["remote_port"] == 2223


def test_sync_query_addresses_returns_unique_library_addresses() -> None:
    addresses = sync_query_addresses("behringer_x32")

    assert "/ch/01/mix/fader" in addresses
    assert len(addresses) == len(set(addresses))


def test_osc_library_for_desk_mode_maps_protocol_ids() -> None:
    assert osc_library_for_desk_mode("x32") == "behringer_x32"
    assert osc_library_for_desk_mode("wing") == "behringer_wing"
    assert osc_library_for_desk_mode("") == ""
    assert desk_mode_for_library("behringer_wing") == "wing"


def test_osc_library_for_desk_mode_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="desk_mode must be"):
        osc_library_for_desk_mode("dm3")


def test_desk_subscribe_address_for_wing_uses_event_subscription() -> None:
    wing = desk_protocol_for_library("behringer_wing")

    assert wing is not None
    assert wing.keepalive_address == "/*s~"
    assert desk_subscribe_address(wing, 2223) == "/%2223/*s~"
    assert desk_subscribe_address(wing, 0) == "/*s~"


def test_decode_wing_fader_feedback_message() -> None:
    payload = encode_message("/ch/1/fdr~~~", ["-oo", 0.0, -144.0])
    address, arguments = decode_messages(payload)[0]

    assert address == "/ch/1/fdr~~~"
    assert arguments[0] == "-oo"
    assert arguments[1] == pytest.approx(0.0)
    assert arguments[2] == pytest.approx(-144.0)


def test_desk_protocol_for_library_returns_keepalive_command() -> None:
    wing = desk_protocol_for_library("behringer_wing")

    assert wing is not None
    assert wing.keepalive_address == "/*s~"
    assert wing.default_port == 2223
