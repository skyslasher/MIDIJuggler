"""Default data-point connections for rotary display OSC devices."""

from __future__ import annotations

from midijuggler.datapoint.types import ConnectionSpec, ModifierKind
from midijuggler.device.types import DeviceConfig

ROTARY_DISPLAY_LIBRARY = "rotary_display"


def rotary_display_device_ids(devices: dict[str, DeviceConfig]) -> list[str]:
    return [
        device.uid
        for device in devices.values()
        if str(device.library or "").strip() == ROTARY_DISPLAY_LIBRARY
    ]


def rotary_encoder_to_clock_connections(device_id: str) -> list[ConnectionSpec]:
    """Map encoder OSC commands on a rotary_display device to clock inputs."""

    return [
        ConnectionSpec(
            id=f"{device_id}-bpm-to-clock",
            source=f"{device_id}./midijuggler/clock/bpm",
            target="clock.bpm_set",
            modifier=ModifierKind.PASSTHROUGH,
        ),
        ConnectionSpec(
            id=f"{device_id}-start-stop-to-clock",
            source=f"{device_id}./midijuggler/clock/start_stop",
            target="clock.start_stop",
            modifier=ModifierKind.PASSTHROUGH,
        ),
        ConnectionSpec(
            id=f"{device_id}-click-toggle-to-clock",
            source=f"{device_id}./midijuggler/clock/click_toggle",
            target="clock.click_toggle",
            modifier=ModifierKind.PASSTHROUGH,
        ),
        ConnectionSpec(
            id=f"{device_id}-tap-tempo-to-clock",
            source=f"{device_id}./midijuggler/clock/tap_tempo",
            target="clock.tap_tempo",
            modifier=ModifierKind.PASSTHROUGH,
        ),
    ]


def rotary_clock_feedback_connections(device_id: str) -> list[ConnectionSpec]:
    """Map master clock feedback to the rotary display OSC targets."""

    return [
        ConnectionSpec(
            id=f"clock-beat-to-{device_id}",
            source="clock.beat",
            target=f"{device_id}./midijuggler/rotary/beat",
            modifier=ModifierKind.PASSTHROUGH,
        ),
    ]


def merge_rotary_display_connections(
    connections: list[ConnectionSpec],
    devices: dict[str, DeviceConfig],
    *,
    include_feedback: bool = True,
) -> list[ConnectionSpec]:
    """Append default rotary encoder connections for configured devices."""

    existing_pairs = {(connection.source, connection.target) for connection in connections}
    merged = list(connections)
    for device_id in rotary_display_device_ids(devices):
        defaults = rotary_encoder_to_clock_connections(device_id)
        if include_feedback:
            defaults.extend(rotary_clock_feedback_connections(device_id))
        for connection in defaults:
            key = (connection.source, connection.target)
            if key in existing_pairs:
                continue
            merged.append(connection)
            existing_pairs.add(key)
    return merged
