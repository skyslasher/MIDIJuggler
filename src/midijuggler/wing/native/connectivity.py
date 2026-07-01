"""Runtime connectivity state for Wing native adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any


def _age_seconds(timestamp: float | None) -> float | None:
    if timestamp is None:
        return None
    return max(0.0, monotonic() - timestamp)


@dataclass
class WingNativeConnectivity:
    connection_phase: str = "stopped"
    connected: bool = False
    remote_host: str = ""
    native_port: int = 2222
    last_error: str = ""
    last_error_at: float | None = None
    last_feedback_at: float | None = None
    last_feedback_path: str = ""
    last_feedback_value: float | None = None
    last_keepalive_at: float | None = None
    last_send_at: float | None = None
    connected_at: float | None = None
    paths_cached: int = 0
    paths_warmup_failed: int = 0

    def note_error(self, message: str) -> None:
        self.last_error = message.strip()
        self.last_error_at = monotonic()
        self.connected = False
        self.connection_phase = "error"

    def note_connected(self, host: str, port: int) -> None:
        now = monotonic()
        self.connection_phase = "connected"
        self.connected = True
        self.remote_host = host
        self.native_port = port
        self.connected_at = now
        self.last_error = ""
        self.last_error_at = None

    def note_stopped(self) -> None:
        self.connection_phase = "stopped"
        self.connected = False

    def note_connecting(self, host: str, port: int) -> None:
        self.connection_phase = "connecting"
        self.connected = False
        self.remote_host = host
        self.native_port = port

    def note_waiting(self, host: str, port: int) -> None:
        self.connection_phase = "waiting"
        self.connected = False
        self.remote_host = host
        self.native_port = port

    def note_feedback(self, path: str, value: float) -> None:
        self.last_feedback_at = monotonic()
        self.last_feedback_path = path
        self.last_feedback_value = value

    def note_keepalive(self) -> None:
        self.last_keepalive_at = monotonic()

    def note_send(self) -> None:
        self.last_send_at = monotonic()

    def as_dict(self) -> dict[str, Any]:
        return {
            "connection_phase": self.connection_phase,
            "connected": self.connected,
            "remote_host": self.remote_host,
            "native_port": self.native_port,
            "last_error": self.last_error,
            "last_error_age_s": _age_seconds(self.last_error_at),
            "last_feedback_path": self.last_feedback_path,
            "last_feedback_value": self.last_feedback_value,
            "last_feedback_age_s": _age_seconds(self.last_feedback_at),
            "last_keepalive_age_s": _age_seconds(self.last_keepalive_at),
            "last_send_age_s": _age_seconds(self.last_send_at),
            "connected_age_s": _age_seconds(self.connected_at),
            "paths_cached": self.paths_cached,
            "paths_warmup_failed": self.paths_warmup_failed,
        }
