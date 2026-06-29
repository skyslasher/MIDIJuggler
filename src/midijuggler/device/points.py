"""Build data-point specs for configured devices."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from midijuggler.adapters.gpio import GpioAdapter
    from midijuggler.adapters.hid import HidAdapter
    from midijuggler.config import AdapterConfig
from midijuggler.device.registry import DeviceRegistry
from midijuggler.device.types import CustomPointSpec, DeviceConfig
from midijuggler.datapoint.types import (
    DataPointDirection,
    DataPointId,
    DataPointSpec,
    ValueType,
)
from midijuggler.midi.library_match import resolve_library_port
from midijuggler.midi_library import get_midi_library
from midijuggler.osc_library import get_osc_library

MIDI_OUT_POINT = "midi_out"

_DIRECTION_MAP = {
    "input": DataPointDirection.INPUT,
    "output": DataPointDirection.OUTPUT,
    "bidirectional": DataPointDirection.BIDIRECTIONAL,
    "source": DataPointDirection.INPUT,
    "target": DataPointDirection.OUTPUT,
}


def _optional_library_range(value: float | None) -> float | None:
    if value is None:
        return None
    return float(value)


def build_device_datapoints(
    device: DeviceConfig,
    adapter: AdapterConfig,
    *,
    gpio_adapter: GpioAdapter | None = None,
    hid_adapter: HidAdapter | None = None,
) -> tuple[list[DataPointSpec], set[str]]:
    """Return specs and the set of writable point ids for a device."""

    specs: list[DataPointSpec] = []
    output_points: set[str] = set()
    kind = _resolved_kind(device, adapter)

    if kind == "midi":
        _append_midi_library_points(device, adapter, specs, output_points)
        specs.append(_midi_out_spec(device.uid))
    elif kind in {"osc", "wing"}:
        _append_osc_library_points(device, kind, specs, output_points)
    elif kind == "gpio":
        _append_gpio_points(device, gpio_adapter, specs)
    elif kind == "hid":
        _append_hid_points(device, hid_adapter, specs)

    for point in device.custom_points:
        spec = _custom_point_spec(device.uid, point)
        specs.append(spec)
        if spec.direction in {
            DataPointDirection.OUTPUT,
            DataPointDirection.BIDIRECTIONAL,
        }:
            output_points.add(point.id)

    return specs, output_points


def _resolved_kind(device: DeviceConfig, adapter: AdapterConfig) -> str:
    if device.library_kind:
        kind = device.library_kind
    else:
        kind = adapter.kind or device.adapter
    if kind == "wing_native":
        return "wing"
    return kind


def _append_midi_library_points(
    device: DeviceConfig,
    adapter: AdapterConfig,
    specs: list[DataPointSpec],
    output_points: set[str],
) -> None:
    if not device.library:
        return
    library = get_midi_library(device.library)
    library_port = resolve_library_port(adapter)
    for parameter in library.parameters:
        direction = (
            DataPointDirection.INPUT
            if parameter.direction == "source"
            else DataPointDirection.OUTPUT
        )
        specs.append(
            DataPointSpec(
                id=DataPointId(device.uid, parameter.id),
                value_type=ValueType.FLOAT,
                direction=direction,
                label=parameter.label,
                value_min=_optional_library_range(parameter.value_min),
                value_max=_optional_library_range(parameter.value_max),
                protocol="midi",
                input_mode=(
                    parameter.value_type if parameter.direction == "source" else ""
                ),
                relative_encoding=(
                    parameter.relative_encoding if parameter.direction == "source" else ""
                ),
                category=parameter.category,
            )
        )
        if direction == DataPointDirection.OUTPUT:
            output_points.add(parameter.id)
        elif (
            parameter.direction == "source"
            and parameter.message_type == "control_change"
            and parameter.category == "fader"
        ):
            output_points.add(parameter.id)


def _append_osc_library_points(
    device: DeviceConfig,
    kind: str,
    specs: list[DataPointSpec],
    output_points: set[str],
) -> None:
    if not device.library:
        return
    library = get_osc_library(device.library)
    protocol = "wing_native" if kind == "wing" else "osc"
    for parameter in library.parameters:
        if parameter.direction == "source":
            direction = DataPointDirection.INPUT
        else:
            direction = DataPointDirection.BIDIRECTIONAL
        point = parameter.address if parameter.address.startswith("/") else parameter.id
        specs.append(
            DataPointSpec(
                id=DataPointId(device.uid, point),
                value_type=ValueType.FLOAT,
                direction=direction,
                label=parameter.label,
                value_min=_optional_library_range(parameter.value_min),
                value_max=_optional_library_range(parameter.value_max),
                protocol=protocol,
                category=parameter.category,
            )
        )
        if direction in {
            DataPointDirection.OUTPUT,
            DataPointDirection.BIDIRECTIONAL,
        }:
            output_points.add(point)


def _append_gpio_points(
    device: DeviceConfig,
    gpio_adapter: GpioAdapter | None,
    specs: list[DataPointSpec],
) -> None:
    if gpio_adapter is None:
        return
    for gpio_input in gpio_adapter.inputs:
        specs.append(
            DataPointSpec(
                id=DataPointId(device.uid, gpio_input.control),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.INPUT,
                label=f"GPIO pin {gpio_input.pin}",
                value_min=0.0,
                value_max=1.0,
                protocol="gpio",
                category="gpio",
            )
        )


def _append_hid_points(
    device: DeviceConfig,
    hid_adapter: HidAdapter | None,
    specs: list[DataPointSpec],
) -> None:
    if hid_adapter is None:
        return
    for hid_input in hid_adapter.inputs:
        specs.append(
            DataPointSpec(
                id=DataPointId(device.uid, hid_input.control),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.INPUT,
                label=hid_input.code_name,
                value_min=hid_input.value_min,
                value_max=hid_input.value_max,
                protocol="hid",
                category="hid",
            )
        )


def _custom_point_spec(device_id: str, point: CustomPointSpec) -> DataPointSpec:
    direction = _DIRECTION_MAP.get(point.direction, DataPointDirection.BIDIRECTIONAL)
    value_type = ValueType.FLOAT
    if point.value_type == "bool":
        value_type = ValueType.BOOL
    elif point.value_type == "int":
        value_type = ValueType.INT
    return DataPointSpec(
        id=DataPointId(device_id, point.id),
        value_type=value_type,
        direction=direction,
        label=point.label or point.id,
        value_min=float(point.value_min),
        value_max=float(point.value_max),
        protocol=point.protocol,
        category="custom",
        input_mode=point.input_mode,
        relative_encoding=point.relative_encoding,
    )


def _midi_out_spec(device_id: str) -> DataPointSpec:
    return DataPointSpec(
        id=DataPointId(device_id, MIDI_OUT_POINT),
        value_type=ValueType.MIDI_MESSAGE,
        direction=DataPointDirection.INPUT,
        label="MIDI output",
        protocol="midi",
        category="midi",
    )


def library_point_ids(device: DeviceConfig, adapter: AdapterConfig) -> set[str]:
    """Return logical point ids provided by a device library catalog."""

    kind = _resolved_kind(device, adapter)
    point_ids: set[str] = set()
    if kind == "midi":
        if not device.library:
            return point_ids
        library = get_midi_library(device.library)
        point_ids.update(parameter.id for parameter in library.parameters)
        return point_ids
    if kind in {"osc", "wing"}:
        if not device.library:
            return point_ids
        library = get_osc_library(device.library)
        for parameter in library.parameters:
            point = parameter.address if parameter.address.startswith("/") else parameter.id
            point_ids.add(point)
        return point_ids
    if kind == "gpio" and adapter.kind == "gpio":
        return set()
    if kind == "hid" and adapter.kind == "hid":
        return set()
    return point_ids


def library_address_for_point(
    registry: DeviceRegistry,
    device_id: str,
    point: str,
) -> str | None:
    device = registry.require(device_id)
    if point.startswith("/"):
        return None
    if not device.library:
        return None
    kind = registry.resolved_library_kind(device)
    if kind not in {"osc", "wing"}:
        return None
    library = get_osc_library(device.library)
    for parameter in library.parameters:
        if parameter.id != point:
            continue
        address = parameter.address if parameter.address.startswith("/") else parameter.id
        if address != point:
            return address
    return None
