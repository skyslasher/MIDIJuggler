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
        assert "configured device" in str(exc)
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


def test_parse_config_enriches_device_library_from_adapter() -> None:
    config = parse_config(
        {
            "adapters": {
                "xtouch_mini": {
                    "type": "midi",
                    "enabled": True,
                    "midi_library": "behringer_xtouch_mini",
                },
            },
            "devices": [
                {
                    "id": "device_220b4dff",
                    "name": "X-Touch Mini",
                    "adapter": "xtouch_mini",
                }
            ],
        }
    )

    device = config.devices["device_220b4dff"]
    assert device.library == "behringer_xtouch_mini"
    assert device.library_kind == "midi"


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


def test_supplement_devices_uses_adapter_display_name() -> None:
    from midijuggler.config import AdapterConfig, supplement_devices

    devices = supplement_devices(
        {},
        {
            "device_f7a5b4b0": AdapterConfig(
                enabled=True,
                options={"midi_library": "behringer_xtouch_mini"},
                kind="midi",
                name="X-Touch Mini",
            )
        },
    )

    device = devices["device_f7a5b4b0"]
    assert device.uid == "device_f7a5b4b0"
    assert device.name == "X-Touch Mini"
    assert device.adapter == "device_f7a5b4b0"


def test_enrich_device_from_adapter_syncs_legacy_auto_name() -> None:
    from midijuggler.config import AdapterConfig, enrich_device_from_adapter

    device = DeviceConfig(
        uid="device_f7a5b4b0",
        name="device_f7a5b4b0",
        adapter="device_f7a5b4b0",
        library="behringer_xtouch_mini",
        library_kind="midi",
    )
    adapter = AdapterConfig(
        enabled=True,
        options={"midi_library": "behringer_xtouch_mini"},
        kind="midi",
        name="X-Touch Mini",
    )

    enriched = enrich_device_from_adapter(device, adapter)
    assert enriched.name == "X-Touch Mini"


def test_supplement_devices_respects_suppressed_adapters() -> None:
    from midijuggler.config import AdapterConfig, supplement_devices

    adapters = {
        "device_f7a5b4b0": AdapterConfig(
            enabled=True,
            options={"midi_library": "behringer_xtouch_mini"},
            kind="midi",
            name="X-Touch Mini",
        )
    }
    devices = supplement_devices(
        {},
        adapters,
        suppressed_adapters=("device_f7a5b4b0",),
    )
    assert devices == {}


def test_update_suppressed_inferred_device_adapters_tracks_deletions() -> None:
    from midijuggler.config import (
        AdapterConfig,
        update_suppressed_inferred_device_adapters,
    )

    adapters = {
        "device_f7a5b4b0": AdapterConfig(enabled=True, kind="midi"),
    }
    previous = {
        "device_f7a5b4b0": DeviceConfig(
            uid="device_f7a5b4b0",
            name="X-Touch Mini",
            adapter="device_f7a5b4b0",
            library_kind="midi",
        )
    }

    suppressed = update_suppressed_inferred_device_adapters(previous, {}, adapters, ())
    assert suppressed == ("device_f7a5b4b0",)

    restored = update_suppressed_inferred_device_adapters(
        {},
        previous,
        adapters,
        suppressed,
    )
    assert restored == ()


def test_parse_config_respects_suppressed_inferred_devices() -> None:
    config = parse_config(
        {
            "runtime": {
                "suppressed_inferred_device_adapters": ["xtouch_mini"],
            },
            "adapters": {
                "xtouch_mini": {
                    "type": "midi",
                    "enabled": True,
                    "midi_library": "behringer_xtouch_mini",
                },
            },
            "devices": [],
        }
    )

    assert "xtouch_mini" not in config.devices


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
            uid="xtouch",
            name="FOH X-Touch",
            adapter="xtouch_mini",
            library="behringer_xtouch_mini",
            library_kind="midi",
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
            uid="xtouch",
            name="xtouch",
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


def test_resolve_adapter_uid_matches_slugged_legacy_refs() -> None:
    from midijuggler.config import AdapterConfig
    from midijuggler.device.identity import resolve_adapter_uid

    adapters = {
        "wing_midi_1": AdapterConfig(
            enabled=True,
            kind="midi",
            options={},
            name="Wing_MIDI_1",
        )
    }

    assert resolve_adapter_uid("wing__midi_1", adapters) == "wing_midi_1"
    assert resolve_adapter_uid("Wing MIDI 1", adapters) == "wing_midi_1"


def test_parse_config_skips_devices_with_unknown_adapter() -> None:
    config = parse_config(
        {
            "adapters": {
                "gpio": {"enabled": True, "pins": [17]},
            },
            "devices": [
                {"uid": "foot_switches", "adapter": "gpio", "library_kind": "gpio"},
                {"uid": "orphan", "adapter": "missing_adapter", "library_kind": "midi"},
            ],
        },
        strict=False,
    )

    assert set(config.devices) == {"foot_switches"}
    assert any("missing_adapter" in issue for issue in config.load_issues)


def test_parse_config_lenient_skips_duplicate_device_uid() -> None:
    config = parse_config(
        {
            "adapters": {
                "wing_midi_1": {"type": "midi", "enabled": True},
            },
            "devices": [
                {
                    "uid": "wing_midi_1",
                    "adapter": "wing_midi_1",
                    "library": "behringer_wing",
                    "library_kind": "midi",
                },
                {
                    "uid": "wing_midi_1",
                    "adapter": "wing_midi_1",
                    "library": "behringer_wing",
                    "library_kind": "midi",
                },
            ],
        },
        strict=False,
    )

    assert set(config.devices) == {"wing_midi_1"}
    assert any("duplicates device uid 'wing_midi_1'" in issue for issue in config.load_issues)


def test_parse_config_strict_rejects_duplicate_device_uid() -> None:
    import pytest

    with pytest.raises(ValueError, match="duplicates device uid 'wing_midi_1'"):
        parse_config(
            {
                "adapters": {
                    "wing_midi_1": {"type": "midi", "enabled": True},
                },
                "devices": [
                    {
                        "uid": "wing_midi_1",
                        "adapter": "wing_midi_1",
                        "library": "behringer_wing",
                        "library_kind": "midi",
                    },
                    {
                        "uid": "wing_midi_1",
                        "adapter": "wing_midi_1",
                        "library": "behringer_wing",
                        "library_kind": "midi",
                    },
                ],
            },
            strict=True,
        )

