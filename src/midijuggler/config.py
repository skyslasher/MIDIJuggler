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
class MasterClockConfig:
    enabled: bool = False
    bpm: float = 120.0
    bpm_min: float = 20.0
    bpm_max: float = 300.0
    auto_start: bool = False
    output_targets: list[str] = field(default_factory=list)
    midi_input_targets: list[str] | None = None
    osc_input_targets: list[str] | None = None
    send_transport: bool = True
    bpm_osc_address: str = "/midijuggler/clock/bpm"
    click_interval_osc_address: str = "/midijuggler/clock/click_interval"
    bpm_msb_cc: int = 20
    bpm_lsb_cc: int = 21
    click_interval_cc: int = 22
    midi_channel: int = 1
    click_enabled: bool = False
    click_wav: str = ""
    click_interval: str = "quarter"
    click_command: str = "aplay"
    click_audio_device: str = ""


@dataclass(frozen=True)
class AppConfig:
    web: WebConfig = field(default_factory=WebConfig)
    adapters: dict[str, AdapterConfig] = field(default_factory=dict)
    master_clock: MasterClockConfig = field(default_factory=MasterClockConfig)
    mappings: list[MappingRule] = field(default_factory=list)


DEFAULT_ADAPTERS = ("osc", "midi", "rtp_midi", "gpio")
MULTI_INSTANCE_ADAPTERS = ("osc", "midi", "rtp_midi")
LEGACY_USB_MIDI_KIND = "usb_midi"


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    return parse_config(raw)


def save_midi_adapter_configs(
    path: str | Path,
    instances: dict[str, AdapterConfig],
) -> None:
    """Persist editable MIDI adapter sections in a TOML config file."""

    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    for instance_name, adapter in instances.items():
        header = f"[adapters.{instance_name}]"
        section = _format_adapter_section(instance_name, adapter)
        text = _replace_toml_section(text, header, section)

    temp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(config_path)


def remove_midi_adapter_configs(
    path: str | Path,
    instance_names: list[str],
) -> None:
    """Remove MIDI adapter sections from a TOML config file."""

    if not instance_names:
        return

    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    for instance_name in instance_names:
        text = _remove_toml_section(text, f"[adapters.{instance_name}]")

    temp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(config_path)


def save_gpio_adapter_options(path: str | Path, options: dict[str, Any]) -> None:
    """Persist the editable GPIO adapter options in a TOML config file."""

    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    section = _format_gpio_adapter_section(options)
    new_text = _replace_toml_section(text, "[adapters.gpio]", section)

    temp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    temp_path.write_text(new_text, encoding="utf-8")
    temp_path.replace(config_path)


def save_master_clock_config(path: str | Path, config: MasterClockConfig) -> None:
    """Persist the editable master clock config in a TOML config file."""

    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    section = _format_master_clock_section(config)
    new_text = _replace_toml_section(text, "[master_clock]", section)

    temp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    temp_path.write_text(new_text, encoding="utf-8")
    temp_path.replace(config_path)


def save_mappings(path: str | Path, mappings: list[MappingRule]) -> None:
    """Persist mapping rules in a TOML config file."""

    config_path = Path(path)
    text = _remove_mapping_sections(config_path.read_text(encoding="utf-8"))
    if mappings:
        text = text.rstrip() + "\n\n" + _format_mappings_section(mappings)
    else:
        text = text.rstrip() + "\n"

    temp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(config_path)


def _remove_mapping_sections(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() == "[[mappings]]":
            index += 1
            while index < len(lines):
                stripped = lines[index].strip()
                if stripped == "[[mappings]]":
                    break
                if (
                    stripped.startswith("[")
                    and stripped.endswith("]")
                    and stripped != "[[mappings]]"
                ):
                    break
                index += 1
            continue
        kept.append(lines[index])
        index += 1
    return "\n".join(kept).rstrip() + "\n"


def _format_mappings_section(mappings: list[MappingRule]) -> str:
    blocks = [_format_mapping_rule(rule) for rule in mappings]
    return "\n\n".join(blocks) + "\n"


def _format_mapping_rule(rule: MappingRule) -> str:
    lines = [
        "[[mappings]]",
        f"id = {_toml_string(rule.id)}",
        f"source = {_toml_string(rule.source)}",
        f"target = {_toml_string(rule.target)}",
        f"input_min = {rule.input_min}",
        f"input_max = {rule.input_max}",
        f"output_min = {rule.output_min}",
        f"output_max = {rule.output_max}",
        f"invert = {_toml_bool(rule.invert)}",
    ]
    return "\n".join(lines)


def _remove_toml_section(text: str, header: str) -> str:
    lines = text.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.strip() == header),
        None,
    )
    if start is None:
        return text

    end = start + 1
    while end < len(lines):
        stripped = lines[end].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            break
        end += 1

    new_lines = [*lines[:start], *lines[end:]]
    return "\n".join(new_lines).rstrip() + "\n"


def _replace_toml_section(text: str, header: str, section: str) -> str:
    lines = text.splitlines()

    start = next(
        (index for index, line in enumerate(lines) if line.strip() == header),
        None,
    )
    if start is None:
        return text.rstrip() + "\n\n" + section
    else:
        end = start + 1
        while end < len(lines):
            stripped = lines[end].strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                break
            end += 1
        new_lines = [*lines[:start], *section.rstrip().splitlines(), "", *lines[end:]]
        return "\n".join(new_lines).rstrip() + "\n"


def _format_adapter_section(instance_name: str, adapter: AdapterConfig) -> str:
    kind = adapter.kind or instance_name
    lines = [
        f"[adapters.{instance_name}]",
        f"enabled = {_toml_bool(adapter.enabled)}",
    ]
    if instance_name not in DEFAULT_ADAPTERS:
        lines.append(f"type = {_toml_string(kind)}")
    for key in sorted(adapter.options):
        lines.append(f"{key} = {_format_toml_value(adapter.options[key])}")
    return "\n".join(lines) + "\n\n"


def _format_toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return _toml_bool(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, list):
        items = ", ".join(_format_toml_value(item) for item in value)
        return f"[{items}]"
    return _toml_string(str(value))


def _format_gpio_adapter_section(options: dict[str, Any]) -> str:
    pins = [int(pin) for pin in options.get("pins", [])]
    active_low = bool(options.get("active_low", True))
    bounce_ms = int(float(options.get("bounce_ms", 25)))
    poll_interval_ms = int(float(options.get("poll_interval_ms", 5)))
    return (
        "[adapters.gpio]\n"
        "enabled = true\n"
        f"pins = [{', '.join(str(pin) for pin in pins)}]\n"
        f"active_low = {_toml_bool(active_low)}\n"
        f"bounce_ms = {bounce_ms}\n"
        f"poll_interval_ms = {poll_interval_ms}\n\n"
    )


def _format_master_clock_section(config: MasterClockConfig) -> str:
    output_targets = ", ".join(_toml_string(target) for target in config.output_targets)
    return (
        "[master_clock]\n"
        f"enabled = {_toml_bool(config.enabled)}\n"
        f"bpm = {config.bpm}\n"
        f"bpm_min = {config.bpm_min}\n"
        f"bpm_max = {config.bpm_max}\n"
        f"auto_start = {_toml_bool(config.auto_start)}\n"
        f"output_targets = [{output_targets}]\n"
        + _format_optional_string_list("midi_input_targets", config.midi_input_targets)
        + _format_optional_string_list("osc_input_targets", config.osc_input_targets)
        + f"send_transport = {_toml_bool(config.send_transport)}\n"
        f"bpm_osc_address = {_toml_string(config.bpm_osc_address)}\n"
        f"click_interval_osc_address = {_toml_string(config.click_interval_osc_address)}\n"
        f"bpm_msb_cc = {config.bpm_msb_cc}\n"
        f"bpm_lsb_cc = {config.bpm_lsb_cc}\n"
        f"click_interval_cc = {config.click_interval_cc}\n"
        f"midi_channel = {config.midi_channel}\n"
        f"click_enabled = {_toml_bool(config.click_enabled)}\n"
        f"click_wav = {_toml_string(config.click_wav)}\n"
        f"click_interval = {_toml_string(config.click_interval)}\n"
        f"click_audio_device = {_toml_string(config.click_audio_device)}\n\n"
    )


def _format_optional_string_list(name: str, values: list[str] | None) -> str:
    if values is None:
        return ""
    items = ", ".join(_toml_string(value) for value in values)
    return f"{name} = [{items}]\n"


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _normalize_legacy_usb_midi(raw: dict[str, Any]) -> None:
    adapters = raw.get("adapters")
    if isinstance(adapters, dict):
        if LEGACY_USB_MIDI_KIND in adapters and "midi" not in adapters:
            adapters["midi"] = adapters.pop(LEGACY_USB_MIDI_KIND)
        for adapter_raw in adapters.values():
            if isinstance(adapter_raw, dict) and adapter_raw.get("type") == LEGACY_USB_MIDI_KIND:
                adapter_raw["type"] = "midi"

    master_clock = raw.get("master_clock")
    if isinstance(master_clock, dict):
        for field in ("output_targets", "midi_input_targets"):
            targets = master_clock.get(field)
            if isinstance(targets, list):
                master_clock[field] = [
                    "midi" if str(target) == LEGACY_USB_MIDI_KIND else str(target)
                    for target in targets
                ]

    mappings = raw.get("mappings")
    if isinstance(mappings, list):
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            for field in ("source", "target"):
                value = mapping.get(field)
                if isinstance(value, str) and value.startswith(f"{LEGACY_USB_MIDI_KIND}:"):
                    mapping[field] = "midi" + value[len(LEGACY_USB_MIDI_KIND) :]


def parse_config(raw: dict[str, Any]) -> AppConfig:
    _normalize_legacy_usb_midi(raw)
    web_raw = raw.get("web", {})
    web = WebConfig(
        host=str(web_raw.get("host", "0.0.0.0")),
        port=_as_int(web_raw.get("port", 8080), "web.port"),
    )

    adapters = _parse_adapters(raw.get("adapters", {}))
    master_clock = _parse_master_clock(raw.get("master_clock", {}))

    mappings = [
        _parse_mapping(index, mapping_raw)
        for index, mapping_raw in enumerate(raw.get("mappings", []), start=1)
    ]

    return AppConfig(web=web, adapters=adapters, master_clock=master_clock, mappings=mappings)


def _parse_master_clock(raw: Any) -> MasterClockConfig:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("master_clock must be a table")

    bpm_min = _as_float(raw.get("bpm_min", 20.0), "master_clock.bpm_min")
    bpm_max = _as_float(raw.get("bpm_max", 300.0), "master_clock.bpm_max")
    bpm = _as_float(raw.get("bpm", 120.0), "master_clock.bpm")
    if bpm_min <= 0 or bpm_max <= 0 or bpm_min >= bpm_max:
        raise ValueError("master_clock bpm_min/bpm_max must be positive and ordered")
    if not bpm_min <= bpm <= bpm_max:
        raise ValueError("master_clock.bpm must be inside bpm_min/bpm_max")

    output_targets = raw.get("output_targets", [])
    if not isinstance(output_targets, list):
        raise ValueError("master_clock.output_targets must be a list")

    midi_input_targets = _parse_optional_string_list(
        raw.get("midi_input_targets"),
        "master_clock.midi_input_targets",
    )
    osc_input_targets = _parse_optional_string_list(
        raw.get("osc_input_targets"),
        "master_clock.osc_input_targets",
    )

    click_interval = str(raw.get("click_interval", "quarter"))
    if click_interval not in {"eighth", "quarter", "half", "whole"}:
        raise ValueError("master_clock.click_interval must be eighth, quarter, half or whole")

    return MasterClockConfig(
        enabled=bool(raw.get("enabled", False)),
        bpm=bpm,
        bpm_min=bpm_min,
        bpm_max=bpm_max,
        auto_start=bool(raw.get("auto_start", False)),
        output_targets=[str(target) for target in output_targets],
        midi_input_targets=midi_input_targets,
        osc_input_targets=osc_input_targets,
        send_transport=bool(raw.get("send_transport", True)),
        bpm_osc_address=str(raw.get("bpm_osc_address", "/midijuggler/clock/bpm")),
        click_interval_osc_address=str(
            raw.get("click_interval_osc_address", "/midijuggler/clock/click_interval")
        ),
        bpm_msb_cc=_as_int(raw.get("bpm_msb_cc", 20), "master_clock.bpm_msb_cc"),
        bpm_lsb_cc=_as_int(raw.get("bpm_lsb_cc", 21), "master_clock.bpm_lsb_cc"),
        click_interval_cc=_as_int(
            raw.get("click_interval_cc", 22),
            "master_clock.click_interval_cc",
        ),
        midi_channel=_as_int(raw.get("midi_channel", 1), "master_clock.midi_channel"),
        click_enabled=bool(raw.get("click_enabled", False)),
        click_wav=str(raw.get("click_wav", "")),
        click_interval=click_interval,
        click_command=str(raw.get("click_command", "aplay")),
        click_audio_device=str(raw.get("click_audio_device", "")),
    )


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
    if kind == LEGACY_USB_MIDI_KIND:
        kind = "midi"
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


def _parse_optional_string_list(raw: Any, field_name: str) -> list[str] | None:
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError(f"{field_name} must be a list")
    return [str(item) for item in raw]


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
