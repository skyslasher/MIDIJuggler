"""Stable device identity helpers."""

from __future__ import annotations

import re
import secrets
from typing import Any

_UID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def generate_device_uid(adapter: str) -> str:
    """Create a stable internal device identifier."""

    base = re.sub(r"[^a-zA-Z0-9_]+", "_", adapter.strip().lower()).strip("_")
    if not base:
        base = "device"
    return f"{base}_{secrets.token_hex(4)}"


generate_instance_uid = generate_device_uid


def validate_device_uid(uid: str, *, field_name: str = "device.uid") -> str:
    value = uid.strip()
    if not value:
        raise ValueError(f"{field_name} is required")
    if ":" in value or any(character.isspace() for character in value):
        raise ValueError(f"{field_name} cannot contain ':' or whitespace")
    if not _UID_PATTERN.match(value):
        raise ValueError(f"{field_name} must use letters, numbers, '.', '_' or '-'")
    return value


def validate_device_name(name: str, *, field_name: str = "device.name") -> str:
    value = name.strip()
    if not value:
        raise ValueError(f"{field_name} is required")
    if ":" in value:
        raise ValueError(f"{field_name} cannot contain ':'")
    return value


def device_display_name(uid: str, name: str = "") -> str:
    return name.strip() or uid


def parse_device_identity(raw: dict[str, Any], *, field_name: str = "device") -> tuple[str, str]:
    uid = str(raw.get("uid", "")).strip()
    legacy_id = str(raw.get("id", "")).strip()
    if not uid:
        uid = legacy_id
    uid = validate_device_uid(uid, field_name=f"{field_name}.uid")

    display_name = str(raw.get("name", "")).strip()
    if not display_name:
        display_name = str(raw.get("label", "")).strip()
    if not display_name:
        display_name = legacy_id or uid
    display_name = validate_device_name(display_name, field_name=f"{field_name}.name")
    return uid, display_name


def resolve_adapter_instance_identity(
    raw: dict[str, Any],
    *,
    field_name: str = "adapter instance",
) -> tuple[str, str]:
    uid = str(raw.get("uid", "")).strip()
    name = str(raw.get("name", "")).strip()
    previous_name = str(raw.get("previous_name", "")).strip()
    if not uid:
        uid = previous_name or name
    uid = validate_device_uid(uid, field_name=f"{field_name} uid")
    if not name:
        name = uid
    name = validate_device_name(name, field_name=f"{field_name} name")
    return uid, name


def resolve_adapter_uid(adapter_ref: str, adapters: dict[str, Any]) -> str | None:
    ref = adapter_ref.strip()
    if not ref:
        return None
    if ref in adapters:
        return ref
    for uid, adapter in adapters.items():
        display = getattr(adapter, "name", "") or ""
        if ref == display or ref == device_display_name(uid, display):
            return uid
    return None
