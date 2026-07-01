import asyncio
import logging

from midijuggler.eventbus import EventBus
from midijuggler.events import LogEvent
from midijuggler.web.monitor_log import MonitorLogHandler


def test_monitor_log_handler_publishes_log_event() -> None:
    bus = EventBus()
    events: list[LogEvent] = []
    bus.subscribe(LogEvent, lambda event: events.append(event))

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        handler = MonitorLogHandler(bus, loop)
        handler.setLevel(logging.INFO)
        root_logger = logging.getLogger("midijuggler")
        root_logger.addHandler(handler)
        handler.start()
        logging.getLogger("midijuggler.test").warning("adapter unavailable")
        await asyncio.sleep(0.05)
        root_logger.removeHandler(handler)
        await handler.stop()

    asyncio.run(scenario())

    assert len(events) == 1
    assert events[0].level == "WARNING"
    assert events[0].message == "adapter unavailable"
    assert events[0].logger == "midijuggler.test"
