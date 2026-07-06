"""GamePi system actions for the web API."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from aiohttp import web


def _reboot_script() -> Path:
    app_root = Path(os.environ.get("MIDIJUGGLER_APP_ROOT", "/opt/midijuggler/app"))
    return app_root / "scripts" / "gamepi-reboot.sh"


def request_reboot(request: web.Request) -> dict[str, bool | str]:
    host = request.remote or ""
    if host not in {"127.0.0.1", "::1", "::ffff:127.0.0.1"}:
        raise PermissionError("reboot is only allowed from localhost")

    script = _reboot_script()
    if script.is_file():
        command = ["sudo", "-n", str(script)]
    else:
        command = ["/usr/bin/systemctl", "reboot"]

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc)}

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "reboot failed").strip()
        return {"ok": False, "error": detail}

    return {"ok": True}
