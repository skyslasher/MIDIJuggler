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
                        "source": "desk.pin17",
                        "target": "foot_switches.pin17",
                    }
                ],
            }
        )
    except ValueError as exc:
        assert "device id" in str(exc)
        assert "foot_switches" in str(exc)
    else:
        raise AssertionError("expected unknown device rejection")


def test_parse_config_normalizes_adapter_prefixed_connections() -> None:
    config = parse_config(
        {
            "adapters": {
                "x32_foh": {"type": "osc", "enabled": True, "osc_library": "behringer_x32"},
            },
            "devices": [
                {
                    "id": "x32_foh",
                    "adapter": "x32_foh",
                    "library": "behringer_x32",
                    "library_kind": "osc",
                }
            ],
            "connections": [
                {
                    "id": "legacy-prefix",
                    "source": "x32./ch/01/mix/fader",
                    "target": "x32_foh./ch/01/mix/fader",
                }
            ],
        }
    )

    assert config.connections[0].source == "x32_foh./ch/01/mix/fader"


def test_parse_config_infers_devices_when_devices_section_missing() -> None:
    config = parse_config(
        {
            "adapters": {
                "x32_foh": {
                    "type": "osc",
                    "enabled": True,
                    "osc_library": "behringer_x32",
                },
                "xtouch_mini": {
                    "type": "midi",
                    "enabled": True,
                    "midi_library": "behringer_xtouch_mini",
                },
            },
            "connections": [
                {
                    "id": "learn-x32-ch-01-mix-fader-to-xtouch-mini-layer-a-encoder-1-led-ring",
                    "source": "x32./ch/01/mix/fader",
                    "target": "xtouch_mini.layer_a_encoder_1_led_ring",
                }
            ],
        }
    )

    assert config.devices["x32_foh"].adapter == "x32_foh"
    assert config.devices["x32_foh"].library == "behringer_x32"
    assert config.devices["xtouch_mini"].library == "behringer_xtouch_mini"
    assert config.connections[0].source == "x32_foh./ch/01/mix/fader"
    assert config.connections[0].target == "xtouch_mini.layer_a_encoder_1_led_ring"


def test_parse_config_normalizes_x32_shorthand_without_devices_section() -> None:
    config = parse_config(
        {
            "adapters": {
                "x32_foh": {
                    "type": "osc",
                    "enabled": True,
                    "osc_library": "behringer_x32",
                },
            },
            "connections": [
                {
                    "id": "legacy-prefix",
                    "source": "x32./ch/01/mix/fader",
                    "target": "x32_foh./ch/01/mix/fader",
                }
            ],
        }
    )

    assert config.connections[0].source == "x32_foh./ch/01/mix/fader"


def test_parse_config_supplements_missing_adapter_devices() -> None:
    config = parse_config(
        {
            "adapters": {
                "x32_foh": {
                    "type": "osc",
                    "enabled": True,
                    "osc_library": "behringer_x32",
                },
                "xtouch_mini": {
                    "type": "midi",
                    "enabled": True,
                    "midi_library": "behringer_xtouch_mini",
                },
            },
            "devices": [
                {
                    "id": "x32_foh",
                    "adapter": "x32_foh",
                    "library": "behringer_x32",
                    "library_kind": "osc",
                }
            ],
            "connections": [
                {
                    "id": "midi-to-x32",
                    "source": "xtouch_mini.layer_a_fader",
                    "target": "x32./ch/01/mix/fader",
                }
            ],
        }
    )

    assert "xtouch_mini" in config.devices
    assert config.devices["xtouch_mini"].library == "behringer_xtouch_mini"
    assert config.connections[0].target == "x32_foh./ch/01/mix/fader"


def test_adapter_device_options_lists_configured_adapters() -> None:
    from midijuggler.config import adapter_device_options

    config = parse_config(
        {
            "adapters": {
                "gpio": {"enabled": True, "pins": [17]},
                "x32_foh": {"type": "osc", "enabled": True, "osc_library": "behringer_x32"},
            },
            "devices": [{"id": "gpio", "adapter": "gpio", "library_kind": "gpio"}],
        }
    )
    options = adapter_device_options(config.adapters, config.devices)
    by_name = {entry["name"]: entry for entry in options}
    assert by_name["gpio"]["bound_device_id"] == "gpio"
    assert by_name["x32_foh"]["library"] == "behringer_x32"
    assert by_name["x32_foh"]["bound_device_id"] == "x32_foh"


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


def test_save_devices_removes_custom_points_without_leaving_orphans(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[adapters.xtouch_mini]
type = "midi"
enabled = true
midi_library = "behringer_xtouch_mini"

[[devices]]
id = "xtouch"
adapter = "xtouch_mini"
library = "behringer_xtouch_mini"
library_kind = "midi"

[[devices.custom_points]]
id = "custom_fader"
direction = "source"
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
        )
    }

    save_devices(path, devices)

    saved_text = path.read_text(encoding="utf-8")
    assert saved_text.count("[[devices]]") == 1
    assert "[[devices.custom_points]]" not in saved_text
    import tomllib

    with path.open("rb") as handle:
        tomllib.load(handle)
