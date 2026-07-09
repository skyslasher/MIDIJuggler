"""OSC mapping libraries for common devices."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from itertools import product
from typing import Any
import tomllib


@dataclass(frozen=True)
class OscParameter:
    """One OSC parameter that can be used as a mapping source or target."""

    id: str
    label: str
    address: str
    value_type: str
    value_min: float
    value_max: float
    category: str
    direction: str
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "address": self.address,
            "value_type": self.value_type,
            "value_min": self.value_min,
            "value_max": self.value_max,
            "category": self.category,
            "direction": self.direction,
            "description": self.description,
        }


@dataclass(frozen=True)
class BundledConnection:
    """Default routing bundled with a packaged OSC library."""

    id: str
    label: str
    connection_id: str
    source: str
    target: str
    source_suffix: str
    target_suffix: str
    modifier: str
    managed_by: str
    direction: str

    def resolve(self, device_id: str) -> tuple[str, str, str]:
        resolved_id = self.connection_id.format(device_id=device_id)
        source = self.source or f"{device_id}{self.source_suffix}"
        target = self.target or f"{device_id}{self.target_suffix}"
        return resolved_id, source, target

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "connection_id": self.connection_id,
            "source": self.source,
            "target": self.target,
            "source_suffix": self.source_suffix,
            "target_suffix": self.target_suffix,
            "modifier": self.modifier,
            "managed_by": self.managed_by,
            "direction": self.direction,
        }


@dataclass(frozen=True)
class OscLibrary:
    """Collection of OSC parameters for one device family."""

    id: str
    name: str
    vendor: str
    model: str
    notes: str
    parameters: tuple[OscParameter, ...]
    bundled: bool = False
    bundled_connections: tuple[BundledConnection, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "name": self.name,
            "vendor": self.vendor,
            "model": self.model,
            "notes": self.notes,
            "bundled": self.bundled,
            "parameters": [parameter.as_dict() for parameter in self.parameters],
        }
        if self.bundled_connections:
            payload["bundled_connections"] = [
                connection.as_dict() for connection in self.bundled_connections
            ]
        return payload


def list_osc_libraries() -> list[OscLibrary]:
    """Load all packaged OSC mapping libraries."""

    package = resources.files("midijuggler.osc_libraries")
    libraries = [
        _load_library_file(resource.name)
        for resource in package.iterdir()
        if resource.name.endswith(".toml")
    ]
    return sorted(libraries, key=lambda library: library.id)


def get_osc_library(library_id: str) -> OscLibrary:
    """Load one packaged OSC mapping library by id."""

    for library in list_osc_libraries():
        if library.id == library_id:
            return library
    raise KeyError(f"unknown OSC library: {library_id}")


def _load_library_file(filename: str) -> OscLibrary:
    resource = resources.files("midijuggler.osc_libraries").joinpath(filename)
    raw = tomllib.loads(resource.read_text(encoding="utf-8"))
    return _parse_library(raw)


def _parse_library(raw: dict[str, Any]) -> OscLibrary:
    library_raw = raw.get("library", {})
    library_id = _required_str(library_raw, "id", "library.id")
    parameters = [
        _parse_parameter(parameter_raw, f"parameters[{index}]")
        for index, parameter_raw in enumerate(raw.get("parameters", []), start=1)
    ]

    for index, template_raw in enumerate(raw.get("templates", []), start=1):
        parameters.extend(_expand_template(template_raw, f"templates[{index}]"))

    bundled_connections = [
        _parse_bundled_connection(connection_raw, f"bundled_connections[{index}]")
        for index, connection_raw in enumerate(raw.get("bundled_connections", []), start=1)
    ]

    return OscLibrary(
        id=library_id,
        name=_required_str(library_raw, "name", "library.name"),
        vendor=str(library_raw.get("vendor", "")),
        model=str(library_raw.get("model", "")),
        notes=str(library_raw.get("notes", "")),
        parameters=tuple(parameters),
        bundled=bool(library_raw.get("bundled", False)),
        bundled_connections=tuple(bundled_connections),
    )


def _parse_bundled_connection(raw: dict[str, Any], field_name: str) -> BundledConnection:
    if not isinstance(raw, dict):
        raise ValueError(f"{field_name} must be a table")

    source = str(raw.get("source", "")).strip()
    target = str(raw.get("target", "")).strip()
    source_suffix = str(raw.get("source_suffix", "")).strip()
    target_suffix = str(raw.get("target_suffix", "")).strip()
    if not source and not source_suffix:
        raise ValueError(f"{field_name} requires source or source_suffix")
    if not target and not target_suffix:
        raise ValueError(f"{field_name} requires target or target_suffix")

    return BundledConnection(
        id=_required_str(raw, "id", f"{field_name}.id"),
        label=_required_str(raw, "label", f"{field_name}.label"),
        connection_id=_required_str(raw, "connection_id", f"{field_name}.connection_id"),
        source=source,
        target=target,
        source_suffix=source_suffix,
        target_suffix=target_suffix,
        modifier=str(raw.get("modifier", "passthrough")),
        managed_by=_required_str(raw, "managed_by", f"{field_name}.managed_by"),
        direction=str(raw.get("direction", "")),
    )


def _expand_template(raw: dict[str, Any], field_name: str) -> list[OscParameter]:
    if not isinstance(raw, dict):
        raise ValueError(f"{field_name} must be a table")

    parameters: list[OscParameter] = []
    for values in _template_value_sets(raw, field_name):
        parameters.append(
            OscParameter(
                id=_format_template(raw, "id", values, field_name),
                label=_format_template(raw, "label", values, field_name),
                address=_format_template(raw, "address", values, field_name),
                value_type=str(raw.get("value_type", "float")),
                value_min=_as_float(raw.get("value_min", 0.0), f"{field_name}.value_min"),
                value_max=_as_float(raw.get("value_max", 1.0), f"{field_name}.value_max"),
                category=str(raw.get("category", "")),
                direction=str(raw.get("direction", "target")),
                description=_format_template(raw, "description", values, field_name)
                if "description" in raw
                else "",
            )
        )
    return parameters


def _template_value_sets(raw: dict[str, Any], field_name: str) -> list[dict[str, int]]:
    ranges = raw.get("ranges")
    if ranges is None:
        range_name = _required_str(raw, "range_name", f"{field_name}.range_name")
        start = _required_int(raw, "range_start", f"{field_name}.range_start")
        end = _required_int(raw, "range_end", f"{field_name}.range_end")
        ranges = [{"name": range_name, "start": start, "end": end}]

    if not isinstance(ranges, list) or not ranges:
        raise ValueError(f"{field_name}.ranges must be a non-empty list")

    names: list[str] = []
    value_ranges: list[range] = []
    for index, raw_range in enumerate(ranges, start=1):
        if not isinstance(raw_range, dict):
            raise ValueError(f"{field_name}.ranges[{index}] must be a table")
        name = _required_str(raw_range, "name", f"{field_name}.ranges[{index}].name")
        start = _required_int(raw_range, "start", f"{field_name}.ranges[{index}].start")
        end = _required_int(raw_range, "end", f"{field_name}.ranges[{index}].end")
        if start > end:
            raise ValueError(f"{field_name}.ranges[{index}].start must be <= end")
        names.append(name)
        value_ranges.append(range(start, end + 1))

    if len(names) != len(set(names)):
        raise ValueError(f"{field_name}.ranges names must be unique")

    return [
        dict(zip(names, values, strict=True))
        for values in product(*value_ranges)
    ]


def _parse_parameter(raw: dict[str, Any], field_name: str) -> OscParameter:
    if not isinstance(raw, dict):
        raise ValueError(f"{field_name} must be a table")

    return OscParameter(
        id=_required_str(raw, "id", f"{field_name}.id"),
        label=_required_str(raw, "label", f"{field_name}.label"),
        address=_required_str(raw, "address", f"{field_name}.address"),
        value_type=str(raw.get("value_type", "float")),
        value_min=_as_float(raw.get("value_min", 0.0), f"{field_name}.value_min"),
        value_max=_as_float(raw.get("value_max", 1.0), f"{field_name}.value_max"),
        category=str(raw.get("category", "")),
        direction=str(raw.get("direction", "target")),
        description=str(raw.get("description", "")),
    )


def _format_template(
    raw: dict[str, Any],
    key: str,
    values: dict[str, int],
    field_name: str,
) -> str:
    template = _required_str(raw, key, f"{field_name}.{key}")
    return template.format(**values)


def _required_str(raw: dict[str, Any], key: str, field_name: str) -> str:
    value = raw.get(key)
    if value is None or value == "":
        raise ValueError(f"{field_name} is required")
    return str(value)


def _required_int(raw: dict[str, Any], key: str, field_name: str) -> int:
    if key not in raw:
        raise ValueError(f"{field_name} is required")
    try:
        return int(raw[key])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _as_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
