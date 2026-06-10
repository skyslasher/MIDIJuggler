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


@dataclass(frozen=True)
class AppConfig:
    web: WebConfig = field(default_factory=WebConfig)
    adapters: dict[str, AdapterConfig] = field(default_factory=dict)
    mappings: list[MappingRule] = field(default_factory=list)


DEFAULT_ADAPTERS = ("osc", "usb_midi", "rtp_midi", "gpio")


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

    adapters_raw = raw.get("adapters", {})
    adapters = {
        name: _parse_adapter(name, adapters_raw.get(name, {}))
        for name in DEFAULT_ADAPTERS
    }

    mappings = [
        _parse_mapping(index, mapping_raw)
        for index, mapping_raw in enumerate(raw.get("mappings", []), start=1)
    ]

    return AppConfig(web=web, adapters=adapters, mappings=mappings)


def _parse_adapter(name: str, raw: Any) -> AdapterConfig:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"adapters.{name} must be a table")
    options = {key: value for key, value in raw.items() if key != "enabled"}
    return AdapterConfig(enabled=bool(raw.get("enabled", False)), options=options)


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
