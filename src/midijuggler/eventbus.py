"""Small asyncio event bus used by adapters, mappers and the web UI."""

from __future__ import annotations

import inspect
import logging
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from midijuggler.events import Event

LOGGER = logging.getLogger(__name__)

Handler = Callable[[Event], Awaitable[None] | None]


class EventBus:
    """Publish events to exact-type subscribers and wildcard observers."""

    def __init__(self, history_size: int = 200) -> None:
        self._subscribers: dict[type[Event] | str, list[Handler]] = defaultdict(list)
        self._history: deque[Event] = deque(maxlen=history_size)

    def subscribe(self, event_type: type[Event] | str, handler: Handler) -> None:
        """Subscribe to an event class or "*" for all events."""

        if event_type != "*" and not (
            inspect.isclass(event_type) and issubclass(event_type, Event)
        ):
            raise TypeError("event_type must be an Event subclass or '*'")
        self._subscribers[event_type].append(handler)

    async def publish(self, event: Event) -> None:
        """Publish an event and await async handlers."""

        self._history.append(event)
        handlers = [*self._subscribers[type(event)], *self._subscribers["*"]]
        for handler in handlers:
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                LOGGER.exception("event handler failed for %s", event.kind)

    def history(self) -> list[Event]:
        """Return a snapshot of recent events."""

        return list(self._history)

    def history_dicts(self) -> list[dict[str, Any]]:
        return [event.as_dict() for event in self._history]

    async def publish_many(self, events: Iterable[Event]) -> None:
        for event in events:
            await self.publish(event)
