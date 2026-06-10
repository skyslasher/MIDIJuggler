"""Mapping engine with linear scaling and optional inversion."""

from __future__ import annotations

from dataclasses import dataclass

from midijuggler.events import ControlEvent, MappedEvent


@dataclass(frozen=True)
class MappingRule:
    """Declarative mapping from one normalized source to an output target."""

    id: str
    source: str
    target: str
    input_min: float = 0.0
    input_max: float = 1.0
    output_min: float = 0.0
    output_max: float = 127.0
    invert: bool = False

    def __post_init__(self) -> None:
        if self.input_min == self.input_max:
            raise ValueError(f"mapping {self.id!r} has an empty input range")

    def matches(self, event: ControlEvent) -> bool:
        return f"{event.source}:{event.control}" == self.source

    def apply(self, value: float) -> float:
        """Scale input linearly into the output range and clamp to bounds."""

        clamped = min(max(value, self.input_min), self.input_max)
        position = (clamped - self.input_min) / (self.input_max - self.input_min)
        if self.invert:
            position = 1.0 - position
        return self.output_min + position * (self.output_max - self.output_min)


class MappingEngine:
    """Apply all matching mapping rules to incoming control events."""

    def __init__(self, rules: list[MappingRule]) -> None:
        self._rules = list(rules)

    @property
    def rules(self) -> tuple[MappingRule, ...]:
        return tuple(self._rules)

    def replace_rules(self, rules: list[MappingRule]) -> None:
        self._rules = list(rules)

    def map_event(self, event: ControlEvent) -> list[MappedEvent]:
        return [
            MappedEvent(
                source="mapping",
                mapping_id=rule.id,
                target=rule.target,
                value=rule.apply(event.value),
                original=event,
            )
            for rule in self._rules
            if rule.matches(event)
        ]
