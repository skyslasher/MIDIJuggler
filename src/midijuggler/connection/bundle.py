"""Export and import connection bundles for a 1:1 device pair."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from midijuggler.config import AppConfig, AdapterConfig
from midijuggler.datapoint.disconnected import is_reserved_connection_module
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    ConnectionSpec,
    DataPointDirection,
    DataPointSpec,
    ModifierKind,
    SCALE_CURVES,
)
from midijuggler.device.points import _resolved_kind, library_point_ids
from midijuggler.device.types import CustomPointSpec, DeviceConfig
from midijuggler.learn import make_mapping_id, upsert_connection

BUNDLE_FORMAT = "midijuggler_connection_bundle"
BUNDLE_VERSION = 1
DEVICE_A = "device_a"
DEVICE_B = "device_b"
DEVICE_ROLES = (DEVICE_A, DEVICE_B)


def export_device_type(device: DeviceConfig, adapter: AdapterConfig) -> dict[str, str]:
    library_kind = device.library_kind or _resolved_kind(device, adapter)
    payload: dict[str, str] = {
        "library_kind": library_kind,
    }
    if device.library:
        payload["library"] = device.library
    if device.label:
        payload["label"] = device.label
    elif device.name:
        payload["label"] = device.name
    return payload


def device_types_compatible(
    exported_type: dict[str, Any],
    device: DeviceConfig,
    adapter: AdapterConfig,
) -> bool:
    local_type = export_device_type(device, adapter)
    exported_library = str(exported_type.get("library", "")).strip()
    local_library = str(local_type.get("library", "")).strip()
    if exported_library and local_library:
        return exported_library == local_library
    return str(exported_type.get("library_kind", "")).strip() == str(
        local_type.get("library_kind", "")
    ).strip()


def compatible_devices(
    config: AppConfig,
    exported_type: dict[str, Any],
) -> list[DeviceConfig]:
    matches: list[DeviceConfig] = []
    for device in config.devices.values():
        adapter = config.adapters.get(device.adapter)
        if adapter is None:
            continue
        if device_types_compatible(exported_type, device, adapter):
            matches.append(device)
    return sorted(matches, key=lambda item: item.display_name().casefold())


def export_connection_bundle(
    connections: list[ConnectionSpec],
    device_a_uid: str,
    device_b_uid: str,
    devices: dict[str, DeviceConfig],
    adapters: dict[str, AdapterConfig],
    *,
    datapoint_store: DataPointStore | None = None,
) -> dict[str, Any]:
    device_a = _require_device(devices, device_a_uid, "device_a")
    device_b = _require_device(devices, device_b_uid, "device_b")
    if device_a_uid == device_b_uid:
        raise ValueError("device_a and device_b must be different devices")

    adapter_a = _require_adapter(adapters, device_a, "device_a")
    adapter_b = _require_adapter(adapters, device_b, "device_b")

    exported_connections: list[dict[str, Any]] = []
    referenced_points: dict[str, set[str]] = {DEVICE_A: set(), DEVICE_B: set()}

    for connection in connections:
        exported = _export_connection_for_pair(
            connection,
            device_a_uid,
            device_b_uid,
        )
        if exported is None:
            continue
        exported_connections.append(exported)
        referenced_points[exported["source_device"]].add(exported["source_point"])
        referenced_points[exported["target_device"]].add(exported["target_point"])

    custom_points = {
        DEVICE_A: _collect_extra_points(
            device_a,
            adapter_a,
            referenced_points[DEVICE_A],
            datapoint_store,
        ),
        DEVICE_B: _collect_extra_points(
            device_b,
            adapter_b,
            referenced_points[DEVICE_B],
            datapoint_store,
        ),
    }

    return {
        "format": BUNDLE_FORMAT,
        "version": BUNDLE_VERSION,
        "devices": {
            DEVICE_A: export_device_type(device_a, adapter_a),
            DEVICE_B: export_device_type(device_b, adapter_b),
        },
        "device_pair": [DEVICE_A, DEVICE_B],
        "exported_from": {
            DEVICE_A: device_a_uid,
            DEVICE_B: device_b_uid,
        },
        "connections": exported_connections,
        "custom_points": custom_points,
    }


def preview_connection_bundle_import(
    bundle: dict[str, Any],
    config: AppConfig,
) -> dict[str, Any]:
    validated = validate_bundle(bundle)
    devices: dict[str, Any] = {}
    for role in DEVICE_ROLES:
        type_info = validated["devices"][role]
        candidates = compatible_devices(config, type_info)
        devices[role] = {
            "type": type_info,
            "candidates": [device.as_dict() for device in candidates],
        }
    return {
        "connection_count": len(validated["connections"]),
        "devices": devices,
    }


def apply_connection_bundle_import(
    bundle: dict[str, Any],
    device_mapping: dict[str, str],
    config: AppConfig,
    connections: list[ConnectionSpec],
    *,
    datapoint_store: DataPointStore | None = None,
) -> tuple[list[ConnectionSpec], dict[str, DeviceConfig], list[ConnectionSpec]]:
    validated = validate_bundle(bundle)
    uid_by_role = _resolve_device_mapping(validated, device_mapping, config)

    devices = dict(config.devices)
    updated_devices: dict[str, DeviceConfig] = {}
    for role in DEVICE_ROLES:
        device = devices[uid_by_role[role]]
        adapter = _require_adapter(config.adapters, device, role)
        extra_points = [
            _import_custom_point(index, raw)
            for index, raw in enumerate(
                validated.get("custom_points", {}).get(role, []),
                start=1,
            )
        ]
        merged = _merge_custom_points(device, extra_points)
        if merged is not device:
            updated_devices[merged.uid] = merged
            devices[merged.uid] = merged

    existing_ids = {connection.id for connection in connections}
    imported: list[ConnectionSpec] = []
    merged_connections = list(connections)
    for raw in validated["connections"]:
        connection = _import_connection_spec(raw, uid_by_role, existing_ids)
        existing_ids.add(connection.id)
        imported.append(connection)
        merged_connections = upsert_connection(merged_connections, connection)

    return imported, updated_devices, merged_connections


def validate_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(bundle, dict):
        raise ValueError("connection bundle must be an object")
    if bundle.get("format") != BUNDLE_FORMAT:
        raise ValueError(f"unsupported bundle format: {bundle.get('format')!r}")
    if int(bundle.get("version", 0)) != BUNDLE_VERSION:
        raise ValueError(f"unsupported bundle version: {bundle.get('version')!r}")

    devices = bundle.get("devices")
    if not isinstance(devices, dict):
        raise ValueError("bundle.devices must be an object")
    for role in DEVICE_ROLES:
        type_info = devices.get(role)
        if not isinstance(type_info, dict):
            raise ValueError(f"bundle.devices.{role} must be an object")

    raw_connections = bundle.get("connections")
    if not isinstance(raw_connections, list):
        raise ValueError("bundle.connections must be a list")

    custom_points = bundle.get("custom_points", {})
    if custom_points is not None and not isinstance(custom_points, dict):
        raise ValueError("bundle.custom_points must be an object")

    return bundle


def _require_device(
    devices: dict[str, DeviceConfig],
    uid: str,
    label: str,
) -> DeviceConfig:
    device = devices.get(uid)
    if device is None:
        raise ValueError(f"unknown {label}: {uid!r}")
    return device


def _require_adapter(
    adapters: dict[str, AdapterConfig],
    device: DeviceConfig,
    label: str,
) -> AdapterConfig:
    adapter = adapters.get(device.adapter)
    if adapter is None:
        raise ValueError(f"{label} adapter {device.adapter!r} is not configured")
    return adapter


def _export_connection_for_pair(
    connection: ConnectionSpec,
    device_a_uid: str,
    device_b_uid: str,
) -> dict[str, Any] | None:
    source_role, source_point = _endpoint_role_and_point(
        connection.source,
        device_a_uid,
        device_b_uid,
    )
    target_role, target_point = _endpoint_role_and_point(
        connection.target,
        device_a_uid,
        device_b_uid,
    )
    if source_role is None or target_role is None:
        return None
    if source_role == target_role:
        return None

    payload = connection.as_dict()
    payload.pop("source", None)
    payload.pop("target", None)
    payload["source_device"] = source_role
    payload["source_point"] = source_point
    payload["target_device"] = target_role
    payload["target_point"] = target_point
    return payload


def _endpoint_role_and_point(
    endpoint: str,
    device_a_uid: str,
    device_b_uid: str,
) -> tuple[str | None, str]:
    module, separator, point = endpoint.partition(".")
    if not separator or not point or is_reserved_connection_module(module):
        return None, ""
    if module == device_a_uid:
        return DEVICE_A, point
    if module == device_b_uid:
        return DEVICE_B, point
    return None, ""


def _collect_extra_points(
    device: DeviceConfig,
    adapter: AdapterConfig,
    referenced_points: set[str],
    datapoint_store: DataPointStore | None,
) -> list[dict[str, Any]]:
    if not referenced_points:
        return []

    library_ids = library_point_ids(device, adapter)
    custom_by_id = {point.id: point for point in device.custom_points}
    exported: list[dict[str, Any]] = []
    seen: set[str] = set()

    for point_id in sorted(referenced_points):
        if point_id in library_ids or point_id in seen:
            continue
        if point_id in custom_by_id:
            exported.append(custom_by_id[point_id].as_dict())
            seen.add(point_id)
            continue
        if datapoint_store is None:
            continue
        spec = datapoint_store.spec(f"{device.uid}.{point_id}")
        if spec is None:
            continue
        exported.append(_datapoint_spec_to_custom_export(spec))
        seen.add(point_id)
    return exported


def _datapoint_spec_to_custom_export(spec: DataPointSpec) -> dict[str, Any]:
    direction = {
        DataPointDirection.INPUT: "input",
        DataPointDirection.OUTPUT: "output",
        DataPointDirection.BIDIRECTIONAL: "bidirectional",
    }.get(spec.direction, "bidirectional")
    payload: dict[str, Any] = {
        "id": spec.id.point,
        "value_type": spec.value_type.value,
        "direction": direction,
    }
    if spec.label:
        payload["label"] = spec.label
    if spec.value_min is not None and spec.value_min != 0.0:
        payload["value_min"] = spec.value_min
    if spec.value_max is not None and spec.value_max != 127.0:
        payload["value_max"] = spec.value_max
    if spec.protocol:
        payload["protocol"] = spec.protocol
    if spec.input_mode:
        payload["input_mode"] = spec.input_mode
    if spec.relative_encoding:
        payload["relative_encoding"] = spec.relative_encoding
    return payload


def _import_custom_point(index: int, raw: Any) -> CustomPointSpec:
    if not isinstance(raw, dict):
        raise ValueError(f"custom_points[{index}] must be an object")
    point_id = str(raw.get("id", "")).strip()
    if not point_id:
        raise ValueError(f"custom_points[{index}].id is required")
    return CustomPointSpec(
        id=point_id,
        value_type=str(raw.get("value_type", "float")),
        direction=str(raw.get("direction", "bidirectional")),
        label=str(raw.get("label", "")),
        value_min=float(raw.get("value_min", 0.0)),
        value_max=float(raw.get("value_max", 127.0)),
        protocol=str(raw.get("protocol", "")),
        input_mode=str(raw.get("input_mode", "")),
        relative_encoding=str(raw.get("relative_encoding", "")),
    )


def _merge_custom_points(
    device: DeviceConfig,
    new_points: list[CustomPointSpec],
) -> DeviceConfig:
    if not new_points:
        return device
    existing_ids = {point.id for point in device.custom_points}
    merged = list(device.custom_points)
    changed = False
    for point in new_points:
        if point.id in existing_ids:
            continue
        merged.append(point)
        existing_ids.add(point.id)
        changed = True
    if not changed:
        return device
    return replace(device, custom_points=tuple(merged))


def _resolve_device_mapping(
    bundle: dict[str, Any],
    device_mapping: dict[str, str],
    config: AppConfig,
) -> dict[str, str]:
    if not isinstance(device_mapping, dict):
        raise ValueError("device_mapping must be an object")

    uid_by_role: dict[str, str] = {}
    for role in DEVICE_ROLES:
        mapped_uid = str(device_mapping.get(role, "")).strip()
        if not mapped_uid:
            raise ValueError(f"device mapping for {role} is required")
        device = config.devices.get(mapped_uid)
        if device is None:
            raise ValueError(f"unknown device {mapped_uid!r} for {role}")
        adapter = config.adapters.get(device.adapter)
        if adapter is None:
            raise ValueError(f"adapter for device {mapped_uid!r} is not configured")
        exported_type = bundle["devices"][role]
        if not device_types_compatible(exported_type, device, adapter):
            raise ValueError(
                f"device {device.display_name()!r} is not compatible with exported {role} type"
            )
        uid_by_role[role] = mapped_uid
    return uid_by_role


def _import_connection_spec(
    raw: dict[str, Any],
    uid_by_role: dict[str, str],
    existing_ids: set[str],
) -> ConnectionSpec:
    source_role = str(raw.get("source_device", "")).strip()
    target_role = str(raw.get("target_device", "")).strip()
    source_point = str(raw.get("source_point", "")).strip()
    target_point = str(raw.get("target_point", "")).strip()
    if source_role not in uid_by_role or target_role not in uid_by_role:
        raise ValueError("connection uses unknown device role")
    if not source_point or not target_point:
        raise ValueError("connection source_point and target_point are required")

    source = f"{uid_by_role[source_role]}.{source_point}"
    target = f"{uid_by_role[target_role]}.{target_point}"

    modifier_raw = str(raw.get("modifier", ModifierKind.RANGE_MAP.value)).strip()
    try:
        modifier = ModifierKind(modifier_raw)
    except ValueError as exc:
        raise ValueError(f"unsupported modifier: {modifier_raw!r}") from exc

    scale_curve = str(raw.get("scale_curve", "linear")).strip() or "linear"
    if scale_curve not in SCALE_CURVES:
        raise ValueError(f"unsupported scale_curve: {scale_curve!r}")

    factor = float(raw.get("factor", 1.0))
    if modifier == ModifierKind.FACTOR and factor == 0.0:
        raise ValueError("factor must not be zero")

    connection_id = str(raw.get("id", "")).strip() or make_mapping_id(source, target)
    if connection_id in existing_ids:
        connection_id = make_mapping_id(source, target)

    return ConnectionSpec(
        id=connection_id,
        source=source,
        target=target,
        modifier=modifier,
        input_min=float(raw.get("input_min", 0.0)),
        input_max=float(raw.get("input_max", 1.0)),
        output_min=float(raw.get("output_min", 0.0)),
        output_max=float(raw.get("output_max", 127.0)),
        invert=bool(raw.get("invert", False)),
        scale_curve=scale_curve,
        factor=factor,
        enabled=bool(raw.get("enabled", True)),
    )
