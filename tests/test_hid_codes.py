import pytest

from midijuggler.hid import codes

SAMPLE_DEVICES = [
    {
        "path": "/dev/input/event0",
        "name": "Test Gamepad",
        "vendor_id": "0x046d",
        "product_id": "0xc21f",
    },
    {
        "path": "/dev/input/event2",
        "name": "USB Encoder",
        "vendor_id": "0x1234",
        "product_id": "0xabcd",
    },
]


def test_keyboard_code_name_prefers_key_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeEcodes:
        EV_KEY = 1

        def bytype_get(self, event_type, code):
            mapping = {
                (1, 30): "KEY_A",
                (1, 304): "BTN_A",
            }
            return mapping.get((event_type, code))

    fake_ecodes = FakeEcodes()
    fake_ecodes.bytype = {1: {30: "KEY_A", 304: "BTN_A"}}

    monkeypatch.setattr(codes, "_require_evdev", lambda: (None, fake_ecodes))

    assert codes.keyboard_code_name(1, 30) == "KEY_A"
    assert codes.keyboard_code_name(1, 304) is None
    assert codes.is_keyboard_key(1, 30) is True
    assert codes.is_keyboard_key(1, 304) is False


def test_lookup_input_device_matches_vendor_product() -> None:
    matched = codes.lookup_input_device(
        vendor_id="0x046d",
        product_id="0xc21f",
        devices=SAMPLE_DEVICES,
    )

    assert matched is not None
    assert matched["name"] == "Test Gamepad"
    assert matched["path"] == "/dev/input/event0"


def test_lookup_input_device_matches_device_path() -> None:
    matched = codes.lookup_input_device(
        device_path="/dev/input/event2",
        devices=SAMPLE_DEVICES,
    )

    assert matched is not None
    assert matched["vendor_id"] == "0x1234"
    assert matched["product_id"] == "0xabcd"


def test_normalize_hid_device_options_migrates_legacy_device_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codes, "list_input_devices", lambda: SAMPLE_DEVICES)

    normalized = codes.normalize_hid_device_options(
        {"device": "/dev/input/event2", "inputs": []},
    )

    assert normalized["vendor_id"] == "0x1234"
    assert normalized["product_id"] == "0xabcd"
    assert "device" not in normalized


def test_resolve_device_path_prefers_vendor_product_over_stale_device_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codes, "list_input_devices", lambda: SAMPLE_DEVICES)

    resolved = codes.resolve_device_path(
        {
            "device": "/dev/input/event99",
            "vendor_id": "0x046d",
            "product_id": "0xc21f",
        }
    )

    assert resolved == "/dev/input/event0"


def test_hid_device_key_normalizes_hex_values() -> None:
    assert codes.hid_device_key("0x046d", "0xc21f") == "0x046d:0xc21f"
    assert codes.parse_hid_device_key("046d:c21f") == ("0x046d", "0xc21f")


def test_unregister_module_except_removes_stale_hid_points() -> None:
    from midijuggler.datapoint.store import DataPointStore
    from midijuggler.datapoint.types import (
        DataPointDirection,
        DataPointId,
        DataPointSpec,
        ValueType,
    )

    store = DataPointStore()
    store.register(
        DataPointSpec(
            id=DataPointId("encoder", "abs_x"),
            value_type=ValueType.FLOAT,
            direction=DataPointDirection.INPUT,
            protocol="hid",
        )
    )
    store.register(
        DataPointSpec(
            id=DataPointId("encoder", "key_a"),
            value_type=ValueType.FLOAT,
            direction=DataPointDirection.INPUT,
            protocol="hid",
        )
    )

    store.unregister_module_except("encoder", {"encoder.key_a"})

    assert store.spec("encoder.abs_x") is None
    assert store.spec("encoder.key_a") is not None
