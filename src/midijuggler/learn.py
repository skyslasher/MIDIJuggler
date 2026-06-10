"""Interactive mapping learn mode."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from midijuggler.config import AdapterConfig, AppConfig
from midijuggler.mapping import MappingRule
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
    message: str = ""

    def as_dict(self) -> dict[str, str | bool | None]:
        return {
            "enabled": self.enabled,
            "phase": self.phase,
            "source": None if self.source is None else self.source.key,
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
                message="Click a monitor message to select the mapping source.",
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
            message="Click a monitor message to select the mapping source.",
        )
        return self._state

    def select_source(self, source: LearnSource) -> LearnState:
        if not self._state.enabled:
            raise ValueError("learn mode is disabled")

        self._state = LearnState(
            enabled=True,
            phase="waiting_target",
            source=source,
            message=f"Source selected: {source.key}. Select an OSC target.",
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
    ) -> MappingRule:
        target_address = resolve_osc_target_address(
            config,
            target_adapter,
            target_parameter_id,
        )
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
        rule_id = mapping_id or make_mapping_id(source.key, f"{target_adapter}:{target_address}")
        return MappingRule(
            id=rule_id,
            source=source.key,
            target=f"{target_adapter}:{target_address}",
            input_min=input_min,
            input_max=input_max,
            output_min=output_min,
            output_max=output_max,
            invert=False,
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
            build_midi_source_index_for_adapter(adapter),
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

    raise ValueError(f"unsupported monitor event kind: {kind!r}")


def build_midi_source_index_for_adapter(adapter: AdapterConfig) -> MidiSourceIndex | None:
    library_id = str(adapter.options.get("midi_library", "")).strip()
    if not library_id:
        return None

    try:
        library = get_midi_library(library_id)
    except KeyError:
        return None

    return build_source_index(library, resolve_library_port(adapter))


def make_mapping_id(source: str, target: str) -> str:
    def slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")

    candidate = f"learn-{slug(source)}-to-{slug(target)}"
    return candidate[:120]


def resolve_osc_target_address(
    config: AppConfig,
    adapter_name: str,
    parameter_id: str,
) -> str:
    adapter = config.adapters.get(adapter_name)
    if adapter is None:
        raise ValueError(f"unknown OSC adapter: {adapter_name}")

    library_id = str(adapter.options.get("osc_library", "")).strip()
    if not library_id:
        raise ValueError(f"OSC adapter {adapter_name} has no osc_library configured")

    library = get_osc_library(library_id)
    parameter = next(
        (entry for entry in library.parameters if entry.id == parameter_id),
        None,
    )
    if parameter is None:
        raise ValueError(
            f"unknown OSC parameter {parameter_id!r} in library {library_id!r}"
        )
    if parameter.direction != "target":
        raise ValueError(f"OSC parameter {parameter_id!r} is not a target")

    return parameter.address


def lookup_midi_source_ranges(
    config: AppConfig,
    adapter_name: str,
    control_id: str,
) -> tuple[float, float]:
    adapter = config.adapters.get(adapter_name)
    if adapter is None:
        return 0.0, 127.0

    library_id = str(adapter.options.get("midi_library", "")).strip()
    if not library_id:
        return _default_source_ranges(adapter_name, control_id)

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
    adapter = config.adapters.get(adapter_name)
    if adapter is None:
        raise ValueError(f"unknown OSC adapter: {adapter_name}")

    library_id = str(adapter.options.get("osc_library", "")).strip()
    if not library_id:
        raise ValueError(f"OSC adapter {adapter_name} has no osc_library configured")

    library = get_osc_library(library_id)
    parameter = next(
        (entry for entry in library.parameters if entry.id == parameter_id),
        None,
    )
    if parameter is None:
        raise ValueError(
            f"unknown OSC parameter {parameter_id!r} in library {library_id!r}"
        )
    return float(parameter.value_min), float(parameter.value_max)


def _default_source_ranges(adapter_name: str, control_id: str) -> tuple[float, float]:
    if adapter_name == "gpio" or control_id.startswith("pin"):
        return 0.0, 1.0
    return 0.0, 127.0


def upsert_mapping_rule(
    mappings: list[MappingRule],
    rule: MappingRule,
) -> list[MappingRule]:
    """Replace an existing rule with the same source or id, otherwise append."""

    updated = [existing for existing in mappings if existing.source != rule.source]
    updated = [existing for existing in updated if existing.id != rule.id]
    updated.append(rule)
    return updated
