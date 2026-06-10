"""Configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import tomllib

from midijuggler.mapping import MappingRule


@dataclass(frozen=True)
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8080


@dataclass(frozen=True)
class AdapterConfig:
    enabled: bool = False
    options: dict[str, Any] = field(default_factory=dict)
    kind: str = ""


@dataclass(frozen=True)
class AppConfig:
    web: WebConfig = field(default_factory=WebConfig)
    adapters: dict[str, AdapterConfig] = field(default_factory=dict)
    mappings: list[MappingRule] = field(default_factory=list)


DEFAULT_ADAPTERS = ("osc", "usb_midi", "rtp_midi", "gpio")
MULTI_INSTANCE_ADAPTERS = ("osc", "usb_midi", "rtp_midi")


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    return parse_config(raw)


def parse_config(raw: dict[str, Any]) -> AppConfig:
    web_raw = raw.get("web", {})
    web = WebConfig(
        host=str(web_raw.get("host", "0.0.0.0")),
        port=_as_int(web_raw.get("port", 8080), "web.port"),
    )

    adapters = _parse_adapters(raw.get("adapters", {}))

    mappings = [
        _parse_mapping(index, mapping_raw)
        for index, mapping_raw in enumerate(raw.get("mappings", []), start=1)
    ]

    return AppConfig(web=web, adapters=adapters, mappings=mappings)


def _parse_adapters(raw: Any) -> dict[str, AdapterConfig]:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("adapters must be a table")

    adapters = {
        name: AdapterConfig(enabled=False, options={}, kind=name)
        for name in DEFAULT_ADAPTERS
    }

    for instance_name, adapter_raw in raw.items():
        adapters[instance_name] = _parse_adapter(instance_name, adapter_raw)

    return adapters


def _parse_adapter(instance_name: str, raw: Any) -> AdapterConfig:
    _validate_adapter_instance_name(instance_name)
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"adapters.{instance_name} must be a table")

    kind = str(raw.get("type") or instance_name)
    if kind not in DEFAULT_ADAPTERS:
        raise ValueError(
            f"adapters.{instance_name}.type must be one of: "
            f"{', '.join(DEFAULT_ADAPTERS)}"
        )
    if instance_name in DEFAULT_ADAPTERS and kind != instance_name:
        raise ValueError(
            f"adapters.{instance_name}.type must be {instance_name!r} "
            "for the default adapter table"
        )
    if instance_name not in DEFAULT_ADAPTERS and kind not in MULTI_INSTANCE_ADAPTERS:
        raise ValueError(
            f"adapters.{instance_name} cannot create additional {kind} instances"
        )

    options = {
        key: value
        for key, value in raw.items()
        if key not in {"enabled", "type"}
    }
    return AdapterConfig(
        enabled=bool(raw.get("enabled", False)),
        options=options,
        kind=kind,
    )


def _validate_adapter_instance_name(instance_name: str) -> None:
    if not instance_name:
        raise ValueError("adapter instance names must not be empty")
    if ":" in instance_name or any(character.isspace() for character in instance_name):
        raise ValueError(
            f"adapter instance name {instance_name!r} cannot contain ':' or whitespace"
        )


def _parse_mapping(index: int, raw: Any) -> MappingRule:
    if not isinstance(raw, dict):
        raise ValueError(f"mappings[{index}] must be a table")

    required = ("id", "source", "target")
    missing = [key for key in required if not raw.get(key)]
    if missing:
        raise ValueError(f"mappings[{index}] missing required fields: {', '.join(missing)}")

    return MappingRule(
        id=str(raw["id"]),
        source=str(raw["source"]),
        target=str(raw["target"]),
        input_min=_as_float(raw.get("input_min", 0.0), f"mappings[{index}].input_min"),
        input_max=_as_float(raw.get("input_max", 1.0), f"mappings[{index}].input_max"),
        output_min=_as_float(raw.get("output_min", 0.0), f"mappings[{index}].output_min"),
        output_max=_as_float(raw.get("output_max", 127.0), f"mappings[{index}].output_max"),
        invert=bool(raw.get("invert", False)),
    )


def _as_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _as_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
