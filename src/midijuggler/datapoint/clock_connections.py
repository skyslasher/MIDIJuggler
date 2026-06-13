"""Default master-clock output connections for data-point routing."""

from __future__ import annotations

from midijuggler.datapoint.types import ConnectionSpec, ModifierKind

CLOCK_MIDI_OUTPUT_POINTS = (
    "midi_tick",
    "midi_start",
    "midi_continue",
    "midi_stop",
)


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
