import asyncio

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import parse_config
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.service import MIDIJugglerService


def test_master_clock_start_does_not_recursion_error() -> None:
    config = parse_config(
        {
            "master_clock": {
                "enabled": True,
                "bpm": 120.0,
                "auto_start": False,
            },
            "adapters": {"gpio": {"enabled": False}},
        }
    )
    service = MIDIJugglerService(config)

    async def scenario() -> None:
        service.event_bridge.attach()
        await service.master_clock.start()
        await service.module_registry.start_all()

    asyncio.run(scenario())
