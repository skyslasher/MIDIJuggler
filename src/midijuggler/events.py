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
class GpioEvent(Event):
    """GPIO input transition or initial state."""

    pin: int = 0
    control: str = ""
    value: float = 0.0
    initial: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload = super().as_dict()
        payload.update(
            {
                "pin": self.pin,
                "control": self.control,
                "value": self.value,
                "initial": self.initial,
            }
        )
        return payload


@dataclass(frozen=True)
class MidiClockEvent(Event):
    """MIDI timing clock tick, typically status byte 0xF8 at 24 PPQN."""

    def as_dict(self) -> dict[str, Any]:
        return super().as_dict()


@dataclass(frozen=True)
class MidiMessageEvent(Event):
    """Raw-ish MIDI message exchanged with MIDI-capable adapters."""

    status: int = 0
    data: tuple[int, ...] = ()
    target: str = ""
    direction: str = "input"

    def as_dict(self) -> dict[str, Any]:
        payload = super().as_dict()
        payload.update(
            {
                "status": self.status,
                "data": list(self.data),
                "target": self.target,
                "direction": self.direction,
            }
        )
        return payload


@dataclass(frozen=True)
class OscMessageEvent(Event):
    """OSC message exchanged with OSC-capable adapters."""

    address: str = ""
    arguments: tuple[Any, ...] = ()
    target: str = ""
    direction: str = "input"

    def as_dict(self) -> dict[str, Any]:
        payload = super().as_dict()
        payload.update(
            {
                "address": self.address,
                "arguments": list(self.arguments),
                "target": self.target,
                "direction": self.direction,
            }
        )
        return payload


@dataclass(frozen=True)
class MasterClockCommandEvent(Event):
    """Control command for the MIDI master clock."""

    command: str = ""
    value: Any = None

    def as_dict(self) -> dict[str, Any]:
        payload = super().as_dict()
        payload.update({"command": self.command, "value": self.value})
        return payload


@dataclass(frozen=True)
class MasterClockStateEvent(Event):
    """Published when master clock state changes."""

    bpm: float = 0.0
    running: bool = False
    position_ticks: int = 0
    click_interval: str = "quarter"

    def as_dict(self) -> dict[str, Any]:
        payload = super().as_dict()
        payload.update(
            {
                "bpm": self.bpm,
                "running": self.running,
                "position_ticks": self.position_ticks,
                "click_interval": self.click_interval,
            }
        )
        return payload


@dataclass(frozen=True)
class ClickEvent(Event):
    """Published when the master clock triggers an audio click."""

    interval: str = "quarter"
    position_ticks: int = 0

    def as_dict(self) -> dict[str, Any]:
        payload = super().as_dict()
        payload.update({"interval": self.interval, "position_ticks": self.position_ticks})
        return payload


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
    connection_phase: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = super().as_dict()
        payload.update(
            {
                "adapter": self.adapter,
                "status": self.status,
                "detail": self.detail,
                "connection_phase": self.connection_phase,
            }
        )
        return payload
