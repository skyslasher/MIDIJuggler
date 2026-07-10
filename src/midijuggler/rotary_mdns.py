"""mDNS hostname helpers for rotary display devices."""

from __future__ import annotations

import contextlib
import ipaddress
import logging
import re
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any

LOGGER = logging.getLogger(__name__)

_MDNS_HOSTNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_MDNS_CACHE_TTL_S = 30.0
_MDNS_RESOLVE_TIMEOUT_MS = 3000
ROTARY_MDNS_SERVICE_TYPE = "_midijuggler-rotary._udp.local."
_AVAHI_ROTARY_SERVICE_TYPE = "_midijuggler-rotary._udp"
_BROWSE_CANDIDATES = ("avahi-browse", "/usr/bin/avahi-browse")


@dataclass(frozen=True)
class RotaryMdnsService:
    """A rotary display advertised via mDNS."""

    hostname: str
    port: int


def zeroconf_available() -> bool:
    try:
        import zeroconf  # noqa: F401
    except ImportError:
        return False
    return True


def normalize_mdns_hostname(value: str) -> str:
    """Normalize a rotary display mDNS hostname without the .local suffix."""

    hostname = str(value or "").strip().lower()
    if hostname.endswith(".local"):
        hostname = hostname[:-6]
    if not hostname:
        return ""
    if not _MDNS_HOSTNAME_RE.match(hostname):
        raise ValueError(
            "mdns_hostname must use lowercase letters, digits, and hyphens "
            "(1-63 characters, no leading/trailing hyphen)"
        )
    return hostname


def format_mdns_hostname(value: str) -> str:
    hostname = normalize_mdns_hostname(value)
    if not hostname:
        return ""
    return f"{hostname}.local"


def is_mdns_hostname(host: str) -> bool:
    return str(host or "").strip().lower().endswith(".local")


def is_ipv4_address(host: str) -> bool:
    try:
        ipaddress.IPv4Address(str(host or "").strip())
    except ValueError:
        return False
    return True


def mdns_fqdn(host: str) -> str:
    """Return an mDNS hostname with a trailing dot for DNS queries."""

    name = str(host or "").strip().lower()
    if not name.endswith(".local"):
        raise ValueError(f"not an mDNS hostname: {host!r}")
    if not name.endswith("."):
        name += "."
    return name


@dataclass(frozen=True)
class _MdnsCacheEntry:
    ip: str
    expires_at: float


_cache: dict[str, _MdnsCacheEntry] = {}
_cache_lock = threading.Lock()
_zeroconf: Any | None = None
_zeroconf_lock = threading.Lock()


def _cache_key(host: str) -> str:
    return str(host or "").strip().lower()


def invalidate_mdns_cache(host: str) -> None:
    key = _cache_key(host)
    with _cache_lock:
        _cache.pop(key, None)


def _get_cached_ip(host: str) -> str | None:
    key = _cache_key(host)
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None or entry.expires_at <= now:
            if entry is not None:
                _cache.pop(key, None)
            return None
        return entry.ip


def _store_cached_ip(host: str, ip: str) -> None:
    key = _cache_key(host)
    with _cache_lock:
        _cache[key] = _MdnsCacheEntry(
            ip=ip,
            expires_at=time.monotonic() + _MDNS_CACHE_TTL_S,
        )


def _get_zeroconf() -> Any:
    global _zeroconf
    with _zeroconf_lock:
        if _zeroconf is None:
            from zeroconf import Zeroconf

            try:
                _zeroconf = Zeroconf()
            except OSError as exc:
                raise OSError(f"failed to open mDNS socket: {exc}") from exc
        return _zeroconf


def _resolve_mdns_via_avahi(host: str) -> str | None:
    """Resolve a .local hostname using avahi-resolve-host-name when available."""

    avahi = shutil.which("avahi-resolve-host-name")
    if avahi is None:
        return None

    try:
        result = subprocess.run(
            [avahi, "-4", host],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        LOGGER.debug("avahi-resolve failed for %s: %s", host, exc)
        return None

    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and is_ipv4_address(parts[1]):
            return str(parts[1]).strip()
    return None


def resolve_mdns_ipv4(host: str, *, force: bool = False) -> str | None:
    """Resolve a .local hostname to an IPv4 address via mDNS."""

    target = str(host or "").strip()
    if not is_mdns_hostname(target):
        return None

    if not force:
        cached = _get_cached_ip(target)
        if cached is not None:
            return cached

    if zeroconf_available():
        try:
            from zeroconf import AddressResolverIPv4
        except ImportError:
            LOGGER.warning(
                "python-zeroconf AddressResolverIPv4 is unavailable; cannot resolve %s",
                target,
            )
        else:
            resolver = AddressResolverIPv4(mdns_fqdn(target))
            try:
                zeroconf = _get_zeroconf()
                resolved = resolver.request(
                    zeroconf,
                    timeout=_MDNS_RESOLVE_TIMEOUT_MS,
                )
            except OSError as exc:
                LOGGER.warning("mDNS lookup failed for %s: %s", target, exc)
                resolved = False

            if resolved:
                addresses = resolver.parsed_addresses()
                for address in addresses:
                    if is_ipv4_address(address):
                        ip = str(address).strip()
                        _store_cached_ip(target, ip)
                        return ip
    else:
        LOGGER.debug(
            "python-zeroconf is not installed; trying avahi-resolve for %s",
            target,
        )

    ip = _resolve_mdns_via_avahi(target)
    if ip is not None:
        _store_cached_ip(target, ip)
        return ip

    LOGGER.warning(
        "could not resolve rotary display feedback target %s via mDNS "
        "(install python-zeroconf with pip install midijuggler[rotary] or avahi-utils)",
        target,
    )
    return None


def resolve_udp_host(
    host: str,
    *,
    fallback_ip: str | None = None,
    force: bool = False,
) -> str:
    """Resolve a UDP destination host to an IPv4 address."""

    target = str(host or "").strip()
    if not target:
        raise OSError("empty UDP host")

    if is_ipv4_address(target):
        return target

    if is_mdns_hostname(target):
        ip = resolve_mdns_ipv4(target, force=force)
        if ip is not None:
            return ip
        if fallback_ip and is_ipv4_address(fallback_ip):
            return str(fallback_ip).strip()
        raise OSError(f"mDNS resolution failed for {target}")

    try:
        addresses = socket.getaddrinfo(
            target,
            None,
            family=socket.AF_INET,
            type=socket.SOCK_DGRAM,
        )
    except OSError as exc:
        if fallback_ip and is_ipv4_address(fallback_ip):
            return str(fallback_ip).strip()
        raise OSError(f"DNS resolution failed for {target}: {exc}") from exc

    if not addresses:
        if fallback_ip and is_ipv4_address(fallback_ip):
            return str(fallback_ip).strip()
        raise OSError(f"DNS resolution failed for {target}")

    return str(addresses[0][4][0])


def _format_rotary_mdns_hostname(server: str) -> str:
    hostname = str(server or "").strip().rstrip(".")
    if not hostname:
        return ""
    if hostname.endswith(".local"):
        return hostname
    return f"{hostname}.local"


def parse_avahi_rotary_browse_line(line: str) -> RotaryMdnsService | None:
    """Parse one `avahi-browse -rpt` line for a rotary display service."""

    if not line.startswith("="):
        return None

    parts = line.split(";")
    if len(parts) < 10:
        return None

    service_type = parts[4].strip()
    if service_type != _AVAHI_ROTARY_SERVICE_TYPE:
        return None

    hostname = _format_rotary_mdns_hostname(parts[6].strip())
    if not hostname:
        return None

    try:
        port = int(parts[8].strip())
    except ValueError:
        return None
    if port <= 0 or port > 65535:
        return None

    return RotaryMdnsService(hostname=hostname, port=port)


def _browse_rotary_via_avahi(*, timeout_s: float) -> list[RotaryMdnsService]:
    browse_path = None
    for candidate in _BROWSE_CANDIDATES:
        if candidate.startswith("/"):
            path = candidate
        else:
            path = shutil.which(candidate)
        if path:
            browse_path = path
            break
    if browse_path is None:
        return []

    try:
        result = subprocess.run(
            [browse_path, "-r", "-p", "-t", _AVAHI_ROTARY_SERVICE_TYPE],
            capture_output=True,
            text=True,
            timeout=max(timeout_s, 1.0),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        LOGGER.debug("avahi-browse failed for rotary display services: %s", exc)
        return []

    services: dict[tuple[str, int], RotaryMdnsService] = {}
    for line in result.stdout.splitlines():
        parsed = parse_avahi_rotary_browse_line(line.strip())
        if parsed is None:
            continue
        services[(parsed.hostname, parsed.port)] = parsed
    return list(services.values())


class _RotaryServiceListener:
    def __init__(self) -> None:
        self._services: dict[tuple[str, int], RotaryMdnsService] = {}
        self._lock = threading.Lock()

    def add_service(self, zc: Any, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name, timeout=2000)
        if info is None:
            return
        server = info.server
        if isinstance(server, bytes):
            server = server.decode("utf-8", errors="ignore")
        hostname = _format_rotary_mdns_hostname(str(server))
        if not hostname:
            return
        service = RotaryMdnsService(hostname=hostname, port=int(info.port))
        with self._lock:
            self._services[(service.hostname, service.port)] = service

    def remove_service(self, zc: Any, type_: str, name: str) -> None:
        return

    def update_service(self, zc: Any, type_: str, name: str) -> None:
        self.add_service(zc, type_, name)

    def services(self) -> list[RotaryMdnsService]:
        with self._lock:
            return list(self._services.values())


def _browse_rotary_via_zeroconf(*, timeout_s: float) -> list[RotaryMdnsService]:
    from zeroconf import ServiceBrowser

    listener = _RotaryServiceListener()
    zeroconf = _get_zeroconf()
    browser = ServiceBrowser(zeroconf, ROTARY_MDNS_SERVICE_TYPE, listener)
    try:
        time.sleep(max(timeout_s, 0.5))
    finally:
        with contextlib.suppress(Exception):
            browser.cancel()
    return listener.services()


def browse_rotary_feedback_targets(*, timeout_s: float = 4.0) -> list[RotaryMdnsService]:
    """Discover rotary display feedback endpoints advertised on the LAN."""

    if zeroconf_available():
        try:
            services = _browse_rotary_via_zeroconf(timeout_s=timeout_s)
        except OSError as exc:
            LOGGER.warning("zeroconf browse failed for rotary display services: %s", exc)
            services = []
        if services:
            return sorted(services, key=lambda item: item.hostname)
    else:
        services = []

    avahi_services = _browse_rotary_via_avahi(timeout_s=timeout_s)
    if avahi_services:
        return sorted(avahi_services, key=lambda item: item.hostname)
    return services
