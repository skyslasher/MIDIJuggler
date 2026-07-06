"""GamePi brightness helpers for the web API."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_scripts_path() -> None:
    app_root = os.environ.get("MIDIJUGGLER_APP_ROOT", "/opt/midijuggler/app")
    scripts = Path(app_root) / "scripts"
    if not scripts.is_dir():
        scripts = Path(__file__).resolve().parents[3] / "scripts"
    path = str(scripts)
    if path not in sys.path:
        sys.path.insert(0, path)
    gamma_script = scripts / "gamepi-apply-gamma.sh"
    os.environ.setdefault("GAMEPI_APPLY_GAMMA_SCRIPT", str(gamma_script))


def brightness_status_payload() -> dict[str, int | bool]:
    _ensure_scripts_path()
    from gamepi_brightness_lib import brightness_status

    return brightness_status()


def adjust_brightness_payload(delta: int) -> dict[str, int | bool]:
    _ensure_scripts_path()
    from gamepi_brightness_lib import adjust_brightness

    return adjust_brightness(delta)
