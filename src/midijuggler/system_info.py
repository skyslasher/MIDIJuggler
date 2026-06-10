"""Small host discovery helpers for the web configuration UI."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess


def parse_aplay_devices(output: str) -> list[dict[str, str]]:
    devices: list[dict[str, str]] = [
        {"id": "", "label": "default (software/mixed)", "mode": "alias"},
    ]
    pattern = re.compile(
        r"card\s+(?P<card>\d+):\s*(?P<card_name>[^\[]+).*"
        r"device\s+(?P<device>\d+):\s*(?P<device_name>[^\[]+)"
    )
    for line in output.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        card = match.group("card")
        device = match.group("device")
        card_name = match.group("card_name").strip()
        device_name = match.group("device_name").strip()
        devices.append(
            {
                "id": f"plughw:{card},{device}",
                "label": f"{card_name} / {device_name} (plughw:{card},{device})",
                "mode": "dmix",
            }
        )
    return devices


def list_alsa_output_devices() -> list[dict[str, str]]:
    try:
        result = subprocess.run(
            ["aplay", "-l"],
            capture_output=True,
            check=False,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [{"id": "", "label": "default (software/mixed)", "mode": "alias"}]
    return parse_aplay_devices(result.stdout)


_IGNORED_MIDI_CLIENTS = {"System", "Midi Through"}


def parse_aconnect_ports(output: str) -> list[dict[str, str]]:
    ports: list[dict[str, str]] = []
    seen: set[str] = set()
    current_client = ""
    client_pattern = re.compile(r"client \d+: '([^']+)'")
    port_pattern = re.compile(r"\d+ '([^']+)'")

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        client_match = client_pattern.match(line)
        if client_match:
            current_client = client_match.group(1)
            continue

        port_match = port_pattern.match(line)
        if not port_match or not current_client or current_client in _IGNORED_MIDI_CLIENTS:
            continue

        port_name = port_match.group(1)
        if port_name in seen:
            continue
        seen.add(port_name)
        ports.append(
            {
                "id": port_name,
                "label": f"{current_client} / {port_name}",
                "client": current_client,
            }
        )

    return ports


def list_midi_ports() -> list[dict[str, str]]:
    try:
        result = subprocess.run(
            ["aconnect", "-l"],
            capture_output=True,
            check=False,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_aconnect_ports(result.stdout)


def list_click_wavs(directory: str | Path = "/etc/midijuggler") -> list[dict[str, str]]:
    wav_dir = Path(directory)
    try:
        files = sorted(
            path
            for path in wav_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".wav"
        )
    except OSError:
        return []
    return [{"path": str(path), "label": path.name} for path in files]
