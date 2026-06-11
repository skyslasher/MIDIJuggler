"""Hostname helpers for stage boxes."""

from __future__ import annotations

import asyncio
import logging
import re
import socket
from pathlib import Path

LOGGER = logging.getLogger(__name__)

_HOSTNAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


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
    return Path(__file__).resolve().parents[2] / "scripts"


def set_hostname_script() -> Path:
    return scripts_dir() / "set-hostname.sh"


def restart_service_script() -> Path:
    return scripts_dir() / "restart-midijuggler.sh"


async def _sudo_script_allowed(script: Path) -> bool:
    if not script.is_file():
        return False
    process = await asyncio.create_subprocess_exec(
        "sudo",
        "-n",
        "-l",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        return False
    listing = stdout.decode("utf-8", errors="replace")
    script_path = str(script.resolve())
    return script_path in listing or str(script) in listing


async def can_set_hostname() -> bool:
    return await _sudo_script_allowed(set_hostname_script())


async def can_restart_service() -> bool:
    return await _sudo_script_allowed(restart_service_script())


async def _run_sudo_script(script: Path, *arguments: str) -> None:
    if not script.is_file():
        raise OSError(f"helper script not found: {script}")
    process = await asyncio.create_subprocess_exec(
        "sudo",
        "-n",
        str(script),
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        if not detail:
            detail = stdout.decode("utf-8", errors="replace").strip()
        raise OSError(detail or f"{script.name} exited with code {process.returncode}")


async def apply_hostname(hostname: str) -> str:
    normalized = validate_hostname(hostname)
    current = get_hostname()
    if normalized == current:
        return normalized
    await _run_sudo_script(set_hostname_script(), normalized)
    LOGGER.info("system hostname changed from %s to %s", current, normalized)
    return normalized


async def restart_service() -> None:
    await _run_sudo_script(restart_service_script(), "restart")
