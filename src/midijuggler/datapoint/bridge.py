"""Translate between legacy events/mappings and data points."""

from __future__ import annotations

from midijuggler.datapoint.endpoints import osc_address_variants
from midijuggler.datapoint.types import ConnectionSpec, DataPointId, DataPointValue, ModifierKind, ValueType, float_value, midi_message_value
from midijuggler.datapoint.store import DataPointStore
from midijuggler.device.registry import DeviceRegistry
from midijuggler.eventbus import EventBus
from midijuggler.events import ControlEvent, MasterClockStateEvent, MidiMessageEvent, OscMessageEvent
from midijuggler.osc.protocol import first_numeric_osc_argument, wing_control_value
from midijuggler.mapping import MappingRule


def legacy_source_to_datapoint(source: str) -> str:
    module, separator, point = source.partition(":")
    if not separator:
        return source
    return f"{module}.{point}"


def legacy_target_to_datapoint(target: str) -> str:
    module, separator, point = target.partition(":")
    if not separator:
        return target
    if point.startswith("/"):
        return f"{module}.{point}"
    if point.startswith(("cc:", "note:", "program:", "pitch_bend:")):
        return f"{module}.{point.replace(':', '_')}"
    return f"{module}.{point.replace(':', '_')}"


def datapoint_to_legacy_source(point_id: str) -> str:
    parsed = DataPointId.parse(point_id)
    return f"{parsed.module}:{parsed.point}"


def datapoint_to_legacy_target(point_id: str) -> str:
    parsed = DataPointId.parse(point_id)
    if parsed.point.startswith("/"):
        return f"{parsed.module}:{parsed.point}"
    if parsed.point.startswith(("cc_", "note_", "program_", "pitch_bend_")):
        return f"{parsed.module}:{parsed.point.replace('_', ':', 1).replace('_', ':')}"
    return f"{parsed.module}:{parsed.point}"


def connection_from_legacy_mapping(rule: MappingRule) -> ConnectionSpec:
    return ConnectionSpec(
        id=rule.id,
        source=legacy_source_to_datapoint(rule.source),
        target=legacy_target_to_datapoint(rule.target),
        modifier=ModifierKind.RANGE_MAP,
        input_min=rule.input_min,
        input_max=rule.input_max,
        output_min=rule.output_min,
        output_max=rule.output_max,
        invert=rule.invert,
    )


def connections_from_legacy_mappings(rules: list[MappingRule]) -> list[ConnectionSpec]:
    return [connection_from_legacy_mapping(rule) for rule in rules]


def migrate_mappings_to_connections(rules: list[MappingRule]) -> list[ConnectionSpec]:
    """Convert legacy [[mappings]] entries to [[connections]] specs."""

    return connections_from_legacy_mappings(rules)


def mapping_from_connection(connection: ConnectionSpec) -> MappingRule:
    return MappingRule(
        id=connection.id,
        source=datapoint_to_legacy_source(connection.source),
        target=datapoint_to_legacy_target(connection.target),
        input_min=connection.input_min,
        input_max=connection.input_max,
        output_min=connection.output_min,
        output_max=connection.output_max,
        invert=connection.invert,
    )


class EventToDataPointBridge:
    """Mirror legacy bus events into the data-point store."""

    def __init__(
        self,
        store: DataPointStore,
        bus: EventBus,
        device_registry: DeviceRegistry,
    ) -> None:
        self.store = store
        self.bus = bus
        self.device_registry = device_registry

    def attach(self) -> None:
        self.bus.subscribe(ControlEvent, self._on_control)
        self.bus.subscribe(MidiMessageEvent, self._on_midi_message)
        self.bus.subscribe(OscMessageEvent, self._on_osc_message)
        self.bus.subscribe(MasterClockStateEvent, self._on_clock_state)

    async def _on_clock_state(self, event: MasterClockStateEvent) -> None:
        from midijuggler.datapoint.types import DataPointId, DataPointValue, ValueType

        await self.store.write(
            DataPointValue(
                point_id=DataPointId("clock", "running"),
                value_type=ValueType.BOOL,
                bool_value=event.running,
            )
        )
        await self.store.write(float_value(DataPointId("clock", "bpm"), event.bpm))

    async def _on_control(self, event: ControlEvent) -> None:
        if event.control.startswith("/"):
            return
        module = self._module_for_adapter(event.source)
        point_id = DataPointId(module=module, point=event.control)
        await self.store.write(float_value(point_id, event.value, emit_outputs=False))

    async def _on_midi_message(self, event: MidiMessageEvent) -> None:
        if event.direction == "output" and event.source == "master_clock":
            if event.status == 0xF8:
                await self.store.write(
                    midi_message_value(DataPointId("clock", "midi_tick"), event.status, event.data)
                )
            return
        if event.direction != "input":
            return
        point_id = DataPointId(
            module=self._module_for_adapter(event.source),
            point=_midi_message_point_id(event),
        )
        await self.store.write(
            midi_message_value(point_id, event.status, event.data, emit_outputs=False),
        )

    async def _on_osc_message(self, event: OscMessageEvent) -> None:
        if event.direction != "input" or event.echo_suppressed:
            return
        address = event.canonical_address or event.address
        module = self._module_for_adapter(event.source)
        point_id = self._resolve_osc_point_id(module, address)
        value = DataPointValue(
            point_id=point_id,
            value_type=ValueType.OSC_MESSAGE,
            osc_address=event.address,
            osc_arguments=event.arguments,
        )
        numeric_value = first_numeric_osc_argument(event.arguments)
        if event.address.endswith("~~~"):
            numeric_value = wing_control_value(event.arguments)
        if numeric_value is not None:
            await self.store.write(
                float_value(point_id, numeric_value, emit_outputs=False)
            )
            return
        await self.store.write(value)


    def _resolve_osc_point_id(self, module: str, address: str) -> DataPointId:
        for point in osc_address_variants(address):
            point_id = DataPointId(module=module, point=point)
            if self.store.spec(point_id) is not None:
                return point_id
        return DataPointId(module=module, point=address)

    def _module_for_adapter(self, adapter_name: str) -> str:
        if adapter_name in {"clock", "mapping"}:
            return adapter_name
        device = self.device_registry.device_for_adapter(adapter_name)
        if device is None:
            raise ValueError(f"no device configured for adapter {adapter_name!r}")
        return device.uid


def adapter_control_to_datapoint(
    adapter_name: str,
    control: str,
    device_registry: DeviceRegistry,
) -> str:
    device = device_registry.require_device_for_adapter(adapter_name)
    return str(DataPointId(device.uid, control))


def _midi_message_point_id(event: MidiMessageEvent) -> str:
    status = event.status & 0xF0
    channel = event.status & 0x0F
    if status == 0xB0 and event.data:
        return f"cc_{channel}_{event.data[0]}"
    if status in {0x90, 0x80} and event.data:
        return f"note_{channel}_{event.data[0]}"
    if status == 0xC0 and event.data:
        return f"program_{channel}_{event.data[0]}"
    if status == 0xE0:
        return f"pitch_bend_{channel}"
    return f"status_{event.status:02x}"
