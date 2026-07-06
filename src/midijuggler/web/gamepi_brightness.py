"""GamePi brightness helpers for the web API."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def _app_root() -> Path:
    app_root = os.environ.get("MIDIJUGGLER_APP_ROOT", "/opt/midijuggler/app")
    root = Path(app_root)
    if root.is_dir():
        return root
    return Path(__file__).resolve().parents[3]


def _brightness_python() -> str:
    return os.environ.get("GAMEPI_BRIGHTNESS_PYTHON", "/usr/bin/python3")


def _brightness_script() -> Path:
    return _app_root() / "scripts" / "gamepi-brightness-adjust.py"


def _run_brightness_cli(*args: str) -> dict[str, int | bool | str]:
    script = _brightness_script()
    if not script.is_file():
        return {"ok": False, "available": False, "mode": "none"}
    try:
        result = subprocess.run(
            [_brightness_python(), str(script), *args],
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


def brightness_status_payload() -> dict[str, int | bool | str]:
    return _run_brightness_cli("--status")


def adjust_brightness_payload(delta: int) -> dict[str, int | bool | str]:
    return _run_brightness_cli("--delta", str(delta))
