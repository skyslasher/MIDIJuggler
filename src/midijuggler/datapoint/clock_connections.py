"""Default master-clock output connections for data-point routing."""

from __future__ import annotations

import logging

from midijuggler.config import AdapterConfig
from midijuggler.datapoint.types import ConnectionSpec, ModifierKind

LOGGER = logging.getLogger(__name__)

CLOCK_MIDI_OUTPUT_POINTS = (
    "midi_tick",
    "midi_start",
    "midi_continue",
    "midi_stop",
)


def adapter_has_midi_output_port(adapter: AdapterConfig) -> bool:
    kind = adapter.kind or ""
    if kind not in {"midi", "rtp_midi"}:
        return False
    if not adapter.enabled:
        return False
    output_port = str(adapter.options.get("output_port", "")).strip()
    input_port = str(adapter.options.get("input_port", "")).strip()
    return bool(output_port or input_port)


def usable_clock_output_targets(
    configured_targets: list[str],
    adapters: dict[str, AdapterConfig],
) -> list[str]:
    routable = {
        name
        for name, adapter in adapters.items()
        if adapter_has_midi_output_port(adapter)
    }
    usable = [target for target in configured_targets if target in routable]
    dropped = [target for target in configured_targets if target not in routable]
    if dropped:
        LOGGER.warning(
            "ignoring master clock output targets without configured MIDI ports: %s",
            ", ".join(dropped),
        )
    return usable


def clock_output_connections(output_targets: list[str]) -> list[ConnectionSpec]:
    connections: list[ConnectionSpec] = []
    for adapter_name in output_targets:
        for point in CLOCK_MIDI_OUTPUT_POINTS:
            label = point.removeprefix("midi_").replace("_", "-")
            connections.append(
                ConnectionSpec(
                    id=f"clock-{label}-to-{adapter_name}",
                    source=f"clock.{point}",
                    target=f"{adapter_name}.midi_out",
                    modifier=ModifierKind.PASSTHROUGH,
                )
            )
    return connections


def merge_clock_output_connections(
    connections: list[ConnectionSpec],
    output_targets: list[str],
) -> list[ConnectionSpec]:
    if not output_targets:
        return list(connections)

    existing_pairs = {(connection.source, connection.target) for connection in connections}
    merged = list(connections)
    for connection in clock_output_connections(output_targets):
        key = (connection.source, connection.target)
        if key in existing_pairs:
            continue
        merged.append(connection)
        existing_pairs.add(key)
    return merged
