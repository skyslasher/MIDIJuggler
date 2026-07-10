"""mDNS hostname helpers for rotary display devices."""

from __future__ import annotations

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
