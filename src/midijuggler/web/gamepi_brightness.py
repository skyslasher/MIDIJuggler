"""GamePi brightness helpers for the web API."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

_STATUS_CACHE: tuple[float, dict[str, int | bool | str]] | None = None
_STATUS_CACHE_TTL = float(os.environ.get("GAMEPI_BRIGHTNESS_STATUS_CACHE_SEC", "5"))


def _app_root() -> Path:
    app_root = os.environ.get("MIDIJUGGLER_APP_ROOT", "/opt/midijuggler/app")
    root = Path(app_root)
    if root.is_dir():
        return root
    return Path(__file__).resolve().parents[3]


def _scripts_dir() -> Path:
    return _app_root() / "scripts"


def _brightness_runner() -> Path:
    return _scripts_dir() / "gamepi-brightness-run.sh"


def _import_brightness_lib():
    scripts = str(_scripts_dir())
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import gamepi_brightness_lib

    return gamepi_brightness_lib


def _direct_brightness_status() -> dict[str, int | bool | str] | None:
    try:
        return _import_brightness_lib().brightness_status()
    except Exception:
        return None


def _direct_adjust_brightness(delta: int) -> dict[str, int | bool | str] | None:
    try:
        payload = _import_brightness_lib().adjust_brightness(delta)
    except Exception:
        return None
    if not payload.get("available") or not payload.get("ok"):
        return None
    return payload


def _direct_set_brightness(level: int) -> dict[str, int | bool | str] | None:
    try:
        payload = _import_brightness_lib().set_brightness(level)
    except Exception:
        return None
    if not payload.get("available") or not payload.get("ok"):
        return None
    return payload


def _run_brightness_cli(*args: str) -> dict[str, int | bool | str]:
    runner = _brightness_runner()
    if not runner.is_file():
        return {"ok": False, "available": False, "mode": "none"}
    command = ["sudo", "-n", str(runner), *args]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "available": False, "mode": "none"}
    output = result.stdout.strip()
    if not output:
        return {"ok": False, "available": False, "mode": "none"}
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"ok": False, "available": False, "mode": "none"}


def _cache_status(payload: dict[str, int | bool | str]) -> dict[str, int | bool | str]:
    global _STATUS_CACHE
    _STATUS_CACHE = (time.monotonic(), payload)
    return payload


def _invalidate_status_cache() -> None:
    global _STATUS_CACHE
    _STATUS_CACHE = None


def brightness_status_payload(*, fresh: bool = False) -> dict[str, int | bool | str]:
    global _STATUS_CACHE
    now = time.monotonic()
    if not fresh and _STATUS_CACHE is not None:
        cached_at, payload = _STATUS_CACHE
        if now - cached_at < _STATUS_CACHE_TTL:
            return payload

    payload = _direct_brightness_status()
    if payload is None:
        payload = _run_brightness_cli("--status")
    return _cache_status(payload)


def adjust_brightness_payload(delta: int) -> dict[str, int | bool | str]:
    _invalidate_status_cache()
    payload = _direct_adjust_brightness(delta)
    if payload is not None:
        return payload
    return _run_brightness_cli("--delta", str(delta))


def set_brightness_payload(level: int) -> dict[str, int | bool | str]:
    _invalidate_status_cache()
    payload = _direct_set_brightness(level)
    if payload is not None:
        return payload
    return _run_brightness_cli("--set", str(level))
