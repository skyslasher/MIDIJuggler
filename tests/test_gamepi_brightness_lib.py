from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import mock

import pytest


def _load_brightness_lib():
    script = Path(__file__).resolve().parents[1] / "scripts" / "gamepi_brightness_lib.py"
    spec = importlib.util.spec_from_file_location("gamepi_brightness_lib", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_brightness_status_uses_software_when_no_sysfs(tmp_path, monkeypatch) -> None:
    lib = _load_brightness_lib()
    monkeypatch.setattr(lib, "find_backlight", lambda: None)
    monkeypatch.setattr(lib, "STATE_PATH", tmp_path / "brightness")
    monkeypatch.setenv("GAMEPI_SOFTWARE_BRIGHTNESS", "1")

    payload = lib.brightness_status()

    assert payload == {"available": True, "mode": "software", "level": 255, "max": 255}


def test_adjust_brightness_software_updates_state(tmp_path, monkeypatch) -> None:
    lib = _load_brightness_lib()
    monkeypatch.setattr(lib, "find_backlight", lambda: None)
    monkeypatch.setattr(lib, "STATE_PATH", tmp_path / "brightness")
    monkeypatch.setenv("GAMEPI_SOFTWARE_BRIGHTNESS", "1")
    monkeypatch.setattr(lib, "_run_gamma", lambda gamma: True)

    payload = lib.adjust_brightness(-10)

    assert payload["ok"] is True
    assert payload["mode"] == "software"
    assert payload["level"] == 245
    assert (tmp_path / "brightness").read_text(encoding="utf-8").strip() == "245"


def test_adjust_brightness_reports_unavailable_when_disabled(monkeypatch) -> None:
    lib = _load_brightness_lib()
    monkeypatch.setattr(lib, "find_backlight", lambda: None)
    monkeypatch.setenv("GAMEPI_SOFTWARE_BRIGHTNESS", "0")

    payload = lib.adjust_brightness(10)

    assert payload == {"ok": False, "available": False, "mode": "none"}


def test_level_to_gamma_maps_full_range() -> None:
    lib = _load_brightness_lib()

    assert lib.level_to_gamma(0) == pytest.approx(lib.GAMMA_MIN)
    assert lib.level_to_gamma(255) == pytest.approx(lib.GAMMA_MAX)
