import pytest

from midijuggler.config import RotaryDisplayDeviceConfig, parse_config
from midijuggler.modules.interface.rotary_display.device_config import (
    build_device_config_commands,
)
from midijuggler.modules.interface.rotary_display.protocol import parse_hello_osc
from midijuggler.rotary_mdns import (
    browse_rotary_feedback_targets,
    format_mdns_hostname,
    normalize_mdns_hostname,
    parse_avahi_rotary_browse_line,
)


def test_normalize_mdns_hostname_strips_local_suffix() -> None:
    assert normalize_mdns_hostname("Rotary-Stage.local") == "rotary-stage"


def test_normalize_mdns_hostname_rejects_invalid_names() -> None:
    with pytest.raises(ValueError):
        normalize_mdns_hostname("-bad")
    with pytest.raises(ValueError):
        normalize_mdns_hostname("bad name")


def test_format_mdns_hostname() -> None:
    assert format_mdns_hostname("rotary-stage") == "rotary-stage.local"


def test_parse_hello_osc_accepts_mdns_name() -> None:
    assert parse_hello_osc(("rotary-stage-left.local", 9001)) == (
        "rotary-stage-left.local",
        9001,
    )


def test_parse_rotary_display_device_mdns_hostname() -> None:
    config = parse_config(
        {
            "rotary_display": {
                "device": {"mdns_hostname": "Rotary-FOH.local"},
            }
        }
    )
    assert config.rotary_display.device.mdns_hostname == "rotary-foh"


def test_build_device_config_commands_include_mdns_hostname() -> None:
    device = RotaryDisplayDeviceConfig(mdns_hostname="rotary-foh")
    commands = build_device_config_commands(device)
    assert "mdns_hostname rotary-foh" in commands


def test_build_device_config_commands_clear_auto_mdns_hostname() -> None:
    device = RotaryDisplayDeviceConfig()
    commands = build_device_config_commands(device)
    assert "mdns_hostname clear" in commands


def test_parse_avahi_rotary_browse_line() -> None:
    line = (
        "=;eth0;IPv4;rotary-stage;"
        "_midijuggler-rotary._udp;local;rotary-stage.local;192.168.1.42;9001;"
        '""'
    )
    service = parse_avahi_rotary_browse_line(line)
    assert service is not None
    assert service.hostname == "rotary-stage.local"
    assert service.port == 9001


def test_browse_rotary_feedback_targets_uses_avahi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "midijuggler.rotary_mdns.zeroconf_available",
        lambda: False,
    )
    monkeypatch.setattr(
        "midijuggler.rotary_mdns._browse_rotary_via_avahi",
        lambda timeout_s=4.0: [
            __import__(
                "midijuggler.rotary_mdns",
                fromlist=["RotaryMdnsService"],
            ).RotaryMdnsService("rotary-stage.local", 9001)
        ],
    )

    services = browse_rotary_feedback_targets(timeout_s=1.0)
    assert len(services) == 1
    assert services[0].hostname == "rotary-stage.local"
    assert services[0].port == 9001
