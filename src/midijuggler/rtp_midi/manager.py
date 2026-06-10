"""Coordinate RTP-MIDI discovery and per-adapter session hosting."""

from __future__ import annotations

import logging
from typing import Any

from midijuggler.config import AdapterConfig
from midijuggler.rtp_midi.discovery import RtpMidiAnnouncer, RtpMidiDiscovery, zeroconf_available

LOGGER = logging.getLogger(__name__)

RTP_ROLES = {"host", "join"}


class RtpMidiManager:
    """Manage mDNS discovery and local RTP-MIDI session announcements."""

    def __init__(self) -> None:
        self._discovery = RtpMidiDiscovery()
        self._announcers: dict[str, RtpMidiAnnouncer] = {}
        self._instances: dict[str, AdapterConfig] = {}

    @property
    def available(self) -> bool:
        return zeroconf_available()

    def discovered_sessions(self) -> list[dict[str, Any]]:
        return [session.as_dict() for session in self._discovery.sessions()]

    async def start(self) -> None:
        await self._discovery.start()

    async def stop(self) -> None:
        for instance_name in list(self._announcers):
            await self._stop_announcer(instance_name)
        await self._discovery.stop()
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
            announcer = RtpMidiAnnouncer(session_name, port)
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
