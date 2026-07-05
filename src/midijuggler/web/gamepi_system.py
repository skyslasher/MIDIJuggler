"""GamePi system actions for the web API."""

from __future__ import annotations

import subprocess

from aiohttp import web


def request_reboot(request: web.Request) -> dict[str, bool]:
    host = request.remote or ""
    if host not in {"127.0.0.1", "::1", "::ffff:127.0.0.1"}:
        raise PermissionError("reboot is only allowed from localhost")
    subprocess.Popen(
        ["systemctl", "reboot"],
        start_new_session=True,
    )
    return {"ok": True}
