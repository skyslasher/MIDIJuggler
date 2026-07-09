"""mDNS hostname helpers for rotary display devices."""

from __future__ import annotations

import re

_MDNS_HOSTNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


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
