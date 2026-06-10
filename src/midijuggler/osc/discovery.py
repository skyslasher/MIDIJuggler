"""LAN discovery for Behringer Wing and X32 OSC desks."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from dataclasses import dataclass
from typing import Any

from midijuggler.osc.protocol import decode_messages, encode_message

LOGGER = logging.getLogger(__name__)

WING_DISCOVERY_PORT = 2222
WING_DISCOVERY_MESSAGE = b"WING?"
X32_OSC_PORT = 10023
X32_SCAN_CONCURRENCY = 64


@dataclass(frozen=True)
class DiscoveredDesk:
    protocol: str
    ip: str
    name: str = ""
    model: str = ""
    firmware: str = ""
    serial: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "ip": self.ip,
            "name": self.name,
            "model": self.model,
            "firmware": self.firmware,
            "serial": self.serial,
        }


def parse_wing_discovery_response(data: bytes) -> DiscoveredDesk | None:
    try:
        text = data.decode("ascii", errors="ignore").strip()
    except UnicodeDecodeError:
        return None
    if not text.startswith("WING,"):
        return None
    parts = text.split(",")
    if len(parts) < 6:
        return None
    return DiscoveredDesk(
        protocol="wing",
        ip=parts[1].strip(),
        name=parts[2].strip(),
        model=parts[3].strip(),
        serial=parts[4].strip(),
        firmware=parts[5].strip(),
    )


def parse_x32_info_response(data: bytes, source_ip: str) -> DiscoveredDesk | None:
    try:
        messages = decode_messages(data)
    except ValueError:
        return None

    for address, arguments in messages:
        if address not in {"/info", "/xinfo"}:
            continue
        strings = [str(argument) for argument in arguments if isinstance(argument, str)]
        if not strings:
            continue
        if address == "/xinfo" and len(strings) >= 2:
            return DiscoveredDesk(
                protocol="x32",
                ip=source_ip,
                name=strings[1].strip(),
                model=strings[0].strip(),
                firmware=strings[2].strip() if len(strings) > 2 else "",
            )
        model = strings[0].strip() if strings else "X32"
        name = strings[2].strip() if len(strings) > 2 else model
        firmware = strings[3].strip() if len(strings) > 3 else (
            strings[1].strip() if len(strings) > 1 else ""
        )
        return DiscoveredDesk(
            protocol="x32",
            ip=source_ip,
            name=name,
            model=model,
            firmware=firmware,
        )
    return None


def local_ipv4_networks() -> list[ipaddress.IPv4Network]:
    networks: list[ipaddress.IPv4Network] = []
    seen: set[str] = set()

    try:
        hostname = socket.gethostname()
        host_ips = socket.gethostbyname_ex(hostname)[2]
    except OSError:
        host_ips = []

    for host_ip in host_ips:
        if host_ip.startswith("127."):
            continue
        try:
            interface = ipaddress.ip_address(host_ip)
        except ValueError:
            continue
        if not isinstance(interface, ipaddress.IPv4Address):
            continue
        network = ipaddress.ip_network(f"{interface}/24", strict=False)
        key = str(network)
        if key in seen:
            continue
        seen.add(key)
        networks.append(network)

    if not networks:
        for fallback in ("192.168.1.0/24", "192.168.0.0/24", "10.0.0.0/24"):
            network = ipaddress.ip_network(fallback, strict=False)
            if str(network) not in seen:
                seen.add(str(network))
                networks.append(network)
    return networks


async def discover_wing(timeout: float = 2.0) -> list[DiscoveredDesk]:
    loop = asyncio.get_running_loop()
    found: dict[str, DiscoveredDesk] = {}
    transport: asyncio.DatagramTransport | None = None

    class _WingDiscoveryProtocol(asyncio.DatagramProtocol):
        def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
            desk = parse_wing_discovery_response(data)
            if desk is None:
                return
            found[desk.ip] = desk

    try:
        transport, _protocol = await loop.create_datagram_endpoint(
            _WingDiscoveryProtocol,
            local_addr=("0.0.0.0", 0),
        )
        targets = {(str(network.broadcast_address), WING_DISCOVERY_PORT) for network in local_ipv4_networks()}
        targets.add(("255.255.255.255", WING_DISCOVERY_PORT))
        for target in targets:
            transport.sendto(WING_DISCOVERY_MESSAGE, target)
        await asyncio.sleep(timeout)
    finally:
        if transport is not None:
            transport.close()

    return sorted(found.values(), key=lambda desk: desk.ip)


async def discover_x32(timeout: float = 3.0) -> list[DiscoveredDesk]:
    loop = asyncio.get_running_loop()
    found: dict[str, DiscoveredDesk] = {}
    transport: asyncio.DatagramTransport | None = None
    probe_payload = encode_message("/info", [])

    class _X32DiscoveryProtocol(asyncio.DatagramProtocol):
        def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
            desk = parse_x32_info_response(data, addr[0])
            if desk is not None:
                found[desk.ip] = desk

    try:
        transport, _protocol = await loop.create_datagram_endpoint(
            _X32DiscoveryProtocol,
            local_addr=("0.0.0.0", 0),
        )
        hosts = [
            str(host)
            for network in local_ipv4_networks()
            for host in network.hosts()
        ]
        semaphore = asyncio.Semaphore(X32_SCAN_CONCURRENCY)

        async def probe(host: str) -> None:
            async with semaphore:
                transport.sendto(probe_payload, (host, X32_OSC_PORT))

        await asyncio.gather(*(probe(host) for host in hosts))
        await asyncio.sleep(timeout)
    finally:
        if transport is not None:
            transport.close()

    return sorted(found.values(), key=lambda desk: desk.ip)


async def discover_desks(protocols: list[str] | None = None) -> list[DiscoveredDesk]:
    selected = {protocol.strip().lower() for protocol in (protocols or ["wing", "x32"])}
    tasks: list[asyncio.Task[list[DiscoveredDesk]]] = []
    if "wing" in selected:
        tasks.append(asyncio.create_task(discover_wing()))
    if "x32" in selected:
        tasks.append(asyncio.create_task(discover_x32()))
    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)
    desks: dict[str, DiscoveredDesk] = {}
    for result in results:
        if isinstance(result, Exception):
            LOGGER.warning("OSC desk discovery task failed: %s", result)
            continue
        for desk in result:
            desks[f"{desk.protocol}:{desk.ip}"] = desk
    return sorted(desks.values(), key=lambda desk: (desk.protocol, desk.ip))
