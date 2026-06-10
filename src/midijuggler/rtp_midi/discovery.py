"""mDNS discovery and announcement for Apple MIDI / RTP-MIDI sessions."""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass
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


def local_mdns_server_name() -> str:
    """Return the mDNS host name used in Apple MIDI SRV records."""

    hostname = socket.gethostname().split(".", 1)[0].strip() or "midijuggler"
    return f"{hostname}.local."


def build_apple_midi_service_name(session_name: str) -> str:
    """Build the DNS-SD instance name for an Apple MIDI session."""

    return f"{session_name}.{APPLE_MIDI_SERVICE_TYPE}"


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


def _session_from_service_info(service_name: str, info: Any) -> RtpMidiSession | None:
    session_name = parse_rtp_session_name(service_name)
    host = info.server or local_mdns_server_name()
    port = int(info.port or 0)
    if port <= 0:
        return None

    addresses = tuple(
        socket.inet_ntoa(address)
        for address in info.addresses
        if len(address) == 4
    )
    return RtpMidiSession(
        id=rtp_session_id(session_name, host, port),
        name=session_name,
        host=host,
        port=port,
        addresses=addresses,
    )


class RtpMidiDiscovery:
    """Browse the network for announced RTP-MIDI sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, RtpMidiSession] = {}
        self._zeroconf: Any | None = None
        self._browser: Any | None = None
        self._owns_zeroconf = False
        self._lock = asyncio.Lock()

    def sessions(self) -> list[RtpMidiSession]:
        return sorted(
            self._sessions.values(),
            key=lambda session: (session.name.lower(), session.host.lower(), session.port),
        )

    async def start(self, zeroconf: Any | None = None) -> None:
        if not zeroconf_available():
            LOGGER.info("zeroconf is not installed; RTP-MIDI discovery is disabled")
            return

        async with self._lock:
            if self._browser is not None:
                return

            from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf

            if zeroconf is not None:
                self._zeroconf = zeroconf
                self._owns_zeroconf = False
            else:
                self._zeroconf = AsyncZeroconf()
                self._owns_zeroconf = True

            listener = _RtpMidiServiceListener(self)
            try:
                self._browser = AsyncServiceBrowser(
                    self._zeroconf.zeroconf,
                    APPLE_MIDI_SERVICE_TYPE,
                    listener,
                )
            except OSError:
                LOGGER.exception("failed to start RTP-MIDI mDNS discovery")
                if self._owns_zeroconf and self._zeroconf is not None:
                    await self._zeroconf.async_close()
                    self._zeroconf = None
                return

            LOGGER.info("started RTP-MIDI mDNS discovery")

    async def stop(self) -> None:
        async with self._lock:
            if self._browser is not None:
                await self._browser.async_cancel()
                self._browser = None
            if self._owns_zeroconf and self._zeroconf is not None:
                await self._zeroconf.async_close()
            self._zeroconf = None
            self._owns_zeroconf = False
            self._sessions.clear()

    def _upsert_session(self, session: RtpMidiSession) -> None:
        previous = self._sessions.get(session.id)
        self._sessions[session.id] = session
        if previous is None:
            LOGGER.info(
                "discovered RTP-MIDI session %s at %s:%s",
                session.name,
                session.host,
                session.port,
            )

    def _remove_session(self, session_id: str) -> None:
        removed = self._sessions.pop(session_id, None)
        if removed is not None:
            LOGGER.info(
                "removed RTP-MIDI session %s at %s:%s",
                removed.name,
                removed.host,
                removed.port,
            )


class _RtpMidiServiceListener:
    """Sync listener callbacks required by python-zeroconf."""

    def __init__(self, discovery: RtpMidiDiscovery) -> None:
        self._discovery = discovery

    def add_service(self, zc: Any, type_: str, name: str) -> None:
        self._update_service(zc, type_, name)

    def update_service(self, zc: Any, type_: str, name: str) -> None:
        self._update_service(zc, type_, name)

    def remove_service(self, zc: Any, type_: str, name: str) -> None:
        session_name = parse_rtp_session_name(name)
        for session_id, session in list(self._discovery._sessions.items()):
            if session.name == session_name:
                self._discovery._remove_session(session_id)

    def _update_service(self, zc: Any, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name, timeout=3000)
        if info is None:
            LOGGER.debug("no mDNS details yet for RTP-MIDI service %s", name)
            return

        session = _session_from_service_info(name, info)
        if session is None:
            LOGGER.debug("ignored incomplete RTP-MIDI service %s", name)
            return

        self._discovery._upsert_session(session)


class RtpMidiAnnouncer:
    """Publish one local RTP-MIDI session via mDNS."""

    def __init__(self, session_name: str, port: int, zeroconf: Any) -> None:
        self.session_name = session_name
        self.port = port
        self._zeroconf = zeroconf
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

            from zeroconf import ServiceInfo

            address = socket.inet_aton(_preferred_ipv4_address())
            server = local_mdns_server_name()
            service_name = build_apple_midi_service_name(self.session_name)
            self._info = ServiceInfo(
                APPLE_MIDI_SERVICE_TYPE,
                service_name,
                addresses=[address],
                port=self.port,
                properties={"txtvers": "1", "ver": "2"},
                server=server,
            )
            try:
                await self._zeroconf.async_register_service(self._info)
            except OSError:
                LOGGER.exception(
                    "failed to announce RTP-MIDI session %s on UDP port %s; "
                    "check Avahi port 5353 sharing (disallow-other-stacks=no)",
                    self.session_name,
                    self.port,
                )
                self._info = None
                return

            LOGGER.info(
                "announced RTP-MIDI session %s as %s on %s UDP %s",
                self.session_name,
                service_name,
                server,
                self.port,
            )

    async def stop(self) -> None:
        async with self._lock:
            if self._zeroconf is None or self._info is None:
                return
            try:
                await self._zeroconf.async_unregister_service(self._info)
            except OSError:
                LOGGER.exception(
                    "failed to unregister RTP-MIDI session %s",
                    self.session_name,
                )
            self._info = None
