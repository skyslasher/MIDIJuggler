"""MIDI mapping libraries for common controllers."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from itertools import product
from typing import Any
import tomllib


@dataclass(frozen=True)
class MidiParameter:
    """One MIDI control, feedback target or display target."""

    id: str
    label: str
    address: str
    message_type: str
    value_type: str
    value_min: float | None
    value_max: float | None
    category: str
    direction: str
    port: str = ""
    midi_channel: int | None = None
    number: int | None = None
    strip: int | None = None
    line: int | None = None
    text_length: int | None = None
    sysex_template: str = ""
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "address": self.address,
            "message_type": self.message_type,
            "value_type": self.value_type,
            "value_min": self.value_min,
            "value_max": self.value_max,
            "category": self.category,
            "direction": self.direction,
            "port": self.port,
            "midi_channel": self.midi_channel,
            "number": self.number,
            "strip": self.strip,
            "line": self.line,
            "text_length": self.text_length,
            "sysex_template": self.sysex_template,
            "description": self.description,
        }


@dataclass(frozen=True)
class MidiLibrary:
    """Collection of MIDI parameters for one controller family."""

    id: str
    name: str
    vendor: str
    model: str
    notes: str
    parameters: tuple[MidiParameter, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "vendor": self.vendor,
            "model": self.model,
            "notes": self.notes,
            "parameters": [parameter.as_dict() for parameter in self.parameters],
        }


def list_midi_libraries() -> list[MidiLibrary]:
    """Load all packaged MIDI mapping libraries."""

    package = resources.files("midijuggler.midi_libraries")
    libraries = [
        _load_library_file(resource.name)
        for resource in package.iterdir()
        if resource.name.endswith(".toml")
    ]
    return sorted(libraries, key=lambda library: library.id)


def get_midi_library(library_id: str) -> MidiLibrary:
    """Load one packaged MIDI mapping library by id."""

    for library in list_midi_libraries():
        if library.id == library_id:
            return library
    raise KeyError(f"unknown MIDI library: {library_id}")


def _load_library_file(filename: str) -> MidiLibrary:
    resource = resources.files("midijuggler.midi_libraries").joinpath(filename)
    raw = tomllib.loads(resource.read_text(encoding="utf-8"))
    return _parse_library(raw)


def _parse_library(raw: dict[str, Any]) -> MidiLibrary:
    library_raw = raw.get("library", {})
    parameters = [
        _parse_parameter(parameter_raw, f"parameters[{index}]")
        for index, parameter_raw in enumerate(raw.get("parameters", []), start=1)
    ]

    for index, template_raw in enumerate(raw.get("templates", []), start=1):
        parameters.extend(_expand_template(template_raw, f"templates[{index}]"))

    return MidiLibrary(
        id=_required_str(library_raw, "id", "library.id"),
        name=_required_str(library_raw, "name", "library.name"),
        vendor=str(library_raw.get("vendor", "")),
        model=str(library_raw.get("model", "")),
        notes=str(library_raw.get("notes", "")),
        parameters=tuple(parameters),
    )


def _expand_template(raw: dict[str, Any], field_name: str) -> list[MidiParameter]:
    if not isinstance(raw, dict):
        raise ValueError(f"{field_name} must be a table")

    return [
        _parse_parameter(raw, field_name, values)
        for values in _template_value_sets(raw, field_name)
    ]


def _parse_parameter(
    raw: dict[str, Any],
    field_name: str,
    values: dict[str, int] | None = None,
) -> MidiParameter:
    if not isinstance(raw, dict):
        raise ValueError(f"{field_name} must be a table")
    values = values or {}

    return MidiParameter(
        id=_required_formatted_str(raw, "id", f"{field_name}.id", values),
        label=_required_formatted_str(raw, "label", f"{field_name}.label", values),
        address=_required_formatted_str(raw, "address", f"{field_name}.address", values),
        message_type=_formatted_str(raw.get("message_type", "note"), values),
        value_type=_formatted_str(raw.get("value_type", "int"), values),
        value_min=_optional_float(raw.get("value_min"), f"{field_name}.value_min", values),
        value_max=_optional_float(raw.get("value_max"), f"{field_name}.value_max", values),
        category=_formatted_str(raw.get("category", ""), values),
        direction=_formatted_str(raw.get("direction", "source"), values),
        port=_formatted_str(raw.get("port", ""), values),
        midi_channel=_optional_int(raw.get("midi_channel"), f"{field_name}.midi_channel", values),
        number=_optional_int(raw.get("number"), f"{field_name}.number", values),
        strip=_optional_int(raw.get("strip"), f"{field_name}.strip", values),
        line=_optional_int(raw.get("line"), f"{field_name}.line", values),
        text_length=_optional_int(raw.get("text_length"), f"{field_name}.text_length", values),
        sysex_template=_formatted_str(raw.get("sysex_template", ""), values),
        description=_formatted_str(raw.get("description", ""), values),
    )


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

    value_sets = [dict(zip(names, values, strict=True)) for values in product(*value_ranges)]
    return [_with_derived_values(value_set, raw, field_name) for value_set in value_sets]


def _with_derived_values(
    values: dict[str, int],
    raw: dict[str, Any],
    field_name: str,
) -> dict[str, int]:
    derived = raw.get("derived", [])
    if not isinstance(derived, list):
        raise ValueError(f"{field_name}.derived must be a list")

    expanded = dict(values)
    for index, raw_derived in enumerate(derived, start=1):
        if not isinstance(raw_derived, dict):
            raise ValueError(f"{field_name}.derived[{index}] must be a table")
        name = _required_str(raw_derived, "name", f"{field_name}.derived[{index}].name")
        source = _required_str(
            raw_derived,
            "source",
            f"{field_name}.derived[{index}].source",
        )
        if source not in expanded:
            raise ValueError(f"{field_name}.derived[{index}].source is unknown")
        offset = int(raw_derived.get("offset", 0))
        expanded[name] = expanded[source] + offset
    return expanded


def _required_formatted_str(
    raw: dict[str, Any],
    key: str,
    field_name: str,
    values: dict[str, int],
) -> str:
    return _formatted_str(_required_str(raw, key, field_name), values)


def _formatted_str(value: Any, values: dict[str, int]) -> str:
    return str(value).format(**values)


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


def _optional_int(value: Any, field_name: str, values: dict[str, int]) -> int | None:
    if value is None:
        return None
    try:
        return int(_formatted_str(value, values))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _optional_float(value: Any, field_name: str, values: dict[str, int]) -> float | None:
    if value is None:
        return None
    try:
        return float(_formatted_str(value, values))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
