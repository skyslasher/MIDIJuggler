"""Coordinate RTP-MIDI discovery and per-adapter session hosting."""

from __future__ import annotations

import logging
from typing import Any, Literal

from midijuggler.config import AdapterConfig
from midijuggler.rtp_midi.avahi import (
    AvahiRtpMidiAnnouncer,
    AvahiRtpMidiDiscovery,
    avahi_tool_paths,
    avahi_tools_available,
)
from midijuggler.rtp_midi.discovery import (
    RtpMidiAnnouncer,
    RtpMidiDiscovery,
    local_mdns_server_name,
    rtp_session_id,
    zeroconf_available,
)

LOGGER = logging.getLogger(__name__)

RTP_ROLES = {"host", "join"}
RtpMidiBackendName = Literal["avahi", "zeroconf", "none"]


class RtpMidiManager:
    """Manage mDNS discovery and local RTP-MIDI session announcements."""

    def __init__(self) -> None:
        self._discovery: AvahiRtpMidiDiscovery | RtpMidiDiscovery | None = None
        self._announcers: dict[str, AvahiRtpMidiAnnouncer | RtpMidiAnnouncer] = {}
        self._instances: dict[str, AdapterConfig] = {}
        self._zeroconf: Any | None = None
        self._backend: RtpMidiBackendName = "none"
        self._publish_path: str | None = None
        self._browse_path: str | None = None
        self._startup_error: str | None = None

    @property
    def available(self) -> bool:
        return avahi_tools_available() or zeroconf_available()

    @property
    def backend(self) -> RtpMidiBackendName:
        return self._backend

    def status_summary(self) -> dict[str, Any]:
        publish_path, browse_path = avahi_tool_paths()
        discovery = self._discovery
        return {
            "backend": self._backend,
            "available": self.available,
            "avahi_tools": avahi_tools_available(),
            "avahi_publish_path": publish_path,
            "avahi_browse_path": browse_path,
            "zeroconf_installed": zeroconf_available(),
            "startup_error": self._startup_error,
            "active_announcers": len(self._announcers),
            "discovered_sessions": (
                len(discovery.sessions()) if discovery is not None else 0
            ),
        }

    def discovered_sessions(self) -> list[dict[str, Any]]:
        if self._discovery is None:
            return []
        return [session.as_dict() for session in self._discovery.sessions()]

    def hosted_session_ids(self) -> set[str]:
        hosted_ids: set[str] = set()
        for instance_name, config in self._instances.items():
            if instance_name not in self._announcers:
                continue
            if not config.enabled:
                continue
            if str(config.options.get("role", "host")) != "host":
                continue
            session_name = str(config.options.get("session_name", "")).strip()
            if not session_name:
                continue
            port = int(config.options.get("port", 5004))
            hosted_ids.add(
                rtp_session_id(session_name, local_mdns_server_name(), port)
            )
        return hosted_ids

    async def start(self) -> None:
        if self._backend != "none":
            return

        publish_path, browse_path = avahi_tool_paths()
        if publish_path is not None and browse_path is not None:
            self._publish_path = publish_path
            self._browse_path = browse_path
            self._discovery = AvahiRtpMidiDiscovery(browse_path)
            await self._discovery.start()
            self._backend = "avahi"
            self._startup_error = None
            LOGGER.info(
                "RTP-MIDI mDNS backend: avahi (%s, %s)",
                publish_path,
                browse_path,
            )
            return

        if not zeroconf_available():
            self._startup_error = (
                "install avahi-utils (avahi-publish-service, avahi-browse) or "
                "pip install midijuggler[rtp]"
            )
            LOGGER.warning("RTP-MIDI mDNS unavailable: %s", self._startup_error)
            return

        from zeroconf.asyncio import AsyncZeroconf

        try:
            self._zeroconf = AsyncZeroconf()
        except Exception as exc:
            self._startup_error = f"python-zeroconf failed: {exc}"
            LOGGER.exception(
                "failed to open python-zeroconf mDNS socket; on Linux with Avahi "
                "install avahi-utils and ensure avahi-daemon is running"
            )
            return

        self._discovery = RtpMidiDiscovery()
        await self._discovery.start(self._zeroconf)
        self._backend = "zeroconf"
        self._startup_error = None
        LOGGER.info("RTP-MIDI mDNS backend: python-zeroconf")

    async def stop(self) -> None:
        for instance_name in list(self._announcers):
            await self._stop_announcer(instance_name)
        if self._discovery is not None:
            await self._discovery.stop()
            self._discovery = None
        if self._zeroconf is not None:
            await self._zeroconf.async_close()
            self._zeroconf = None
        self._backend = "none"
        self._publish_path = None
        self._browse_path = None
        self._instances.clear()

    async def apply_instance(self, instance_name: str, config: AdapterConfig) -> None:
        self._instances[instance_name] = config
        await self._stop_announcer(instance_name)

        if not config.enabled:
            return

        role = str(config.options.get("role", "host"))
        if role == "host":
            session_name = str(config.options.get("session_name", "")).strip()
            port = int(config.options.get("port", 5004))
            if not session_name:
                LOGGER.warning(
                    "RTP-MIDI adapter %s is enabled in host mode without session_name",
                    instance_name,
                )
                return
            if self._backend == "none":
                await self.start()
            if self._backend == "none":
                LOGGER.warning(
                    "RTP-MIDI adapter %s cannot host session %s because mDNS is "
                    "unavailable (%s)",
                    instance_name,
                    session_name,
                    self._startup_error or self.status_summary(),
                )
                return

            if self._backend == "avahi":
                if self._publish_path is None:
                    LOGGER.warning(
                        "RTP-MIDI adapter %s cannot host session %s because avahi "
                        "publish path is missing",
                        instance_name,
                        session_name,
                    )
                    return
                announcer = AvahiRtpMidiAnnouncer(
                    session_name,
                    port,
                    self._publish_path,
                )
            else:
                announcer = RtpMidiAnnouncer(session_name, port, self._zeroconf)
            await announcer.start()
            self._announcers[instance_name] = announcer
            return

        if role == "join":
            join_target = str(config.options.get("join_target", "")).strip()
            if not join_target:
                LOGGER.warning(
                    "RTP-MIDI adapter %s is enabled in join mode without join_target",
                    instance_name,
                )
            else:
                LOGGER.info(
                    "RTP-MIDI adapter %s configured to join discovered session %s",
                    instance_name,
                    join_target,
                )

    async def remove_instance(self, instance_name: str) -> None:
        self._instances.pop(instance_name, None)
        await self._stop_announcer(instance_name)

    async def _stop_announcer(self, instance_name: str) -> None:
        announcer = self._announcers.pop(instance_name, None)
        if announcer is not None:
            await announcer.stop()
