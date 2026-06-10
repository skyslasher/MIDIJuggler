"""RTP-MIDI mDNS via Avahi CLI tools on Linux."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from midijuggler.rtp_midi.discovery import (
    APPLE_MIDI_SERVICE_TYPE,
    RtpMidiSession,
    parse_rtp_session_name,
    rtp_session_id,
)

LOGGER = logging.getLogger(__name__)

_AVAHI_SERVICE_TYPE = "_apple-midi._udp"
_BROWSE_INTERVAL_SECONDS = 5.0
_PUBLISH_CANDIDATES = ("avahi-publish-service", "/usr/bin/avahi-publish-service")
_BROWSE_CANDIDATES = ("avahi-browse", "/usr/bin/avahi-browse")


def _resolve_executable(candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate.startswith("/"):
            path = Path(candidate)
            if path.is_file() and os.access(path, os.X_OK):
                return str(path)
            continue
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def avahi_tool_paths() -> tuple[str | None, str | None]:
    return (
        _resolve_executable(_PUBLISH_CANDIDATES),
        _resolve_executable(_BROWSE_CANDIDATES),
    )


def avahi_tools_available() -> bool:
    publish_path, browse_path = avahi_tool_paths()
    return publish_path is not None and browse_path is not None


def parse_avahi_browse_line(line: str) -> RtpMidiSession | None:
    """Parse one `avahi-browse -rpt` line into a session."""

    if not line.startswith("="):
        return None

    parts = line.split(";")
    if len(parts) < 10:
        return None

    service_name = parts[3].strip()
    service_type = parts[4].strip()
    if service_type not in {_AVAHI_SERVICE_TYPE, APPLE_MIDI_SERVICE_TYPE.rstrip(".")}:
        return None

    host = parts[6].strip() or "unknown.local."
    if not host.endswith("."):
        host = f"{host}."

    address = parts[7].strip()
    try:
        port = int(parts[8].strip())
    except ValueError:
        return None
    if port <= 0:
        return None

    session_name = parse_rtp_session_name(f"{service_name}.{APPLE_MIDI_SERVICE_TYPE}")
    addresses = (address,) if address else ()
    return RtpMidiSession(
        id=rtp_session_id(session_name, host, port),
        name=session_name,
        host=host,
        port=port,
        addresses=addresses,
    )


class AvahiRtpMidiDiscovery:
    """Poll avahi-browse for Apple MIDI services."""

    def __init__(self, browse_path: str) -> None:
        self._browse_path = browse_path
        self._sessions: dict[str, RtpMidiSession] = {}
        self._task: asyncio.Task[None] | None = None
        self._running = False

    def sessions(self) -> list[RtpMidiSession]:
        return sorted(
            self._sessions.values(),
            key=lambda session: (session.name.lower(), session.host.lower(), session.port),
        )

    async def start(self) -> None:
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop(), name="avahi-rtp-midi-browse")
        LOGGER.info("started RTP-MIDI discovery via %s", self._browse_path)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._sessions.clear()

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self._refresh_sessions()
            except Exception:
                LOGGER.exception("RTP-MIDI avahi-browse poll failed")
            await asyncio.sleep(_BROWSE_INTERVAL_SECONDS)

    async def _refresh_sessions(self) -> None:
        process = await asyncio.create_subprocess_exec(
            self._browse_path,
            "-a",
            "-r",
            "-p",
            "-t",
            _AVAHI_SERVICE_TYPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip()
            LOGGER.warning("%s failed (%s): %s", self._browse_path, process.returncode, message)
            return

        discovered: dict[str, RtpMidiSession] = {}
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            session = parse_avahi_browse_line(line.strip())
            if session is not None:
                discovered[session.id] = session

        for session_id, session in discovered.items():
            if session_id not in self._sessions:
                LOGGER.info(
                    "discovered RTP-MIDI session %s at %s:%s",
                    session.name,
                    session.host,
                    session.port,
                )
        for session_id, session in list(self._sessions.items()):
            if session_id not in discovered:
                LOGGER.info(
                    "removed RTP-MIDI session %s at %s:%s",
                    session.name,
                    session.host,
                    session.port,
                )

        self._sessions = discovered


class AvahiRtpMidiAnnouncer:
    """Publish one RTP-MIDI session through avahi-daemon."""

    def __init__(self, session_name: str, port: int, publish_path: str) -> None:
        self.session_name = session_name
        self.port = port
        self._publish_path = publish_path
        self._process: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        if self._process is not None and self._process.returncode is None:
            return

        self._process = await asyncio.create_subprocess_exec(
            self._publish_path,
            self.session_name,
            _AVAHI_SERVICE_TYPE,
            str(self.port),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.sleep(0.2)
        if self._process.returncode is not None:
            stderr = b""
            if self._process.stderr is not None:
                stderr = await self._process.stderr.read()
            LOGGER.error(
                "failed to announce RTP-MIDI session %s on UDP %s via %s: %s",
                self.session_name,
                self.port,
                self._publish_path,
                stderr.decode("utf-8", errors="replace").strip(),
            )
            self._process = None
            return

        LOGGER.info(
            "announced RTP-MIDI session %s via %s on UDP %s",
            self.session_name,
            self._publish_path,
            self.port,
        )

    async def stop(self) -> None:
        if self._process is None:
            return
        if self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=3)
            except TimeoutError:
                self._process.kill()
                await self._process.wait()
        self._process = None
