"""Interactive mapping learn mode."""

from __future__ import annotations

import re
from dataclasses import dataclass

from midijuggler.config import AppConfig
from midijuggler.events import ControlEvent
from midijuggler.mapping import MappingRule
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
                message="Move a control on your MIDI or GPIO device. Learn listens for ControlEvent or MIDI input.",
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
            message="Move a control on your MIDI or GPIO device.",
        )
        return self._state

    def capture(self, event: ControlEvent) -> LearnState | None:
        if not self._state.enabled or self._state.phase != "waiting_source":
            return None
        if event.source in {"clock", "mapping"}:
            return None

        source = LearnSource(adapter=event.source, control=event.control)
        self._state = LearnState(
            enabled=True,
            phase="waiting_target",
            source=source,
            message=f"Source captured: {source.key}. Select an OSC target.",
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
