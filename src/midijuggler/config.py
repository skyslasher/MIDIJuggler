"""Configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import tomllib

from midijuggler.datapoint.types import ConnectionSpec, ModifierKind, SCALE_CURVES
from midijuggler.device.types import CustomPointSpec, DeviceConfig
from midijuggler.modules.modifier.feedback_suppress import parse_feedback_suppress_ms
from midijuggler.osc.desk_protocol import desk_mode_for_library


@dataclass(frozen=True)
class RuntimeConfig:
    datapoint_routing: bool = True
    feedback_suppress_ms: int = 500


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
    tap_tempo_min_taps: int = 4
    bpm_step: float = 0.5
    bpm_quantize: float = 0.5


@dataclass(frozen=True)
class AppConfig:
    web: WebConfig = field(default_factory=WebConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    adapters: dict[str, AdapterConfig] = field(default_factory=dict)
    devices: dict[str, DeviceConfig] = field(default_factory=dict)
    master_clock: MasterClockConfig = field(default_factory=MasterClockConfig)
    connections: list[ConnectionSpec] = field(default_factory=list)


DEFAULT_ADAPTERS = ("osc", "midi", "rtp_midi", "gpio", "hid", "wing_native")
MULTI_INSTANCE_ADAPTERS = ("osc", "midi", "rtp_midi", "hid", "wing_native")
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

    _save_adapter_configs(path, instances)


def remove_midi_adapter_configs(
    path: str | Path,
    instance_names: list[str],
) -> None:
    """Remove MIDI adapter sections from a TOML config file."""

    _remove_adapter_configs(path, instance_names)


def save_osc_adapter_configs(
    path: str | Path,
    instances: dict[str, AdapterConfig],
) -> None:
    """Persist editable OSC adapter sections in a TOML config file."""

    _save_adapter_configs(path, instances)


def remove_osc_adapter_configs(
    path: str | Path,
    instance_names: list[str],
) -> None:
    """Remove OSC adapter sections from a TOML config file."""

    _remove_adapter_configs(path, instance_names)


def save_wing_native_adapter_configs(
    path: str | Path,
    instances: dict[str, AdapterConfig],
) -> None:
    """Persist editable Wing native adapter sections in a TOML config file."""

    _save_adapter_configs(path, instances)


def remove_wing_native_adapter_configs(
    path: str | Path,
    instance_names: list[str],
) -> None:
    """Remove Wing native adapter sections from a TOML config file."""

    _remove_adapter_configs(path, instance_names)


def save_hid_adapter_configs(
    path: str | Path,
    instances: dict[str, AdapterConfig],
) -> None:
    """Persist editable HID adapter sections in a TOML config file."""

    _save_adapter_configs(path, instances)


def remove_hid_adapter_configs(
    path: str | Path,
    instance_names: list[str],
) -> None:
    """Remove HID adapter sections from a TOML config file."""

    _remove_adapter_configs(path, instance_names)


def _save_adapter_configs(
    path: str | Path,
    instances: dict[str, AdapterConfig],
) -> None:
    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    for instance_name, adapter in instances.items():
        header = f"[adapters.{instance_name}]"
        section = _format_adapter_section(instance_name, adapter)
        text = _replace_toml_section(text, header, section)

    temp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(config_path)


def _remove_adapter_configs(path: str | Path, instance_names: list[str]) -> None:
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


def save_master_clock_config(
    path: str | Path,
    config: MasterClockConfig,
    *,
    datapoint_routing: bool = False,
) -> None:
    """Persist the editable master clock config in a TOML config file."""

    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    section = _format_master_clock_section(config, datapoint_routing=datapoint_routing)
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


def save_devices(path: str | Path, devices: dict[str, DeviceConfig]) -> None:
    """Persist device definitions in a TOML config file."""

    config_path = Path(path)
    text = _remove_device_sections(config_path.read_text(encoding="utf-8"))
    ordered = [devices[key] for key in sorted(devices)]
    if ordered:
        text = text.rstrip() + "\n\n" + _format_devices_section(ordered)
    else:
        text = text.rstrip() + "\n"

    temp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(config_path)


def save_connections(path: str | Path, connections: list[ConnectionSpec]) -> None:
    """Persist connection specs in a TOML config file."""

    config_path = Path(path)
    text = _remove_connection_sections(config_path.read_text(encoding="utf-8"))
    if connections:
        text = text.rstrip() + "\n\n" + _format_connections_section(connections)
    else:
        text = text.rstrip() + "\n"

    temp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(config_path)


def save_runtime_config(path: str | Path, runtime: RuntimeConfig) -> None:
    """Persist runtime options in a TOML config file."""

    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    section = _format_runtime_section(runtime)
    new_text = _replace_toml_section(text, "[runtime]", section)

    temp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    temp_path.write_text(new_text, encoding="utf-8")
    temp_path.replace(config_path)


def _remove_device_sections(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() == "[[devices]]":
            index += 1
            while index < len(lines):
                stripped = lines[index].strip()
                if stripped == "[[devices]]":
                    break
                if (
                    stripped.startswith("[")
                    and stripped.endswith("]")
                    and stripped != "[[devices]]"
                ):
                    break
                index += 1
            continue
        kept.append(lines[index])
        index += 1
    return "\n".join(kept).rstrip() + "\n"


def _format_devices_section(devices: list[DeviceConfig]) -> str:
    blocks = [_format_device_config(device) for device in devices]
    return "\n\n".join(blocks) + "\n"


def _format_device_config(device: DeviceConfig) -> str:
    lines = [
        "[[devices]]",
        f"id = {_toml_string(device.id)}",
        f"adapter = {_toml_string(device.adapter)}",
    ]
    if device.label:
        lines.append(f"label = {_toml_string(device.label)}")
    if device.library:
        lines.append(f"library = {_toml_string(device.library)}")
    if device.library_kind:
        lines.append(f"library_kind = {_toml_string(device.library_kind)}")
    if device.feedback_refresh_interval > 0:
        lines.append(f"feedback_refresh_interval = {device.feedback_refresh_interval}")
    if device.midi_value_channel != 11:
        lines.append(f"midi_value_channel = {device.midi_value_channel}")
    if device.midi_display_channel != 12:
        lines.append(f"midi_display_channel = {device.midi_display_channel}")
    for point in device.custom_points:
        lines.extend(_format_custom_point_lines(point))
    return "\n".join(lines)


def _format_custom_point_lines(point: CustomPointSpec) -> list[str]:
    lines = [
        "",
        "[[devices.custom_points]]",
        f"id = {_toml_string(point.id)}",
    ]
    if point.value_type != "float":
        lines.append(f"value_type = {_toml_string(point.value_type)}")
    if point.direction != "bidirectional":
        lines.append(f"direction = {_toml_string(point.direction)}")
    if point.label:
        lines.append(f"label = {_toml_string(point.label)}")
    if point.value_min != 0.0:
        lines.append(f"value_min = {point.value_min}")
    if point.value_max != 127.0:
        lines.append(f"value_max = {point.value_max}")
    if point.protocol:
        lines.append(f"protocol = {_toml_string(point.protocol)}")
    if point.input_mode:
        lines.append(f"input_mode = {_toml_string(point.input_mode)}")
    if point.relative_encoding:
        lines.append(f"relative_encoding = {_toml_string(point.relative_encoding)}")
    return lines


def _remove_connection_sections(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() == "[[connections]]":
            index += 1
            while index < len(lines):
                stripped = lines[index].strip()
                if stripped == "[[connections]]":
                    break
                if (
                    stripped.startswith("[")
                    and stripped.endswith("]")
                    and stripped != "[[connections]]"
                ):
                    break
                index += 1
            continue
        kept.append(lines[index])
        index += 1
    return "\n".join(kept).rstrip() + "\n"


def _format_connections_section(connections: list[ConnectionSpec]) -> str:
    blocks = [_format_connection_spec(connection) for connection in connections]
    return "\n\n".join(blocks) + "\n"


def _format_connection_spec(connection: ConnectionSpec) -> str:
    lines = [
        "[[connections]]",
        f"id = {_toml_string(connection.id)}",
        f"source = {_toml_string(connection.source)}",
        f"target = {_toml_string(connection.target)}",
        f"modifier = {_toml_string(connection.modifier.value)}",
        f"input_min = {connection.input_min}",
        f"input_max = {connection.input_max}",
        f"output_min = {connection.output_min}",
        f"output_max = {connection.output_max}",
        f"invert = {_toml_bool(connection.invert)}",
    ]
    if connection.scale_curve != "linear":
        lines.append(f"scale_curve = {_toml_string(connection.scale_curve)}")
    if not connection.enabled:
        lines.append(f"enabled = {_toml_bool(connection.enabled)}")
    return "\n".join(lines)


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


def _adapter_section_end(lines: list[str], start: int) -> int:
    end = start + 1
    base_header = lines[start].strip()
    instance_name = ""
    if base_header.startswith("[adapters.") and base_header.endswith("]"):
        instance_name = base_header[len("[adapters.") : -1]
    inputs_header = f"[[adapters.{instance_name}.inputs]]" if instance_name else ""

    while end < len(lines):
        stripped = lines[end].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if inputs_header and stripped == inputs_header:
                end += 1
                while end < len(lines):
                    nested = lines[end].strip()
                    if nested.startswith("[") and nested.endswith("]"):
                        break
                    end += 1
                continue
            if stripped != base_header:
                break
        end += 1
    return end


def _remove_toml_section(text: str, header: str) -> str:
    lines = text.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.strip() == header),
        None,
    )
    if start is None:
        return text

    end = _adapter_section_end(lines, start)
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
    end = _adapter_section_end(lines, start)
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

    inputs = adapter.options.get("inputs")
    has_explicit_inputs = (
        isinstance(inputs, list) and inputs and isinstance(inputs[0], dict)
    )
    for key in sorted(adapter.options):
        if key == "inputs" and has_explicit_inputs:
            continue
        if key == "codes" and has_explicit_inputs:
            continue
        lines.append(f"{key} = {_format_toml_value(adapter.options[key])}")

    section = "\n".join(lines) + "\n"
    if has_explicit_inputs:
        for entry in inputs:
            if not isinstance(entry, dict):
                continue
            section += f"[[adapters.{instance_name}.inputs]]\n"
            for field in sorted(entry):
                section += f"{field} = {_format_toml_value(entry[field])}\n"
    return section + "\n"


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


def _format_master_clock_section(
    config: MasterClockConfig,
    *,
    datapoint_routing: bool = False,
) -> str:
    output_targets = ", ".join(_toml_string(target) for target in config.output_targets)
    section = (
        "[master_clock]\n"
        f"enabled = {_toml_bool(config.enabled)}\n"
        f"bpm = {config.bpm}\n"
        f"bpm_min = {config.bpm_min}\n"
        f"bpm_max = {config.bpm_max}\n"
        f"auto_start = {_toml_bool(config.auto_start)}\n"
        f"output_targets = [{output_targets}]\n"
    )
    if not datapoint_routing:
        section += (
            _format_optional_string_list("midi_input_targets", config.midi_input_targets)
            + _format_optional_string_list("osc_input_targets", config.osc_input_targets)
            + f"send_transport = {_toml_bool(config.send_transport)}\n"
            f"bpm_osc_address = {_toml_string(config.bpm_osc_address)}\n"
            f"click_interval_osc_address = {_toml_string(config.click_interval_osc_address)}\n"
            f"bpm_msb_cc = {config.bpm_msb_cc}\n"
            f"bpm_lsb_cc = {config.bpm_lsb_cc}\n"
            f"click_interval_cc = {config.click_interval_cc}\n"
            f"midi_channel = {config.midi_channel}\n"
        )
    else:
        section += f"send_transport = {_toml_bool(config.send_transport)}\n"
    section += (
        f"click_enabled = {_toml_bool(config.click_enabled)}\n"
        f"click_wav = {_toml_string(config.click_wav)}\n"
        f"click_interval = {_toml_string(config.click_interval)}\n"
        f"tap_tempo_min_taps = {config.tap_tempo_min_taps}\n"
        f"bpm_step = {config.bpm_step}\n"
        f"bpm_quantize = {config.bpm_quantize}\n"
        f"click_audio_device = {_toml_string(config.click_audio_device)}\n\n"
    )
    return section


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
    if raw.get("mappings"):
        raise ValueError(
            "[[mappings]] is no longer supported; configure [[devices]] and [[connections]]"
        )
    web_raw = raw.get("web", {})
    web = WebConfig(
        host=str(web_raw.get("host", "0.0.0.0")),
        port=_as_int(web_raw.get("port", 8080), "web.port"),
    )

    adapters = _parse_adapters(raw.get("adapters", {}))
    devices = _parse_devices(raw.get("devices", []), adapters)
    devices = supplement_devices(devices, adapters)
    master_clock = _parse_master_clock(raw.get("master_clock", {}))
    connections = [
        _parse_connection(index, connection_raw)
        for index, connection_raw in enumerate(raw.get("connections", []), start=1)
    ]
    connections = normalize_connections(connections, devices)
    runtime = _parse_runtime(raw.get("runtime", {}))
    _validate_devices_and_connections(devices, adapters, connections)

    return AppConfig(
        web=web,
        runtime=runtime,
        adapters=adapters,
        devices=devices,
        master_clock=master_clock,
        connections=connections,
    )


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

    tap_tempo_min_taps = _validate_tap_tempo_min_taps(
        raw.get("tap_tempo_min_taps", 4),
        "master_clock.tap_tempo_min_taps",
    )
    bpm_step = _validate_bpm_step(raw.get("bpm_step", 0.5), "master_clock.bpm_step")
    bpm_quantize = _validate_bpm_quantize(
        raw.get("bpm_quantize", 0.5),
        "master_clock.bpm_quantize",
    )

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
        tap_tempo_min_taps=tap_tempo_min_taps,
        bpm_step=bpm_step,
        bpm_quantize=bpm_quantize,
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


def _adapter_qualifies_for_device_inference(
    instance_name: str,
    adapter: AdapterConfig,
) -> bool:
    if instance_name not in DEFAULT_ADAPTERS:
        return True
    return adapter.enabled or bool(adapter.options)


def _infer_device_library(instance_name: str, adapter: AdapterConfig) -> tuple[str, str]:
    kind = adapter.kind or instance_name
    if kind in {"wing", "wing_native"}:
        return "behringer_wing", "wing"
    if kind == "midi":
        library = str(adapter.options.get("midi_library", "")).strip()
        return library, "midi"
    if kind in {"gpio", "hid", "rtp_midi"}:
        return "", kind
    library = str(adapter.options.get("osc_library", "")).strip()
    return library, "osc"


def _infer_device_from_adapter(instance_name: str, adapter: AdapterConfig) -> DeviceConfig:
    from midijuggler.midi.xtouch_channels import (
        DEFAULT_XTOUCH_DISPLAY_CHANNEL,
        DEFAULT_XTOUCH_VALUE_CHANNEL,
        XTOUCH_MINI_LIBRARY_ID,
        parse_midi_channel_option,
    )
    from midijuggler.midi.xtouch_feedback import parse_feedback_refresh_interval

    library, library_kind = _infer_device_library(instance_name, adapter)
    feedback_refresh_interval = 0.0
    midi_value_channel = DEFAULT_XTOUCH_VALUE_CHANNEL
    midi_display_channel = DEFAULT_XTOUCH_DISPLAY_CHANNEL
    if (adapter.kind or instance_name) == "midi" and (
        library == XTOUCH_MINI_LIBRARY_ID
        or "feedback_refresh_interval" in adapter.options
        or "midi_value_channel" in adapter.options
        or "midi_display_channel" in adapter.options
    ):
        if "feedback_refresh_interval" in adapter.options:
            feedback_refresh_interval = parse_feedback_refresh_interval(
                adapter.options["feedback_refresh_interval"]
            )
        if "midi_value_channel" in adapter.options:
            midi_value_channel = parse_midi_channel_option(
                adapter.options["midi_value_channel"],
                field_name="midi_value_channel",
                default=DEFAULT_XTOUCH_VALUE_CHANNEL,
            )
        if "midi_display_channel" in adapter.options:
            midi_display_channel = parse_midi_channel_option(
                adapter.options["midi_display_channel"],
                field_name="midi_display_channel",
                default=DEFAULT_XTOUCH_DISPLAY_CHANNEL,
            )
    return DeviceConfig(
        id=instance_name,
        adapter=instance_name,
        library=library,
        library_kind=library_kind,
        feedback_refresh_interval=feedback_refresh_interval,
        midi_value_channel=midi_value_channel,
        midi_display_channel=midi_display_channel,
    )


def adapter_device_options(
    adapters: dict[str, AdapterConfig],
    devices: dict[str, DeviceConfig],
) -> list[dict[str, Any]]:
    """Describe adapter instances that can be bound to logical devices."""

    bound_adapters = {device.adapter: device.id for device in devices.values()}
    options: list[dict[str, Any]] = []
    for instance_name, adapter in sorted(adapters.items()):
        if not _adapter_qualifies_for_device_inference(instance_name, adapter):
            continue
        inferred = _infer_device_from_adapter(instance_name, adapter)
        options.append(
            {
                "name": instance_name,
                "kind": adapter.kind or instance_name,
                "library": inferred.library,
                "library_kind": inferred.library_kind,
                "bound_device_id": bound_adapters.get(instance_name, ""),
            }
        )
    return options


def supplement_devices(
    devices: dict[str, DeviceConfig],
    adapters: dict[str, AdapterConfig],
) -> dict[str, DeviceConfig]:
    """Add inferred devices for configured adapters not yet bound to a device."""

    bound_adapters = {device.adapter for device in devices.values()}
    supplemented = dict(devices)
    for instance_name, adapter in adapters.items():
        if instance_name in bound_adapters:
            continue
        if instance_name in supplemented:
            continue
        if not _adapter_qualifies_for_device_inference(instance_name, adapter):
            continue
        supplemented[instance_name] = _infer_device_from_adapter(instance_name, adapter)
    return supplemented


def _parse_devices(raw: Any, adapters: dict[str, AdapterConfig]) -> dict[str, DeviceConfig]:
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise ValueError("devices must be a list of [[devices]] tables")

    devices: dict[str, DeviceConfig] = {}
    for index, item in enumerate(raw, start=1):
        device = _parse_device(index, item)
        if device.id in devices:
            raise ValueError(f"devices[{index}] duplicates device id {device.id!r}")
        if device.adapter not in adapters:
            raise ValueError(
                f"devices[{index}] references unknown adapter {device.adapter!r}"
            )
        devices[device.id] = device
    return devices


def _parse_device(index: int, raw: Any) -> DeviceConfig:
    from midijuggler.midi.xtouch_channels import (
        DEFAULT_XTOUCH_DISPLAY_CHANNEL,
        DEFAULT_XTOUCH_VALUE_CHANNEL,
        XTOUCH_MINI_LIBRARY_ID,
        parse_midi_channel_option,
    )
    from midijuggler.midi.xtouch_feedback import parse_feedback_refresh_interval

    if not isinstance(raw, dict):
        raise ValueError(f"devices[{index}] must be a table")

    device_id = str(raw.get("id", "")).strip()
    adapter = str(raw.get("adapter", "")).strip()
    if not device_id:
        raise ValueError(f"devices[{index}] missing required field: id")
    if not adapter:
        raise ValueError(f"devices[{index}] missing required field: adapter")
    if ":" in device_id or any(character.isspace() for character in device_id):
        raise ValueError(f"devices[{index}].id cannot contain ':' or whitespace")

    custom_points = tuple(
        _parse_custom_point(index, point_index, point_raw)
        for point_index, point_raw in enumerate(raw.get("custom_points", []), start=1)
    )
    library = str(raw.get("library", "")).strip()
    feedback_refresh_interval = 0.0
    midi_value_channel = DEFAULT_XTOUCH_VALUE_CHANNEL
    midi_display_channel = DEFAULT_XTOUCH_DISPLAY_CHANNEL
    if "feedback_refresh_interval" in raw:
        feedback_refresh_interval = parse_feedback_refresh_interval(
            raw["feedback_refresh_interval"]
        )
    if "midi_value_channel" in raw:
        midi_value_channel = parse_midi_channel_option(
            raw["midi_value_channel"],
            field_name=f"devices[{index}].midi_value_channel",
            default=DEFAULT_XTOUCH_VALUE_CHANNEL,
        )
    if "midi_display_channel" in raw:
        midi_display_channel = parse_midi_channel_option(
            raw["midi_display_channel"],
            field_name=f"devices[{index}].midi_display_channel",
            default=DEFAULT_XTOUCH_DISPLAY_CHANNEL,
        )
    if feedback_refresh_interval > 0 and library != XTOUCH_MINI_LIBRARY_ID:
        raise ValueError(
            f"devices[{index}].feedback_refresh_interval is only supported for "
            "behringer_xtouch_mini"
        )
    if library != XTOUCH_MINI_LIBRARY_ID and (
        "midi_value_channel" in raw or "midi_display_channel" in raw
    ):
        raise ValueError(
            f"devices[{index}] midi_value_channel and midi_display_channel are only "
            "supported for behringer_xtouch_mini"
        )
    return DeviceConfig(
        id=device_id,
        adapter=adapter,
        library=library,
        library_kind=str(raw.get("library_kind", "")).strip(),
        label=str(raw.get("label", "")).strip(),
        custom_points=custom_points,
        feedback_refresh_interval=feedback_refresh_interval,
        midi_value_channel=midi_value_channel,
        midi_display_channel=midi_display_channel,
    )


def _parse_custom_point(device_index: int, point_index: int, raw: Any) -> CustomPointSpec:
    field_name = f"devices[{device_index}].custom_points[{point_index}]"
    if not isinstance(raw, dict):
        raise ValueError(f"{field_name} must be a table")
    point_id = str(raw.get("id", "")).strip()
    if not point_id:
        raise ValueError(f"{field_name} missing required field: id")
    return CustomPointSpec(
        id=point_id,
        value_type=str(raw.get("value_type", "float")),
        direction=str(raw.get("direction", "bidirectional")),
        label=str(raw.get("label", "")),
        value_min=_as_float(raw.get("value_min", 0.0), f"{field_name}.value_min"),
        value_max=_as_float(raw.get("value_max", 127.0), f"{field_name}.value_max"),
        protocol=str(raw.get("protocol", "")),
        input_mode=str(raw.get("input_mode", "")),
        relative_encoding=str(raw.get("relative_encoding", "")),
    )


def normalize_connections(
    connections: list[ConnectionSpec],
    devices: dict[str, DeviceConfig],
) -> list[ConnectionSpec]:
    """Rewrite legacy adapter-prefixed endpoints to configured device ids."""

    normalized: list[ConnectionSpec] = []
    for connection in connections:
        source = normalize_connection_endpoint(connection.source, devices)
        target = normalize_connection_endpoint(connection.target, devices)
        if source == connection.source and target == connection.target:
            normalized.append(connection)
            continue
        normalized.append(
            ConnectionSpec(
                id=connection.id,
                source=source,
                target=target,
                modifier=connection.modifier,
                input_min=connection.input_min,
                input_max=connection.input_max,
                output_min=connection.output_min,
                output_max=connection.output_max,
                invert=connection.invert,
                scale_curve=connection.scale_curve,
                enabled=connection.enabled,
            )
        )
    return normalized


def normalize_connection_endpoint(
    endpoint: str,
    devices: dict[str, DeviceConfig],
) -> str:
    module, separator, point = endpoint.partition(".")
    if not separator or module in {"clock", "mapping"}:
        return endpoint

    resolved = resolve_connection_device_module(module, devices)
    if resolved is None or resolved == module:
        return endpoint
    return f"{resolved}.{point}"


def _library_shorthand(library_id: str) -> str:
    desk_mode = desk_mode_for_library(library_id)
    if desk_mode:
        return desk_mode
    for prefix in ("behringer_", "presonus_"):
        if library_id.startswith(prefix):
            return library_id[len(prefix) :]
    return library_id


def resolve_connection_device_module(
    module: str,
    devices: dict[str, DeviceConfig],
) -> str | None:
    if module in devices:
        return module

    adapter_to_device = {device.adapter: device.id for device in devices.values()}
    if module in adapter_to_device:
        return adapter_to_device[module]

    prefix_matches = sorted(
        {
            device.id
            for device in devices.values()
            if device.id == module
            or device.adapter == module
            or device.id.startswith(f"{module}_")
            or device.adapter.startswith(f"{module}_")
        }
    )
    if len(prefix_matches) == 1:
        return prefix_matches[0]

    library_matches = sorted(
        {
            device.id
            for device in devices.values()
            if device.library and _library_shorthand(device.library) == module
        }
    )
    if len(library_matches) == 1:
        return library_matches[0]
    return None


def _validate_devices_and_connections(
    devices: dict[str, DeviceConfig],
    adapters: dict[str, AdapterConfig],
    connections: list[ConnectionSpec],
) -> None:
    adapter_bindings: dict[str, str] = {}
    for device in devices.values():
        if device.adapter in adapter_bindings:
            raise ValueError(
                f"adapter {device.adapter!r} is bound to multiple devices "
                f"({adapter_bindings[device.adapter]!r} and {device.id!r})"
            )
        adapter_bindings[device.adapter] = device.id

    for connection in connections:
        for endpoint in (connection.source, connection.target):
            module = endpoint.partition(".")[0]
            if module in {"clock", "mapping"}:
                continue
            if module not in devices:
                available = ", ".join(sorted(devices))
                raise ValueError(
                    f"connection {connection.id!r} endpoint {endpoint!r} "
                    f"must reference a configured device id "
                    f"(available: {available})"
                )


def _parse_connection(index: int, raw: Any) -> ConnectionSpec:
    if not isinstance(raw, dict):
        raise ValueError(f"connections[{index}] must be a table")

    required = ("id", "source", "target")
    missing = [key for key in required if not raw.get(key)]
    if missing:
        raise ValueError(f"connections[{index}] missing required fields: {', '.join(missing)}")

    modifier = str(raw.get("modifier", ModifierKind.RANGE_MAP.value))
    try:
        modifier_kind = ModifierKind(modifier)
    except ValueError as exc:
        raise ValueError(f"connections[{index}] has unsupported modifier: {modifier}") from exc

    scale_curve = str(raw.get("scale_curve", "linear")).strip() or "linear"
    if scale_curve not in SCALE_CURVES:
        raise ValueError(
            f"connections[{index}] scale_curve must be one of: "
            f"{', '.join(sorted(SCALE_CURVES))}"
        )

    return ConnectionSpec(
        id=str(raw["id"]),
        source=str(raw["source"]),
        target=str(raw["target"]),
        modifier=modifier_kind,
        input_min=_as_float(raw.get("input_min", 0.0), f"connections[{index}].input_min"),
        input_max=_as_float(raw.get("input_max", 1.0), f"connections[{index}].input_max"),
        output_min=_as_float(raw.get("output_min", 0.0), f"connections[{index}].output_min"),
        output_max=_as_float(raw.get("output_max", 127.0), f"connections[{index}].output_max"),
        invert=bool(raw.get("invert", False)),
        scale_curve=scale_curve,
        enabled=bool(raw.get("enabled", True)),
    )


def _format_runtime_section(runtime: RuntimeConfig) -> str:
    lines = [
        "[runtime]",
        f"datapoint_routing = {_toml_bool(runtime.datapoint_routing)}",
        f"feedback_suppress_ms = {runtime.feedback_suppress_ms}",
    ]
    return "\n".join(lines) + "\n\n"


def _parse_runtime(raw: Any) -> RuntimeConfig:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("runtime must be a table")
    return RuntimeConfig(
        datapoint_routing=bool(raw.get("datapoint_routing", True)),
        feedback_suppress_ms=parse_feedback_suppress_ms(raw.get("feedback_suppress_ms", 500)),
    )


def _parse_optional_string_list(raw: Any, field_name: str) -> list[str] | None:
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError(f"{field_name} must be a list")
    return [str(item) for item in raw]


def _validate_tap_tempo_min_taps(value: Any, field_name: str) -> int:
    parsed = _as_int(value, field_name)
    if parsed < 3:
        raise ValueError(f"{field_name} must be at least 3")
    return parsed


def _validate_bpm_step(value: Any, field_name: str) -> float:
    parsed = _as_float(value, field_name)
    if parsed <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return parsed


def _validate_bpm_quantize(value: Any, field_name: str) -> float:
    parsed = _as_float(value, field_name)
    if parsed not in {0.5, 1.0}:
        raise ValueError(f"{field_name} must be 0.5 or 1.0")
    return parsed


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
