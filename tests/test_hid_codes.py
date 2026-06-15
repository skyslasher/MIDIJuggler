import pytest

from midijuggler.hid import codes


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
