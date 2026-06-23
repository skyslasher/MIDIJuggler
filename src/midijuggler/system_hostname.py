"""Hostname helpers for stage boxes."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

_HOSTNAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_DEFAULT_SCRIPTS_DIR = Path("/opt/midijuggler/app/scripts")


def get_hostname() -> str:
    return socket.gethostname().split(".", 1)[0].strip() or "midijuggler"


def validate_hostname(hostname: str) -> str:
    normalized = hostname.strip().lower()
    if not normalized:
        raise ValueError("hostname is required")
    if len(normalized) > 63:
        raise ValueError("hostname must be at most 63 characters")
    if not _HOSTNAME_PATTERN.fullmatch(normalized):
        raise ValueError(
            "hostname may contain only letters, digits and hyphens "
            "and must start/end with a letter or digit"
        )
    return normalized


def scripts_dir() -> Path:
    configured = os.environ.get("MIDIJUGGLER_SCRIPTS_DIR", "").strip()
    if configured:
        return Path(configured)

    candidates = [
        Path(__file__).resolve().parents[2] / "scripts",
        _DEFAULT_SCRIPTS_DIR,
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def set_hostname_script() -> Path:
    return scripts_dir() / "set-hostname.sh"


def restart_service_script() -> Path:
    return scripts_dir() / "restart-midijuggler.sh"


def system_diagnostics() -> dict[str, Any]:
    set_script = set_hostname_script()
    restart_script = restart_service_script()
    return {
        "scripts_dir": str(scripts_dir()),
        "set_hostname_script": str(set_script),
        "restart_service_script": str(restart_script),
        "set_hostname_script_exists": set_script.is_file(),
        "restart_service_script_exists": restart_script.is_file(),
    }


async def _run_subprocess(*args: str) -> tuple[int, bytes, bytes]:
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        LOGGER.debug("subprocess unavailable for %s: %s", args[0], exc)
        return 127, b"", str(exc).encode("utf-8")
    stdout, stderr = await process.communicate()
    return process.returncode or 0, stdout, stderr


async def _sudo_listing() -> str:
    returncode, stdout, stderr = await _run_subprocess("sudo", "-n", "-l")
    if returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        if detail:
            LOGGER.debug("sudo -l failed: %s", detail)
        return ""
    return stdout.decode("utf-8", errors="replace")


def _script_listed_in_sudoers(listing: str, script: Path) -> bool:
    if not listing:
        return False
    resolved = str(script.resolve())
    return resolved in listing or script.name in listing


async def _sudo_credentials_valid() -> bool:
    returncode, _, _ = await _run_subprocess("sudo", "-n", "-v")
    return returncode == 0


async def can_set_hostname() -> bool:
    script = set_hostname_script()
    if not script.is_file():
        return False
    if not await _sudo_credentials_valid():
        return False
    listing = await _sudo_listing()
    return _script_listed_in_sudoers(listing, script)


async def can_restart_service() -> bool:
    script = restart_service_script()
    if not script.is_file():
        return False
    if not await _sudo_credentials_valid():
        return False
    listing = await _sudo_listing()
    return _script_listed_in_sudoers(listing, script)


async def capability_message() -> str | None:
    diagnostics = system_diagnostics()
    if not diagnostics["set_hostname_script_exists"]:
        return (
            f"helper script missing: {diagnostics['set_hostname_script']} "
            "(run git pull and chmod +x scripts/*.sh)"
        )
    if not diagnostics["restart_service_script_exists"]:
        return (
            f"helper script missing: {diagnostics['restart_service_script']} "
            "(run git pull and chmod +x scripts/*.sh)"
        )
    if not await _sudo_credentials_valid():
        return (
            "passwordless sudo is unavailable for the midijuggler service user; "
            "install systemd/midijuggler-sudoers.example and ensure "
            "NoNewPrivileges is not enabled in midijuggler.service"
        )
    listing = await _sudo_listing()
    if not _script_listed_in_sudoers(listing, set_hostname_script()):
        return (
            "sudoers does not allow the hostname helper script; "
            "install systemd/midijuggler-sudoers.example as /etc/sudoers.d/midijuggler"
        )
    if not _script_listed_in_sudoers(listing, restart_service_script()):
        return (
            "sudoers does not allow the restart helper script; "
            "install systemd/midijuggler-sudoers.example as /etc/sudoers.d/midijuggler"
        )
    return None


async def _run_sudo_script(script: Path, *arguments: str) -> None:
    if not script.is_file():
        raise OSError(f"helper script not found: {script}")
    command = ("sudo", "-n", str(script), *arguments)
    LOGGER.info("running stage helper: %s", " ".join(command))
    returncode, stdout, stderr = await _run_subprocess(*command)
    if returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        if not detail:
            detail = stdout.decode("utf-8", errors="replace").strip()
        LOGGER.error(
            "stage helper failed (%s): %s",
            script.name,
            detail or f"exit code {returncode}",
        )
        raise OSError(detail or f"{script.name} exited with code {returncode}")


async def apply_hostname(hostname: str) -> tuple[str, bool]:
    normalized = validate_hostname(hostname)
    current = get_hostname()
    if normalized == current:
        LOGGER.info("hostname already %s; no system change required", normalized)
        return normalized, False
    await _run_sudo_script(set_hostname_script(), normalized)
    LOGGER.info("system hostname changed from %s to %s", current, normalized)
    return normalized, True


async def restart_service() -> None:
    await _run_sudo_script(restart_service_script())
