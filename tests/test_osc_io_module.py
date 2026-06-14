import asyncio

from midijuggler.config import parse_config
from midijuggler.datapoint.types import DataPointDirection
from midijuggler.service import MIDIJugglerService


def test_osc_target_parameters_register_as_bidirectional_sources() -> None:
    config = parse_config(
        {
            "adapters": {
                "x32_foh": {
                    "type": "osc",
                    "enabled": True,
                    "osc_library": "behringer_x32",
                }
            }
        }
    )
    service = MIDIJugglerService(config)

    async def scenario() -> list[dict]:
        await service.module_registry.start_all()
        return service.datapoint_store.registry_snapshot()

    specs = asyncio.run(scenario())
    fader = next(
        entry
        for entry in specs
        if entry["id"] == "x32_foh./ch/01/mix/fader"
    )

    assert fader["direction"] == DataPointDirection.BIDIRECTIONAL.value


def test_osc_io_module_does_not_echo_input_sourced_datapoint_writes() -> None:
    from unittest.mock import AsyncMock

    from midijuggler.adapters.osc import OscAdapter
    from midijuggler.datapoint.store import DataPointStore
    from midijuggler.datapoint.types import float_value
    from midijuggler.eventbus import EventBus
    from midijuggler.modules.io.osc import OscIOModule

    config = parse_config(
        {
            "adapters": {
                "x32_foh": {
                    "type": "osc",
                    "enabled": True,
                    "osc_library": "behringer_x32",
                }
            }
        }
    )
    store = DataPointStore()
    bus = EventBus()
    adapter = OscAdapter("x32_foh", config.adapters["x32_foh"], bus)
    module = OscIOModule(adapter, store, config)
    store.register_many(module.datapoints())
    adapter.send = AsyncMock()

    async def scenario() -> None:
        await module.start()
        await store.write(
            float_value("x32_foh./ch/01/mix/fader", 0.5, emit_outputs=False)
        )
        await store.write(float_value("x32_foh./ch/01/mix/fader", 0.75))

    asyncio.run(scenario())

    adapter.send.assert_awaited_once()
    sent = adapter.send.await_args.args[0]
    assert sent.value == 0.75
