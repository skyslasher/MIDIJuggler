"""mDNS discovery and announcement for Apple MIDI / RTP-MIDI sessions."""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)

APPLE_MIDI_SERVICE_TYPE = "_apple-midi._udp.local."


@dataclass(frozen=True)
class RtpMidiSession:
    """One RTP-MIDI session announced on the local network."""

    id: str
    name: str
    host: str
    port: int
    addresses: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "addresses": list(self.addresses),
            "label": f"{self.name} ({self.host}:{self.port})",
        }


def parse_rtp_session_name(service_name: str) -> str:
    """Extract the human-readable RTP-MIDI session name from an mDNS entry."""

    base = service_name.removesuffix(APPLE_MIDI_SERVICE_TYPE)
    if base.endswith("."):
        base = base[:-1]
    if "@" in base:
        return base.split("@", 1)[0]
    return base


def rtp_session_id(name: str, host: str, port: int) -> str:
    return f"{host}:{port}:{name}"


def _preferred_ipv4_address() -> str:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def zeroconf_available() -> bool:
    try:
        import zeroconf  # noqa: F401
    except ImportError:
        return False
    return True


class RtpMidiDiscovery:
    """Browse the network for announced RTP-MIDI sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, RtpMidiSession] = {}
        self._zeroconf: Any | None = None
        self._browser: Any | None = None
        self._lock = asyncio.Lock()

    def sessions(self) -> list[RtpMidiSession]:
        return sorted(
            self._sessions.values(),
            key=lambda session: (session.name.lower(), session.host.lower(), session.port),
        )

    async def start(self) -> None:
        if not zeroconf_available():
            LOGGER.info("zeroconf is not installed; RTP-MIDI discovery is disabled")
            return

        async with self._lock:
            if self._browser is not None:
                return
            from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf

            self._zeroconf = AsyncZeroconf()
            listener = _RtpMidiServiceListener(self)
            self._browser = AsyncServiceBrowser(
                self._zeroconf.zeroconf,
                APPLE_MIDI_SERVICE_TYPE,
                listener,
            )
            LOGGER.info("started RTP-MIDI mDNS discovery")

    async def stop(self) -> None:
        async with self._lock:
            if self._browser is not None:
                await self._browser.async_cancel()
                self._browser = None
            if self._zeroconf is not None:
                await self._zeroconf.async_close()
                self._zeroconf = None
            self._sessions.clear()

    def _upsert_session(self, session: RtpMidiSession) -> None:
        self._sessions[session.id] = session

    def _remove_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


class _RtpMidiServiceListener:
    def __init__(self, discovery: RtpMidiDiscovery) -> None:
        self._discovery = discovery

    async def add_service(self, zc: Any, type_: str, name: str) -> None:
        await self._update_service(zc, type_, name)

    async def update_service(self, zc: Any, type_: str, name: str) -> None:
        await self._update_service(zc, type_, name)

    async def remove_service(self, zc: Any, type_: str, name: str) -> None:
        session_name = parse_rtp_session_name(name)
        for session_id, session in list(self._discovery._sessions.items()):
            if session.name == session_name:
                self._discovery._remove_session(session_id)

    async def _update_service(self, zc: Any, type_: str, name: str) -> None:
        info = await zc.async_get_service_info(type_, name, timeout=1500)
        if info is None:
            return

        session_name = parse_rtp_session_name(name)
        host = info.server or session_name
        port = int(info.port or 0)
        if port <= 0:
            return

        addresses = tuple(
            socket.inet_ntoa(address)
            for address in info.addresses
            if len(address) == 4
        )
        session = RtpMidiSession(
            id=rtp_session_id(session_name, host, port),
            name=session_name,
            host=host,
            port=port,
            addresses=addresses,
        )
        self._discovery._upsert_session(session)


class RtpMidiAnnouncer:
    """Publish one local RTP-MIDI session via mDNS."""

    def __init__(self, session_name: str, port: int) -> None:
        self.session_name = session_name
        self.port = port
        self._zeroconf: Any | None = None
        self._info: Any | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if not zeroconf_available():
            LOGGER.warning(
                "zeroconf is not installed; cannot announce RTP-MIDI session %s",
                self.session_name,
            )
            return

        async with self._lock:
            if self._info is not None:
                return

            from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf

            address = socket.inet_aton(_preferred_ipv4_address())
            service_name = f"{self.session_name}.{APPLE_MIDI_SERVICE_TYPE}"
            self._info = AsyncServiceInfo(
                APPLE_MIDI_SERVICE_TYPE,
                service_name,
                addresses=[address],
                port=self.port,
                properties={"txtvers": "1", "ver": "2"},
            )
            self._zeroconf = AsyncZeroconf()
            await self._zeroconf.async_register_service(self._info)
            LOGGER.info(
                "announced RTP-MIDI session %s on UDP port %s",
                self.session_name,
                self.port,
            )

    async def stop(self) -> None:
        async with self._lock:
            if self._zeroconf is None or self._info is None:
                return
            await self._zeroconf.async_unregister_service(self._info)
            await self._zeroconf.async_close()
            self._zeroconf = None
            self._info = None
