"""Interactive mapping learn mode."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from midijuggler.config import AdapterConfig, AppConfig
from midijuggler.datapoint.bridge import adapter_control_to_datapoint, legacy_target_to_datapoint
from midijuggler.datapoint.disconnected import is_disconnected_endpoint
from midijuggler.datapoint.types import ConnectionSpec, DataPointId, ModifierKind
from midijuggler.datapoint.store import DataPointStore
from midijuggler.device.registry import DeviceRegistry
from midijuggler.device.types import DeviceConfig
from midijuggler.midi.library_match import (
    MidiSourceIndex,
    build_source_index,
    resolve_incoming_controls,
    resolve_library_port,
)
from midijuggler.midi_library import get_midi_library
from midijuggler.osc_library import get_osc_library


@dataclass(frozen=True)
class LearnSource:
    adapter: str
    control: str

    @property
    def key(self) -> str:
        return f"{self.adapter}:{self.control}"


@dataclass(frozen=True)
class LearnState:
    enabled: bool = False
    phase: str = "idle"
    source: LearnSource | None = None
    source_datapoint: str | None = None
    message: str = ""

    def as_dict(self) -> dict[str, str | bool | None]:
        return {
            "enabled": self.enabled,
            "phase": self.phase,
            "source": None if self.source is None else self.source.key,
            "source_datapoint": self.source_datapoint,
            "source_adapter": None if self.source is None else self.source.adapter,
            "source_control": None if self.source is None else self.source.control,
            "message": self.message,
        }


class LearnController:
    """Capture control sources and build mapping rules from them."""

    def __init__(self) -> None:
        self._state = LearnState()

    @property
    def state(self) -> LearnState:
        return self._state

    def set_enabled(self, enabled: bool) -> LearnState:
        if enabled:
            self._state = LearnState(
                enabled=True,
                phase="waiting_source",
                message=(
                    "Select a source data point from the list or use Learn."
                ),
            )
        else:
            self._state = LearnState()
        return self._state

    def clear_source(self) -> LearnState:
        if not self._state.enabled:
            return self._state
        self._state = LearnState(
            enabled=True,
            phase="waiting_source",
            message=(
                "Select a source data point from the list or use Learn."
            ),
        )
        return self._state

    def select_source(
        self,
        source: LearnSource,
        *,
        device_registry: DeviceRegistry | None = None,
    ) -> LearnState:
        if not self._state.enabled:
            raise ValueError("learn mode is disabled")

        if device_registry is not None:
            if device_registry.get(source.adapter) is not None:
                source_datapoint = str(
                    DataPointId(source.adapter, source.control)
                )
            else:
                source_datapoint = adapter_control_to_datapoint(
                    source.adapter,
                    source.control,
                    device_registry,
                )
        else:
            source_datapoint = f"{source.adapter}.{source.control}"
        self._state = LearnState(
            enabled=True,
            phase="waiting_target",
            source=source,
            source_datapoint=source_datapoint,
            message=(
                f"Source selected: {source_datapoint}. "
                "Select a target data point and modifier."
            ),
        )
        return self._state

    def select_source_datapoint(self, point_id: str) -> LearnState:
        if not self._state.enabled:
            raise ValueError("learn mode is disabled")

        normalized = str(point_id).strip()
        DataPointId.parse(normalized)
        module = normalized.partition(".")[0]
        if module in {"clock", "mapping"}:
            raise ValueError(f"cannot map {module} data points")

        self._state = LearnState(
            enabled=True,
            phase="waiting_target",
            source_datapoint=normalized,
            message=(
                f"Source selected: {normalized}. "
                "Select a target data point and modifier."
            ),
        )
        return self._state

    def build_mapping(
        self,
        config: AppConfig,
        *,
        source: LearnSource,
        target_adapter: str,
        target_parameter_id: str,
        mapping_id: str | None = None,
        device_registry: DeviceRegistry | None = None,
    ) -> ConnectionSpec:
        registry = device_registry or DeviceRegistry.from_config(config)
        source_device = registry.require_device_for_adapter(source.adapter)
        target_device = registry.require_device_for_adapter(target_adapter)
        source_datapoint = str(DataPointId(source_device.uid, source.control))
        target_address = resolve_osc_target_address(config, target_device, target_parameter_id)
        target_datapoint = str(DataPointId(target_device.uid, target_address))
        input_min, input_max = lookup_midi_source_ranges(
            config,
            source.adapter,
            source.control,
        )
        output_min, output_max = lookup_osc_target_ranges(
            config,
            target_adapter,
            target_parameter_id,
        )
        rule_id = mapping_id or make_mapping_id(source_datapoint, target_datapoint)
        return ConnectionSpec(
            id=rule_id,
            source=source_datapoint,
            target=target_datapoint,
            input_min=input_min,
            input_max=input_max,
            output_min=output_min,
            output_max=output_max,
            invert=False,
        )

    def build_connection(
        self,
        *,
        source_datapoint: str,
        target_datapoint: str,
        modifier: ModifierKind = ModifierKind.RANGE_MAP,
        input_min: float = 0.0,
        input_max: float = 1.0,
        output_min: float = 0.0,
        output_max: float = 127.0,
        invert: bool = False,
        scale_curve: str = "linear",
        factor: float = 1.0,
        connection_id: str | None = None,
    ) -> ConnectionSpec:
        DataPointId.parse(source_datapoint)
        DataPointId.parse(target_datapoint)
        resolved_id = connection_id or make_mapping_id(source_datapoint, target_datapoint)
        return ConnectionSpec(
            id=resolved_id,
            source=source_datapoint,
            target=target_datapoint,
            modifier=modifier,
            input_min=input_min,
            input_max=input_max,
            output_min=output_min,
            output_max=output_max,
            invert=invert,
            scale_curve=scale_curve,
            factor=factor,
        )


def resolve_monitor_source(config: AppConfig, event: dict[str, Any]) -> LearnSource:
    """Resolve a monitor event payload into a mapping source."""

    kind = str(event.get("kind", "")).strip()
    adapter_name = str(event.get("source", "")).strip()
    if not adapter_name:
        raise ValueError("monitor event source is required")

    if kind == "ControlEvent":
        control = str(event.get("control", "")).strip()
        if not control:
            raise ValueError("monitor ControlEvent is missing control")
        if adapter_name in {"clock", "mapping"}:
            raise ValueError(f"cannot map {adapter_name} events")
        return LearnSource(adapter=adapter_name, control=control)

    if kind == "MidiMessageEvent":
        if str(event.get("direction", "input")) != "input":
            raise ValueError("only input MIDI messages can be mapped")
        adapter = config.adapters.get(adapter_name)
        if adapter is None:
            raise ValueError(f"unknown adapter source {adapter_name!r}")

        status = int(event.get("status", 0))
        data = tuple(int(value) for value in event.get("data", []))
        matches = resolve_incoming_controls(
            build_midi_source_index_for_adapter(config, adapter_name),
            status,
            data,
        )
        if not matches:
            raise ValueError("could not resolve MIDI message to a mapping source")
        return LearnSource(adapter=adapter_name, control=matches[0].control_id)

    if kind == "OscMessageEvent":
        if str(event.get("direction", "input")) != "input":
            raise ValueError("only input OSC messages can be mapped")
        address = str(event.get("address", "")).strip()
        if not address:
            raise ValueError("monitor OscMessageEvent is missing address")
        return LearnSource(adapter=adapter_name, control=address)

    if kind == "GpioEvent":
        control = str(event.get("control", "")).strip()
        if not control:
            raise ValueError("monitor GpioEvent is missing control")
        return LearnSource(adapter=adapter_name, control=control)

    if kind == "HidEvent":
        control = str(event.get("control", "")).strip()
        if not control:
            raise ValueError("monitor HidEvent is missing control")
        return LearnSource(adapter=adapter_name, control=control)

    if kind == "HidLearnEvent":
        control = str(event.get("suggested_control", "")).strip()
        if not control:
            code = str(event.get("code", "")).strip()
            control = code.lower() if code else ""
        if not control:
            raise ValueError("monitor HidLearnEvent is missing suggested_control")
        return LearnSource(adapter=adapter_name, control=control)

    if kind == "DataPointValue":
        point_id = str(event.get("id", "")).strip()
        if not point_id:
            raise ValueError("monitor DataPointValue is missing id")
        module, separator, point = point_id.partition(".")
        if not separator:
            raise ValueError(f"invalid data point id: {point_id!r}")
        if module in {"clock", "mapping"}:
            raise ValueError(f"cannot map {module} data points")
        return LearnSource(adapter=module, control=point)

    raise ValueError(f"unsupported monitor event kind: {kind!r}")


def build_midi_source_index_for_device(
    device: DeviceConfig,
    adapter: AdapterConfig,
) -> MidiSourceIndex | None:
    library_id = device.library.strip()
    if not library_id:
        return None

    try:
        library = get_midi_library(library_id)
    except KeyError:
        return None

    return build_source_index(library, resolve_library_port(adapter), adapter=adapter)


def build_midi_source_index_for_adapter(
    config: AppConfig,
    adapter_name: str,
) -> MidiSourceIndex | None:
    device = DeviceRegistry.from_config(config).device_for_adapter(adapter_name)
    if device is None:
        return None
    adapter = config.adapters.get(adapter_name)
    if adapter is None:
        return None
    return build_midi_source_index_for_device(device, adapter)


def make_mapping_id(source: str, target: str) -> str:
    def slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")

    candidate = f"learn-{slug(source)}-to-{slug(target)}"
    return candidate[:120]


def resolve_osc_target_address(
    config: AppConfig,
    device: DeviceConfig,
    parameter_id: str,
) -> str:
    adapter = config.adapters.get(device.adapter)
    if adapter is None:
        raise ValueError(f"unknown adapter for device {device.id!r}")

    library_id = _device_library_id(device, adapter)
    library = get_osc_library(library_id)
    parameter = next(
        (entry for entry in library.parameters if entry.id == parameter_id),
        None,
    )
    if parameter is None:
        raise ValueError(
            f"unknown desk parameter {parameter_id!r} in library {library_id!r}"
        )
    if parameter.direction != "target":
        raise ValueError(f"desk parameter {parameter_id!r} is not a target")

    return parameter.address


def _device_library_id(device: DeviceConfig, adapter: AdapterConfig) -> str:
    if device.library:
        return device.library
    kind = device.library_kind or adapter.kind or device.adapter
    if kind in {"wing", "wing_native"}:
        library_id = str(adapter.options.get("wing_library", "behringer_wing")).strip()
        if not library_id:
            raise ValueError(f"device {device.id} has no wing library configured")
        return library_id
    if kind == "midi":
        library_id = str(adapter.options.get("midi_library", "")).strip()
        if not library_id:
            raise ValueError(f"device {device.id} has no midi library configured")
        return library_id
    library_id = str(adapter.options.get("osc_library", "")).strip()
    if not library_id:
        raise ValueError(f"device {device.id} has no osc library configured")
    return library_id


def _desk_library_id(adapter: AdapterConfig, adapter_name: str) -> str:
    kind = adapter.kind or adapter_name
    if kind == "wing_native":
        library_id = str(adapter.options.get("wing_library", "behringer_wing")).strip()
        if not library_id:
            raise ValueError(
                f"Wing native adapter {adapter_name} has no wing_library configured"
            )
        return library_id

    library_id = str(adapter.options.get("osc_library", "")).strip()
    if not library_id:
        raise ValueError(f"OSC adapter {adapter_name} has no osc_library configured")
    return library_id


def lookup_midi_source_ranges(
    config: AppConfig,
    adapter_name: str,
    control_id: str,
) -> tuple[float, float]:
    device = DeviceRegistry.from_config(config).device_for_adapter(adapter_name)
    adapter = config.adapters.get(adapter_name)
    if device is None or adapter is None:
        return 0.0, 127.0

    library_id = device.library.strip()
    if not library_id:
        return _default_source_ranges(device.uid, control_id)

    library = get_midi_library(library_id)
    parameter = next(
        (entry for entry in library.parameters if entry.id == control_id),
        None,
    )
    if parameter is None or parameter.value_min is None or parameter.value_max is None:
        return _default_source_ranges(adapter_name, control_id)
    return float(parameter.value_min), float(parameter.value_max)


def lookup_osc_target_ranges(
    config: AppConfig,
    adapter_name: str,
    parameter_id: str,
) -> tuple[float, float]:
    device = DeviceRegistry.from_config(config).require_device_for_adapter(adapter_name)
    adapter = config.adapters.get(adapter_name)
    if adapter is None:
        raise ValueError(f"unknown desk adapter: {adapter_name}")

    library_id = _device_library_id(device, adapter)
    library = get_osc_library(library_id)
    parameter = next(
        (entry for entry in library.parameters if entry.id == parameter_id),
        None,
    )
    if parameter is None:
        raise ValueError(
            f"unknown desk parameter {parameter_id!r} in library {library_id!r}"
        )
    return float(parameter.value_min), float(parameter.value_max)


def _default_source_ranges(adapter_name: str, control_id: str) -> tuple[float, float]:
    if adapter_name == "gpio" or control_id.startswith("pin"):
        return 0.0, 1.0
    return 0.0, 127.0


def upsert_connection(
    connections: list[ConnectionSpec],
    connection: ConnectionSpec,
) -> list[ConnectionSpec]:
    """Replace an existing connection with the same source or id, otherwise append."""

    updated = list(connections)
    if not is_disconnected_endpoint(connection.source):
        updated = [existing for existing in updated if existing.source != connection.source]
    updated = [existing for existing in updated if existing.id != connection.id]
    updated.append(connection)
    return updated


def resolve_target_datapoint(
    config: AppConfig,
    *,
    target_datapoint: str = "",
    target_adapter: str = "",
    target_parameter_id: str = "",
    device_registry: DeviceRegistry | None = None,
) -> str:
    normalized = str(target_datapoint).strip()
    if normalized:
        DataPointId.parse(normalized)
        return normalized

    adapter_name = str(target_adapter).strip()
    parameter_id = str(target_parameter_id).strip()
    if not adapter_name or not parameter_id:
        raise ValueError("target_datapoint or target_adapter and parameter_id are required")

    registry = device_registry or DeviceRegistry.from_config(config)
    device = registry.require_device_for_adapter(adapter_name)
    target_address = resolve_osc_target_address(config, device, parameter_id)
    if target_address.startswith("/"):
        return str(DataPointId(device.uid, target_address))
    return str(DataPointId(device.uid, target_address))


def lookup_datapoint_ranges(
    store: DataPointStore | None,
    point_id: str,
    *,
    fallback: tuple[float, float] = (0.0, 127.0),
) -> tuple[float, float]:
    if store is None:
        return fallback
    spec = store.spec(point_id)
    if spec is None or spec.value_min is None or spec.value_max is None:
        return fallback
    return float(spec.value_min), float(spec.value_max)


def suggest_feedback_target(
    forward_source: str,
    forward_target: str,
    store: DataPointStore | None = None,
) -> str:
    """Pick a display/output data point for the return path of a mapping."""

    del forward_target
    source_module, _, source_point = forward_source.partition(".")
    if source_point.endswith("_turn"):
        base = source_point.removesuffix("_turn")
        for suffix in ("_value", "_led_ring"):
            candidate = f"{source_module}.{base}{suffix}"
            if store is None or store.spec(candidate) is not None:
                return candidate
    return forward_source


def reverse_connection(
    connection: ConnectionSpec,
    store: DataPointStore | None = None,
    *,
    connection_id: str | None = None,
) -> ConnectionSpec:
    """Build a feedback mapping by swapping endpoints and range roles."""

    feedback_target = suggest_feedback_target(
        connection.source,
        connection.target,
        store,
    )
    resolved_id = connection_id or make_mapping_id(
        f"{connection.id}-feedback",
        feedback_target,
    )
    if resolved_id == connection.id:
        resolved_id = f"{connection.id}-feedback"
    return ConnectionSpec(
        id=resolved_id,
        source=connection.target,
        target=feedback_target,
        modifier=connection.modifier,
        input_min=connection.output_min,
        input_max=connection.output_max,
        output_min=connection.input_min,
        output_max=connection.input_max,
        invert=connection.invert,
        scale_curve=connection.scale_curve,
        factor=connection.factor,
    )
