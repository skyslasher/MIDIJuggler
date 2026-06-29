from midijuggler.config import parse_config
from midijuggler.connection.bundle import (
    apply_connection_bundle_import,
    export_connection_bundle,
    preview_connection_bundle_import,
)
from midijuggler.datapoint.types import ConnectionSpec, ModifierKind
from midijuggler.learn import upsert_connection

from conftest import midi_device, osc_device


def _adapters_config() -> dict:
    return {
        "wing_native": {"enabled": True},
        "xtouch_mini": {
            "enabled": True,
            "type": "midi",
        },
    }


def _wing_xtouch_config() -> dict:
    return {
        "adapters": _adapters_config(),
        "devices": [
            osc_device("wing_foh", "behringer_wing", adapter="wing_native"),
            midi_device("xtouch", adapter="xtouch_mini", library="behringer_xtouch_mini"),
        ],
        "connections": [
            {
                "id": "wing-to-xtouch",
                "source": "wing_foh./ch/1/fdr",
                "target": "xtouch.layer_a_encoder_1_value",
                "modifier": "range_map",
                "input_min": 0.0,
                "input_max": 1.0,
                "output_min": 0.0,
                "output_max": 127.0,
            },
            {
                "id": "xtouch-to-wing",
                "source": "xtouch.layer_a_encoder_1_turn",
                "target": "wing_foh./ch/1/fdr",
                "modifier": "passthrough",
            },
            {
                "id": "other-device",
                "source": "wing_foh./ch/2/fdr",
                "target": "wing_foh./bus/1/fdr",
                "modifier": "passthrough",
            },
        ],
    }


def test_export_connection_bundle_for_device_pair() -> None:
    config = parse_config(_wing_xtouch_config())
    bundle = export_connection_bundle(
        config.connections,
        "wing_foh",
        "xtouch",
        config.devices,
        config.adapters,
    )

    assert bundle["format"] == "midijuggler_connection_bundle"
    assert bundle["devices"]["device_a"]["library"] == "behringer_wing"
    assert bundle["devices"]["device_b"]["library"] == "behringer_xtouch_mini"
    assert len(bundle["connections"]) == 2
    assert bundle["connections"][0]["source_point"].startswith("/ch/")
    assert bundle["connections"][0]["target_point"] == "layer_a_encoder_1_value"


def test_import_connection_bundle_remaps_to_selected_devices() -> None:
    source_config = parse_config(_wing_xtouch_config())
    bundle = export_connection_bundle(
        source_config.connections,
        "wing_foh",
        "xtouch",
        source_config.devices,
        source_config.adapters,
    )

    target_config = parse_config(
        {
            "adapters": _adapters_config(),
            "devices": [
                osc_device("wing_remote", "behringer_wing", adapter="wing_native"),
                midi_device(
                    "xtouch_remote",
                    adapter="xtouch_mini",
                    library="behringer_xtouch_mini",
                ),
            ],
            "connections": [],
        }
    )

    preview = preview_connection_bundle_import(bundle, target_config)
    assert preview["connection_count"] == 2
    assert len(preview["devices"]["device_a"]["candidates"]) == 1
    assert len(preview["devices"]["device_b"]["candidates"]) == 1

    imported, updated_devices, merged = apply_connection_bundle_import(
        bundle,
        {
            "device_a": "wing_remote",
            "device_b": "xtouch_remote",
        },
        target_config,
        [],
    )
    assert len(imported) == 2
    assert imported[0].source.startswith("wing_remote.")
    assert imported[0].target.startswith("xtouch_remote.")
    assert updated_devices == {}

    stored = upsert_connection([], imported[0])
    stored = upsert_connection(stored, imported[1])
    assert any(connection.source.startswith("xtouch_remote.") for connection in stored)


def test_import_connection_bundle_rejects_incompatible_device_mapping() -> None:
    config = parse_config(_wing_xtouch_config())
    bundle = export_connection_bundle(
        config.connections,
        "wing_foh",
        "xtouch",
        config.devices,
        config.adapters,
    )

    try:
        apply_connection_bundle_import(
            bundle,
            {
                "device_a": "wing_foh",
                "device_b": "wing_foh",
            },
            config,
            [],
        )
    except ValueError as exc:
        assert "not compatible" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_import_connection_bundle_rejects_missing_mapping() -> None:
    config = parse_config(_wing_xtouch_config())
    bundle = export_connection_bundle(
        config.connections,
        "wing_foh",
        "xtouch",
        config.devices,
        config.adapters,
    )

    try:
        apply_connection_bundle_import(bundle, {"device_a": "wing_foh"}, config, [])
    except ValueError as exc:
        assert "device mapping for device_b is required" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_export_includes_custom_points_not_in_library() -> None:
    config = parse_config(
        {
            "adapters": _adapters_config(),
            "devices": [
                {
                    **osc_device("wing_foh", "behringer_wing", adapter="wing_native"),
                    "custom_points": [
                        {
                            "id": "custom_target",
                            "direction": "target",
                            "label": "Custom target",
                        }
                    ],
                },
                midi_device("xtouch", adapter="xtouch_mini", library="behringer_xtouch_mini"),
            ],
            "connections": [
                {
                    "id": "to-custom",
                    "source": "xtouch.layer_a_fader",
                    "target": "wing_foh.custom_target",
                    "modifier": "passthrough",
                }
            ],
        }
    )
    bundle = export_connection_bundle(
        config.connections,
        "wing_foh",
        "xtouch",
        config.devices,
        config.adapters,
    )
    assert bundle["custom_points"]["device_a"] == [
        {
            "id": "custom_target",
            "value_type": "float",
            "direction": "target",
            "label": "Custom target",
        }
    ]


def test_import_merges_exported_custom_points() -> None:
    source_config = parse_config(
        {
            "adapters": _adapters_config(),
            "devices": [
                {
                    **osc_device("wing_foh", "behringer_wing", adapter="wing_native"),
                    "custom_points": [
                        {
                            "id": "custom_target",
                            "direction": "target",
                            "label": "Custom target",
                        }
                    ],
                },
                midi_device("xtouch", adapter="xtouch_mini", library="behringer_xtouch_mini"),
            ],
            "connections": [
                {
                    "id": "to-custom",
                    "source": "xtouch.layer_a_fader",
                    "target": "wing_foh.custom_target",
                    "modifier": "factor",
                    "factor": 1.5,
                }
            ],
        }
    )
    bundle = export_connection_bundle(
        source_config.connections,
        "wing_foh",
        "xtouch",
        source_config.devices,
        source_config.adapters,
    )
    target_config = parse_config(
        {
            "adapters": _adapters_config(),
            "devices": [
                osc_device("wing_remote", "behringer_wing", adapter="wing_native"),
                midi_device(
                    "xtouch_remote",
                    adapter="xtouch_mini",
                    library="behringer_xtouch_mini",
                ),
            ],
            "connections": [],
        }
    )
    _, updated_devices, _ = apply_connection_bundle_import(
        bundle,
        {"device_a": "wing_remote", "device_b": "xtouch_remote"},
        target_config,
        [],
    )
    assert "wing_remote" in updated_devices
    assert updated_devices["wing_remote"].custom_points[0].id == "custom_target"
