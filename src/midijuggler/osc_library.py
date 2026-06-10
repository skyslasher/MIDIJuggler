"""OSC mapping libraries for common devices."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
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
class OscLibrary:
    """Collection of OSC parameters for one device family."""

    id: str
    name: str
    vendor: str
    model: str
    notes: str
    parameters: tuple[OscParameter, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "vendor": self.vendor,
            "model": self.model,
            "notes": self.notes,
            "parameters": [parameter.as_dict() for parameter in self.parameters],
        }


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

    return OscLibrary(
        id=library_id,
        name=_required_str(library_raw, "name", "library.name"),
        vendor=str(library_raw.get("vendor", "")),
        model=str(library_raw.get("model", "")),
        notes=str(library_raw.get("notes", "")),
        parameters=tuple(parameters),
    )


def _expand_template(raw: dict[str, Any], field_name: str) -> list[OscParameter]:
    if not isinstance(raw, dict):
        raise ValueError(f"{field_name} must be a table")

    range_name = _required_str(raw, "range_name", f"{field_name}.range_name")
    start = _required_int(raw, "range_start", f"{field_name}.range_start")
    end = _required_int(raw, "range_end", f"{field_name}.range_end")
    if start > end:
        raise ValueError(f"{field_name}.range_start must be <= range_end")

    parameters: list[OscParameter] = []
    for value in range(start, end + 1):
        values = {range_name: value}
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
