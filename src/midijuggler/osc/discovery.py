"""LAN discovery for Behringer Wing and X32 OSC desks."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import platform
import re
import socket
import subprocess
from dataclasses import dataclass
from typing import Any

from midijuggler.osc.protocol import decode_messages, encode_message

LOGGER = logging.getLogger(__name__)

WING_DISCOVERY_PORT = 2222
WING_DISCOVERY_MESSAGE = b"WING?"
X32_OSC_PORT = 10023
X32_SCAN_CONCURRENCY = 64
WING_UNICAST_CONCURRENCY = 64
MIN_SCAN_PREFIX_LEN = 20

_IP_ADDR_PATTERN = re.compile(
    r"inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)(?:\s+brd\s+(\d+\.\d+\.\d+\.\d+))?"
)
_IFCONFIG_INET_PATTERN = re.compile(
    r"^\s*inet\s+(\d+\.\d+\.\d+\.\d+)\s+"
    r"(?:netmask\s+(?:0x([0-9a-fA-F]+)|(\d+\.\d+\.\d+\.\d+)))?"
    r"(?:\s+broadcast\s+(\d+\.\d+\.\d+\.\d+))?",
)


@dataclass(frozen=True)
class IPv4Interface:
    address: ipaddress.IPv4Address
    network: ipaddress.IPv4Network
    broadcast: ipaddress.IPv4Address


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


def parse_wing_discovery_response(
    data: bytes,
    source_ip: str = "",
) -> DiscoveredDesk | None:
    try:
        text = data.decode("ascii", errors="ignore").strip()
    except UnicodeDecodeError:
        return None
    if not text.upper().startswith("WING,"):
        return None
    parts = text.split(",")
    if len(parts) < 6:
        return None
    ip = source_ip.strip() or parts[1].strip()
    if not ip:
        return None
    return DiscoveredDesk(
        protocol="wing",
        ip=ip,
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
        strings = _osc_argument_strings(arguments)
        if not strings:
            continue
        if address == "/xinfo" and len(strings) >= 2:
            return DiscoveredDesk(
                protocol="x32",
                ip=source_ip,
                name=strings[1].strip(),
                model=strings[2].strip() if len(strings) > 2 else "X32",
                firmware=strings[3].strip() if len(strings) > 3 else "",
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


def _osc_argument_strings(arguments: tuple[Any, ...]) -> list[str]:
    strings: list[str] = []
    for argument in arguments:
        if isinstance(argument, str):
            value = argument.strip()
        elif isinstance(argument, (int, float)):
            value = str(argument).strip()
        else:
            continue
        if value:
            strings.append(value)
    return strings


def _parse_ipv4_interfaces_from_ip_output(output: str) -> list[IPv4Interface]:
    interfaces: list[IPv4Interface] = []
    seen: set[str] = set()
    for line in output.splitlines():
        match = _IP_ADDR_PATTERN.search(line)
        if match is None:
            continue
        address = ipaddress.ip_address(match.group(1))
        if not isinstance(address, ipaddress.IPv4Address) or address.is_loopback:
            continue
        network = ipaddress.ip_network(f"{address}/{match.group(2)}", strict=False)
        if match.group(3):
            broadcast = ipaddress.ip_address(match.group(3))
        else:
            broadcast = network.broadcast_address
        if not isinstance(broadcast, ipaddress.IPv4Address):
            continue
        key = f"{address}/{network.prefixlen}"
        if key in seen:
            continue
        seen.add(key)
        interfaces.append(
            IPv4Interface(
                address=address,
                network=network,
                broadcast=broadcast,
            )
        )
    return interfaces


def _netmask_to_prefix(netmask_hex: str | None, netmask_dotted: str | None) -> int:
    if netmask_hex:
        return bin(int(netmask_hex, 16)).count("1")
    if netmask_dotted:
        return ipaddress.ip_network(f"0.0.0.0/{netmask_dotted}", strict=False).prefixlen
    return 24


def _interface_from_ipv4_address(
    address: ipaddress.IPv4Address,
    *,
    prefix: int,
    broadcast: ipaddress.IPv4Address | None = None,
    seen: set[str],
) -> IPv4Interface | None:
    if address.is_loopback or address.is_link_local:
        return None
    network = ipaddress.ip_network(f"{address}/{prefix}", strict=False)
    if broadcast is None:
        broadcast_addr = network.broadcast_address
    else:
        broadcast_addr = broadcast
    if not isinstance(broadcast_addr, ipaddress.IPv4Address):
        return None
    key = f"{address}/{network.prefixlen}"
    if key in seen:
        return None
    seen.add(key)
    return IPv4Interface(
        address=address,
        network=network,
        broadcast=broadcast_addr,
    )


def _parse_ipv4_interfaces_from_ifconfig_output(output: str) -> list[IPv4Interface]:
    interfaces: list[IPv4Interface] = []
    seen: set[str] = set()
    for line in output.splitlines():
        match = _IFCONFIG_INET_PATTERN.match(line)
        if match is None:
            continue
        try:
            address = ipaddress.ip_address(match.group(1))
        except ValueError:
            continue
        if not isinstance(address, ipaddress.IPv4Address):
            continue
        prefix = _netmask_to_prefix(match.group(2), match.group(3))
        broadcast = None
        if match.group(4):
            try:
                broadcast = ipaddress.ip_address(match.group(4))
            except ValueError:
                broadcast = None
            if not isinstance(broadcast, ipaddress.IPv4Address):
                broadcast = None
        interface = _interface_from_ipv4_address(
            address,
            prefix=prefix,
            broadcast=broadcast,
            seen=seen,
        )
        if interface is not None:
            interfaces.append(interface)
    return interfaces


def _ipv4_interfaces_from_ip_command() -> list[IPv4Interface]:
    try:
        result = subprocess.run(
            ["ip", "-4", "-o", "addr", "show"],
            capture_output=True,
            check=False,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0:
        return []
    return _parse_ipv4_interfaces_from_ip_output(result.stdout)


def _ipv4_interfaces_from_ifconfig() -> list[IPv4Interface]:
    try:
        result = subprocess.run(
            ["ifconfig"],
            capture_output=True,
            check=False,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0:
        return []
    return _parse_ipv4_interfaces_from_ifconfig_output(result.stdout)


def _ipv4_interfaces_from_hostname_i() -> list[IPv4Interface]:
    if platform.system() != "Linux":
        return []
    try:
        result = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            check=False,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0:
        return []

    interfaces: list[IPv4Interface] = []
    seen: set[str] = set()
    for token in result.stdout.split():
        try:
            address = ipaddress.ip_address(token.strip())
        except ValueError:
            continue
        if not isinstance(address, ipaddress.IPv4Address):
            continue
        interface = _interface_from_ipv4_address(address, prefix=24, seen=seen)
        if interface is not None:
            interfaces.append(interface)
    return interfaces


def _ipv4_interfaces_from_hostname() -> list[IPv4Interface]:
    interfaces: list[IPv4Interface] = []
    seen: set[str] = set()
    try:
        host_ips = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        host_ips = []

    for host_ip in host_ips:
        try:
            address = ipaddress.ip_address(host_ip)
        except ValueError:
            continue
        if not isinstance(address, ipaddress.IPv4Address):
            continue
        interface = _interface_from_ipv4_address(address, prefix=24, seen=seen)
        if interface is not None:
            interfaces.append(interface)
    return interfaces


def ipv4_interfaces() -> list[IPv4Interface]:
    for loader in (
        _ipv4_interfaces_from_ip_command,
        _ipv4_interfaces_from_ifconfig,
        _ipv4_interfaces_from_hostname_i,
        _ipv4_interfaces_from_hostname,
    ):
        interfaces = loader()
        if interfaces:
            return interfaces

    LOGGER.warning(
        "no local IPv4 interfaces detected, falling back to 192.168.1.0/24 for desk discovery"
    )
    return [
        IPv4Interface(
            address=ipaddress.ip_address("192.168.1.1"),
            network=ipaddress.ip_network("192.168.1.0/24", strict=False),
            broadcast=ipaddress.ip_address("192.168.1.255"),
        )
    ]


def scan_network_for_interface(interface: IPv4Interface) -> ipaddress.IPv4Network:
    if interface.network.prefixlen >= MIN_SCAN_PREFIX_LEN:
        return interface.network
    return ipaddress.ip_network(f"{interface.address}/24", strict=False)


def discovery_scan_networks() -> list[ipaddress.IPv4Network]:
    networks: list[ipaddress.IPv4Network] = []
    seen: set[str] = set()
    for interface in ipv4_interfaces():
        network = scan_network_for_interface(interface)
        key = str(network)
        if key in seen:
            continue
        seen.add(key)
        networks.append(network)
    return networks


def local_ipv4_networks() -> list[ipaddress.IPv4Network]:
    return discovery_scan_networks()


def wing_broadcast_targets() -> list[tuple[str, int]]:
    targets = {
        (str(interface.broadcast), WING_DISCOVERY_PORT)
        for interface in ipv4_interfaces()
    }
    targets.add(("255.255.255.255", WING_DISCOVERY_PORT))
    return sorted(targets)


def wing_unicast_probe_hosts() -> list[str]:
    hosts: list[str] = []
    seen: set[str] = set()
    local_addresses = {str(interface.address) for interface in ipv4_interfaces()}
    for interface in ipv4_interfaces():
        network = scan_network_for_interface(interface)
        for host in network.hosts():
            host_ip = str(host)
            if host_ip in local_addresses or host_ip in seen:
                continue
            seen.add(host_ip)
            hosts.append(host_ip)
    return hosts


def x32_broadcast_targets() -> list[tuple[str, int]]:
    targets = {
        (str(interface.broadcast), X32_OSC_PORT) for interface in ipv4_interfaces()
    }
    targets.add(("255.255.255.255", X32_OSC_PORT))
    return sorted(targets)


def x32_probe_hosts() -> list[str]:
    hosts: list[str] = []
    seen: set[str] = set()
    local_addresses = {str(interface.address) for interface in ipv4_interfaces()}
    for network in discovery_scan_networks():
        for host in network.hosts():
            host_ip = str(host)
            if host_ip in local_addresses or host_ip in seen:
                continue
            seen.add(host_ip)
            hosts.append(host_ip)
    return hosts


async def discover_wing(timeout: float = 3.0) -> list[DiscoveredDesk]:
    loop = asyncio.get_running_loop()
    found: dict[str, DiscoveredDesk] = {}
    transport: asyncio.DatagramTransport | None = None

    class _WingDiscoveryProtocol(asyncio.DatagramProtocol):
        def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
            desk = parse_wing_discovery_response(data, source_ip=addr[0])
            if desk is None:
                LOGGER.debug(
                    "ignored Wing discovery response from %s:%s (%r)",
                    addr[0],
                    addr[1],
                    data[:64],
                )
                return
            found[desk.ip] = desk

    try:
        transport, _protocol = await loop.create_datagram_endpoint(
            _WingDiscoveryProtocol,
            local_addr=("0.0.0.0", 0),
            allow_broadcast=True,
        )
        for target in wing_broadcast_targets():
            transport.sendto(WING_DISCOVERY_MESSAGE, target)

        hosts = wing_unicast_probe_hosts()
        semaphore = asyncio.Semaphore(WING_UNICAST_CONCURRENCY)

        async def probe(host: str) -> None:
            async with semaphore:
                transport.sendto(WING_DISCOVERY_MESSAGE, (host, WING_DISCOVERY_PORT))

        if hosts:
            await asyncio.gather(*(probe(host) for host in hosts))

        await asyncio.sleep(timeout)
    finally:
        if transport is not None:
            transport.close()

    return sorted(found.values(), key=lambda desk: desk.ip)


async def discover_x32(timeout: float = 3.0) -> list[DiscoveredDesk]:
    loop = asyncio.get_running_loop()
    found: dict[str, DiscoveredDesk] = {}
    transport: asyncio.DatagramTransport | None = None
    info_payload = encode_message("/info", [])
    xinfo_payload = encode_message("/xinfo", [])

    class _X32DiscoveryProtocol(asyncio.DatagramProtocol):
        def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
            desk = parse_x32_info_response(data, addr[0])
            if desk is not None:
                found[desk.ip] = desk

    try:
        transport, _protocol = await loop.create_datagram_endpoint(
            _X32DiscoveryProtocol,
            local_addr=("0.0.0.0", 0),
            allow_broadcast=True,
        )
        hosts = x32_probe_hosts()
        LOGGER.info(
            "scanning %s X32 host(s) on %s",
            len(hosts),
            ", ".join(str(network) for network in discovery_scan_networks()) or "unknown network",
        )
        semaphore = asyncio.Semaphore(X32_SCAN_CONCURRENCY)

        async def probe(target: tuple[str, int]) -> None:
            async with semaphore:
                transport.sendto(info_payload, target)
                transport.sendto(xinfo_payload, target)

        targets = [target for target in x32_broadcast_targets()]
        targets.extend((host, X32_OSC_PORT) for host in hosts)
        await asyncio.gather(*(probe(target) for target in targets))
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
