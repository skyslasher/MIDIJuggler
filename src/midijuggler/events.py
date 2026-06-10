"""Typed events exchanged inside MIDIJuggler."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any


@dataclass(frozen=True)
class Event:
    """Base event with a monotonic timestamp."""

    source: str
    timestamp: float = field(default_factory=monotonic)

    @property
    def kind(self) -> str:
        return self.__class__.__name__

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source": self.source,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class ControlEvent(Event):
    """Normalized continuous or switch-like input value."""

    control: str = ""
    value: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        payload = super().as_dict()
        payload.update({"control": self.control, "value": self.value})
        return payload


@dataclass(frozen=True)
class MidiClockEvent(Event):
    """MIDI timing clock tick, typically status byte 0xF8 at 24 PPQN."""

    def as_dict(self) -> dict[str, Any]:
        return super().as_dict()


@dataclass(frozen=True)
class BpmChangedEvent(Event):
    """Published when the MIDI clock tracker has a new BPM estimate."""

    bpm: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        payload = super().as_dict()
        payload.update({"bpm": self.bpm})
        return payload


@dataclass(frozen=True)
class MappedEvent(Event):
    """Output event produced by a mapping rule."""

    mapping_id: str = ""
    target: str = ""
    value: float = 0.0
    original: ControlEvent | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = super().as_dict()
        payload.update(
            {
                "mapping_id": self.mapping_id,
                "target": self.target,
                "value": self.value,
                "original": self.original.as_dict() if self.original else None,
            }
        )
        return payload


@dataclass(frozen=True)
class AdapterStatusEvent(Event):
    """Lifecycle status from an adapter."""

    adapter: str = ""
    status: str = ""
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = super().as_dict()
        payload.update(
            {"adapter": self.adapter, "status": self.status, "detail": self.detail}
        )
        return payload
