"""Build and push rotary display device configuration over USB serial."""

from __future__ import annotations

import hashlib
import time
from typing import Any

from midijuggler.config import RotaryDisplayDeviceConfig


def device_config_fingerprint(device: RotaryDisplayDeviceConfig) -> str:
    commands = build_device_config_commands(device)
    return hashlib.sha256("\n".join(commands).encode("utf-8")).hexdigest()


def build_device_config_commands(device: RotaryDisplayDeviceConfig) -> list[str]:
    commands = [
        f"transport {device.transport}",
        f"wifi_enabled {'on' if device.wifi_enabled else 'off'}",
    ]
    if device.wifi_ssid:
        commands.append(f"wifi ssid {device.wifi_ssid}")
    if device.wifi_pass:
        commands.append(f"wifi pass {device.wifi_pass}")
    if not device.wifi_ssid and not device.wifi_pass:
        commands.append("wifi clear")
    commands.extend(
        [
            f"host {device.host}",
            f"port {device.port}",
            f"listen_port {device.listen_port}",
        ]
    )
    return commands


def _is_config_push_noise(line: str) -> bool:
    if not line:
        return True
    if line in {"start_stop", "click_toggle", "tap_tempo"}:
        return True
    noise_prefixes = (
        "hello",
        "sync ",
        "beat ",
        "bpm ",
        "cfg ",
        "wifi:",
        "display:",
        "renderHome:",
        "MIDIJuggler",
        "init ",
        "ready",
    )
    return any(line.startswith(prefix) for prefix in noise_prefixes)


def read_config_response_lines(port: Any, *, timeout_s: float = 3.0) -> list[str]:
    deadline = time.monotonic() + timeout_s
    lines: list[str] = []
    while time.monotonic() < deadline:
        raw = port.readline()
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if _is_config_push_noise(line):
            continue
        lines.append(line)
        if line == "ok" or line.startswith("err "):
            break
    return lines


def push_device_config_sync(port: Any, commands: list[str], *, timeout_s: float = 3.0) -> dict[str, Any]:
    responses: list[str] = []
    failed_command = ""
    try:
        reset_input_buffer = getattr(port, "reset_input_buffer", None)
        if callable(reset_input_buffer):
            reset_input_buffer()
        for command in commands:
            port.write((command + "\n").encode("utf-8"))
            flush = getattr(port, "flush", None)
            if callable(flush):
                flush()
            lines = read_config_response_lines(port, timeout_s=timeout_s)
            responses.extend(lines)
            if any(line.startswith("err ") for line in lines):
                failed_command = command
                return {
                    "ok": False,
                    "responses": responses,
                    "failed_command": failed_command,
                    "reason": "device error",
                }
            if "ok" not in lines:
                failed_command = command
                return {
                    "ok": False,
                    "responses": responses,
                    "failed_command": failed_command,
                    "reason": "timeout waiting for ok",
                }
        port.write(b"config apply\n")
        flush = getattr(port, "flush", None)
        if callable(flush):
            flush()
        lines = read_config_response_lines(port, timeout_s=max(timeout_s, 5.0))
        responses.extend(lines)
        if any(line.startswith("err ") for line in lines):
            failed_command = "config apply"
            return {
                "ok": False,
                "responses": responses,
                "failed_command": failed_command,
                "reason": "device error",
            }
        ok = "ok" in lines
        return {
            "ok": ok,
            "responses": responses,
            "failed_command": "" if ok else "config apply",
            "reason": "" if ok else "timeout waiting for ok",
        }
    except OSError as exc:
        return {
            "ok": False,
            "responses": responses,
            "failed_command": failed_command,
            "error": str(exc),
        }
