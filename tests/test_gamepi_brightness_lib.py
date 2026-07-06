from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest


def _load_module(name: str, filename: str):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    script = scripts / filename
    import sys

    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location(name, script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_brightness_status_uses_software_when_no_sysfs(monkeypatch) -> None:
    lib = _load_module("gamepi_brightness_lib", "gamepi_brightness_lib.py")
    monkeypatch.setattr(lib, "find_backlight", lambda: None)
    monkeypatch.setattr(lib, "STATE_PATH", Path("/tmp/unused-brightness-test"))
    monkeypatch.setenv("GAMEPI_SOFTWARE_BRIGHTNESS", "1")
    monkeypatch.setenv("GAMEPI_PWM_BACKLIGHT", "0")

    payload = lib.brightness_status()

    assert payload["available"] is True
    assert payload["mode"] == "software"


def test_adjust_brightness_pwm_updates_state(tmp_path, monkeypatch) -> None:
    lib = _load_module("gamepi_brightness_lib", "gamepi_brightness_lib.py")
    monkeypatch.setattr(lib, "find_backlight", lambda: None)
    monkeypatch.setattr(lib, "pwm_available", lambda: False)
    monkeypatch.setattr(lib, "_run_gamma", lambda gamma: True)
    monkeypatch.setenv("GAMEPI_SOFTWARE_BRIGHTNESS", "1")
    monkeypatch.setenv("GAMEPI_PWM_BACKLIGHT", "0")
    monkeypatch.setattr(lib, "STATE_PATH", tmp_path / "brightness")
    monkeypatch.setenv("GAMEPI_BRIGHTNESS_DEFAULT", "200")

    payload = lib.adjust_brightness(-10)

    assert payload["ok"] is True
    assert payload["mode"] == "software"
    assert payload["level"] == 190


def test_adjust_brightness_reports_failure_when_pwm_apply_fails(tmp_path, monkeypatch) -> None:
    lib = _load_module("gamepi_brightness_lib", "gamepi_brightness_lib.py")
    monkeypatch.setattr(lib, "find_backlight", lambda: None)
    monkeypatch.setattr(lib, "pwm_available", lambda: True)
    monkeypatch.setattr(lib, "STATE_PATH", tmp_path / "brightness")
    monkeypatch.setattr(lib, "apply_pwm_level", lambda level, max_level=255: False)
    monkeypatch.setenv("GAMEPI_PWM_BACKLIGHT", "1")

    payload = lib.adjust_brightness(-10)

    assert payload["ok"] is False
    assert payload["mode"] == "pwm"


def test_brightness_delta_for_event_uses_device_name(monkeypatch) -> None:
    keys = _load_module("gamepi_gpio_keys", "gamepi_gpio_keys.py")
    monkeypatch.setenv("GAMEPI_BRIGHTNESS_STEP", "10")

    down = SimpleNamespace(type=1, value=1, code=keys.BRIGHTNESS_DOWN)
    up = SimpleNamespace(type=1, value=1, code=keys.BRIGHTNESS_UP)
    gpl = SimpleNamespace(name="GPL")
    gpr = SimpleNamespace(name="GPR")

    assert keys.brightness_delta_for_event(gpl, down) == -10
    assert keys.brightness_delta_for_event(gpr, up) == 10

    _, _, down_names, up_names = keys.brightness_button_names()
    assert "button@17" in down_names
    assert "button@e" in up_names
    assert "button@14" not in up_names


def test_boot_config_uart_blocks_gpio_14(monkeypatch, tmp_path: Path) -> None:
    keys = _load_module("gamepi_gpio_keys", "gamepi_gpio_keys.py")
    boot = tmp_path / "config.txt"
    boot.write_text(
        "\n".join(
            [
                "dtoverlay=waveshare13",
                "enable_uart=1",
                'dtoverlay=gpio-key,gpio=14,active_low=1,gpio_pull=up,label="GPR",keycode=225',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GAMEPI_BOOT_CONFIG", str(boot))

    assert keys.boot_config_uart_reserves_gpio_14() is True
    warnings = keys.boot_config_warnings()
    assert any("enable_uart" in warning for warning in warnings)


def test_boot_config_uart_disabled_allows_gpr_overlay(monkeypatch, tmp_path: Path) -> None:
    keys = _load_module("gamepi_gpio_keys", "gamepi_gpio_keys.py")
    boot = tmp_path / "config.txt"
    boot.write_text(
        "\n".join(
            [
                "enable_uart=0",
                'dtoverlay=gpio-key,gpio=14,active_low=1,gpio_pull=up,label="GPR",keycode=225',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GAMEPI_BOOT_CONFIG", str(boot))

    assert keys.boot_config_uart_reserves_gpio_14() is False
    warnings = keys.boot_config_warnings()
    assert not any("enable_uart" in warning for warning in warnings)


def test_brightness_backend_warnings_for_waveshare13(monkeypatch, tmp_path: Path) -> None:
    keys = _load_module("gamepi_gpio_keys", "gamepi_gpio_keys.py")
    boot = tmp_path / "config.txt"
    boot.write_text("dtoverlay=waveshare13\n", encoding="utf-8")
    monkeypatch.setenv("GAMEPI_BOOT_CONFIG", str(boot))

    warnings = keys.brightness_backend_warnings()
    assert any("GPIO 24" in warning for warning in warnings)
    assert any("software gamma" in warning for warning in warnings)

