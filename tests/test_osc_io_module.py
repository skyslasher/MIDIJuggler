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
