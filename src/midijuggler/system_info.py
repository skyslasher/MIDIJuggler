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
_ADDRESS_PATTERN = re.compile(r"^\d+:\d+$")


def parse_aconnect_ports(output: str) -> list[dict[str, str]]:
    ports: list[dict[str, str]] = []
    seen: set[str] = set()
    current_client = ""
    current_client_id = ""
    client_pattern = re.compile(r"client (\d+): '([^']+)'")
    port_pattern = re.compile(r"(\d+) '([^']+)'")

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        client_match = client_pattern.match(line)
        if client_match:
            current_client_id = client_match.group(1)
            current_client = client_match.group(2)
            continue

        port_match = port_pattern.match(line)
        if not port_match or not current_client or current_client in _IGNORED_MIDI_CLIENTS:
            continue

        port_index = port_match.group(1)
        port_name = port_match.group(2).strip()
        address = f"{current_client_id}:{port_index}"
        if address in seen:
            continue
        seen.add(address)
        ports.append(
            {
                "id": port_name,
                "address": address,
                "label": f"{current_client} / {port_name} ({address})",
                "client": current_client,
            }
        )

    return ports


def _resolve_port_address(port_name: str, ports: list[dict[str, str]]) -> str | None:
    normalized = port_name.strip()
    if not normalized:
        return None

    if _ADDRESS_PATTERN.match(normalized):
        if any(port["address"] == normalized for port in ports):
            return normalized
        return None

    matches = [port for port in ports if port["id"] == normalized]
    if len(matches) == 1:
        return matches[0]["address"]
    if len(matches) > 1:
        return matches[0]["address"]
    return None


def resolve_midi_input_port_address(port_name: str) -> str | None:
    """Resolve a configured readable ALSA port label to a client:port address."""

    return _resolve_port_address(port_name, list_midi_input_ports())


def resolve_midi_output_port_address(port_name: str) -> str | None:
    """Resolve a configured writable ALSA port label to a client:port address."""

    return _resolve_port_address(port_name, list_midi_output_ports())


def resolve_midi_port_address(port_name: str) -> str | None:
    """Resolve a configured ALSA port label to a client:port address."""

    return resolve_midi_output_port_address(port_name) or resolve_midi_input_port_address(
        port_name
    )


def _aconnect_list(*args: str) -> str:
    try:
        result = subprocess.run(
            ["aconnect", *args],
            capture_output=True,
            check=False,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout


def list_midi_input_ports() -> list[dict[str, str]]:
    """List readable ALSA sequencer ports suitable for MIDI input."""

    return parse_aconnect_ports(_aconnect_list("-i"))


def list_midi_output_ports() -> list[dict[str, str]]:
    """List writable ALSA sequencer ports suitable for MIDI output."""

    return parse_aconnect_ports(_aconnect_list("-o"))


def list_midi_ports() -> list[dict[str, str]]:
    """List all ALSA sequencer ports with their current connection status."""

    return parse_aconnect_ports(_aconnect_list("-l"))


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
