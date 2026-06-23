"""Small host discovery helpers for the web configuration UI."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess

from midijuggler.alsa import alsa_stable_device_id


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
        stable_id = alsa_stable_device_id(card_name, device)
        resolved_device = f"plughw:{card},{device}"
        devices.append(
            {
                "id": stable_id,
                "resolved_device": resolved_device,
                "card_number": card,
                "device_index": device,
                "card_name": card_name,
                "device_name": device_name,
                "label": (
                    f"{card_name} / {device_name} "
                    f"({stable_id}, current {resolved_device})"
                ),
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


def _port_open_name(port: dict[str, str]) -> str:
    return port.get("mido_name") or port["address"]


def is_midi_port_address(port_name: str) -> bool:
    return bool(_ADDRESS_PATTERN.match(port_name.strip()))


def lookup_midi_port(
    port_name: str,
    *,
    inputs: bool,
    ports: list[dict[str, str]] | None = None,
) -> dict[str, str] | None:
    listed = list_midi_input_ports() if inputs else list_midi_output_ports()
    if ports is not None:
        listed = ports
    normalized = port_name.strip()
    if not normalized:
        return None

    if is_midi_port_address(normalized):
        for port in listed:
            if port["address"] == normalized or port.get("mido_name") == normalized:
                return port

    matches = _find_port_matches(normalized, listed)
    return _pick_preferred_port(matches)


def normalize_midi_port_id(
    port_name: str,
    *,
    inputs: bool,
    ports: list[dict[str, str]] | None = None,
) -> str:
    """Prefer stable MIDI port names and migrate legacy client:port addresses."""

    normalized = port_name.strip()
    if not normalized:
        return ""

    if is_midi_port_address(normalized):
        matched = lookup_midi_port(normalized, inputs=inputs, ports=ports)
        if matched is not None:
            return matched["id"]

    return normalized


def enrich_midi_port_choice(port: dict[str, str]) -> dict[str, str]:
    return {
        **port,
        "resolved_address": port.get("address", ""),
    }


def _find_port_matches(port_name: str, ports: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized = port_name.strip()
    if not normalized:
        return []

    normalized_key = normalized.casefold()

    if _ADDRESS_PATTERN.match(normalized):
        return [
            port
            for port in ports
            if port["address"] == normalized or port.get("mido_name") == normalized
        ]

    exact = [port for port in ports if port["id"].casefold() == normalized_key]
    if exact:
        return exact

    return [
        port
        for port in ports
        if normalized_key in port.get("mido_name", port["id"]).casefold()
        or normalized_key in port["id"].casefold()
        or normalized_key in port.get("label", "").casefold()
    ]


def _input_client_id(input_port_name: str | None) -> tuple[str | None, str | None]:
    if not input_port_name or not input_port_name.strip():
        return None, None

    matches = _find_port_matches(input_port_name.strip(), list_midi_input_ports())
    if matches:
        port = matches[0]
        address = _port_open_name(port)
        if _ADDRESS_PATTERN.match(address):
            client_id, _, port_index = address.partition(":")
            return client_id or None, port_index or None
        return port.get("client") or None, None

    input_address = resolve_midi_input_port_address(input_port_name)
    if input_address is None:
        return None, None

    if _ADDRESS_PATTERN.match(input_address):
        client_id, _, port_index = input_address.partition(":")
        return client_id or None, port_index or None
    return input_address.split()[0] if " " in input_address else input_address, None


def _ports_on_client(
    ports: list[dict[str, str]],
    client_id: str,
) -> list[dict[str, str]]:
    prefix = f"{client_id}:"
    same_address_prefix = [port for port in ports if port["address"].startswith(prefix)]
    if same_address_prefix:
        return same_address_prefix
    return [
        port
        for port in ports
        if port.get("client") == client_id
        or _port_open_name(port).startswith(f"{client_id} ")
    ]


def _pick_output_on_client(
    ports: list[dict[str, str]],
    *,
    preferred_name: str = "",
    input_port_index: str | None = None,
    input_address: str | None = None,
) -> dict[str, str] | None:
    if not ports:
        return None

    candidates = list(ports)
    if input_address and len(candidates) > 1:
        without_input = [
            port
            for port in candidates
            if _port_open_name(port) != input_address and port["address"] != input_address
        ]
        if without_input:
            candidates = without_input

    if preferred_name:
        named = [port for port in candidates if port["id"] == preferred_name]
        if len(named) == 1:
            return named[0]

    if input_port_index is not None and len(candidates) > 1:
        different_index = [
            port
            for port in candidates
            if port["address"].split(":", 1)[1] != input_port_index
        ]
        if different_index:
            candidates = different_index

    if len(candidates) == 1:
        return candidates[0]

    non_app = [
        port
        for port in candidates
        if "midijuggler" not in port["client"].casefold()
    ]
    if len(non_app) == 1:
        return non_app[0]
    if non_app:
        return non_app[0]

    return candidates[0]


def _pick_preferred_port(
    matches: list[dict[str, str]],
    *,
    input_client_id: str | None = None,
) -> dict[str, str] | None:
    if not matches:
        return None

    if input_client_id:
        same_client = _ports_on_client(matches, input_client_id)
        if same_client:
            return same_client[0]

    non_app = [
        port
        for port in matches
        if "midijuggler" not in port["client"].casefold()
    ]
    if non_app:
        return non_app[0]

    return matches[0]


def _resolve_port_address(
    port_name: str,
    ports: list[dict[str, str]],
    *,
    input_client_id: str | None = None,
) -> str | None:
    matches = _find_port_matches(port_name, ports)
    preferred = _pick_preferred_port(matches, input_client_id=input_client_id)
    if preferred is None:
        return None
    return _port_open_name(preferred)


def resolve_midi_input_port_address(port_name: str) -> str | None:
    """Resolve a configured MIDI input port label to a backend open name."""

    return _resolve_port_address(port_name, list_midi_input_ports())


def resolve_midi_output_port_address(
    port_name: str,
    *,
    input_port_name: str | None = None,
) -> str | None:
    """Resolve a configured writable MIDI port label to a backend open name."""

    output_ports = list_midi_output_ports()
    input_client_id, input_port_index = _input_client_id(input_port_name)
    input_address = (
        resolve_midi_input_port_address(input_port_name)
        if input_port_name and input_port_name.strip()
        else None
    )
    normalized_output = port_name.strip()

    if input_client_id:
        same_client_ports = _ports_on_client(output_ports, input_client_id)
        preferred = _pick_output_on_client(
            same_client_ports,
            preferred_name=normalized_output,
            input_port_index=input_port_index,
            input_address=input_address,
        )
        if preferred is not None:
            return preferred["address"]

    if normalized_output:
        address = _resolve_port_address(
            normalized_output,
            output_ports,
            input_client_id=input_client_id,
        )
        if address is not None and (
            input_client_id is None
            or address.startswith(f"{input_client_id}:")
            or address.startswith(f"{input_client_id} ")
        ):
            return address

    if input_port_name and input_port_name.strip():
        address = _resolve_port_address(
            input_port_name,
            output_ports,
            input_client_id=input_client_id,
        )
        if address is not None:
            return address

    return None


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


def _list_mido_ports(*, inputs: bool) -> list[dict[str, str]] | None:
    try:
        from midijuggler.midi.mido_io import list_mido_port_entries, mido_available
    except ImportError:
        return None
    if not mido_available():
        return None
    return list_mido_port_entries(inputs=inputs)


def list_midi_input_ports() -> list[dict[str, str]]:
    """List readable MIDI input ports."""

    mido_ports = _list_mido_ports(inputs=True)
    if mido_ports:
        return mido_ports
    return parse_aconnect_ports(_aconnect_list("-i"))


def list_midi_output_ports() -> list[dict[str, str]]:
    """List writable MIDI output ports."""

    mido_ports = _list_mido_ports(inputs=False)
    if mido_ports:
        return mido_ports
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
