"""Tests for device configuration."""

from midijuggler.config import parse_config, save_devices
from midijuggler.device.types import DeviceConfig


def test_parse_config_requires_devices_and_rejects_mappings() -> None:
    try:
        parse_config({"mappings": [{"id": "x", "source": "a:b", "target": "c:d"}]})
    except ValueError as exc:
        assert "mappings" in str(exc)
    else:
        raise AssertionError("expected mappings rejection")

    config = parse_config(
        {
            "adapters": {"gpio": {"enabled": True, "pins": [17]}},
            "devices": [{"id": "foot_switches", "adapter": "gpio", "library_kind": "gpio"}],
            "connections": [
                {
                    "id": "switch",
                    "source": "foot_switches.pin17",
                    "target": "foot_switches.pin17",
                }
            ],
        }
    )
    assert config.devices["foot_switches"].adapter == "gpio"


def test_parse_config_rejects_unknown_connection_device() -> None:
    try:
        parse_config(
            {
                "adapters": {"gpio": {"enabled": True, "pins": [17]}},
                "devices": [{"id": "foot_switches", "adapter": "gpio"}],
                "connections": [
                    {
                        "id": "bad",
                        "source": "gpio.pin17",
                        "target": "foot_switches.pin17",
                    }
                ],
            }
        )
    except ValueError as exc:
        assert "device id" in str(exc)
    else:
        raise AssertionError("expected unknown device rejection")


def test_save_devices_round_trip(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[adapters.xtouch_mini]
type = "midi"
enabled = true
midi_library = "behringer_xtouch_mini"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    devices = {
        "xtouch": DeviceConfig(
            id="xtouch",
            adapter="xtouch_mini",
            library="behringer_xtouch_mini",
            library_kind="midi",
            label="FOH X-Touch",
        )
    }
    save_devices(path, devices)
    from midijuggler.config import load_config

    config = load_config(path)
    assert config.devices["xtouch"].library == "behringer_xtouch_mini"
