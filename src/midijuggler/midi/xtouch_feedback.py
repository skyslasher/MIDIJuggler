"""Periodic feedback refresh for the Behringer X-Touch Mini."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from midijuggler.config import AdapterConfig, AppConfig
from midijuggler.midi.xtouch_channels import XTOUCH_MINI_LIBRARY_ID, xtouch_value_channel
from midijuggler.midi_library import get_midi_library

if TYPE_CHECKING:
    from midijuggler.adapters.midi import MidiAdapter

LOGGER = logging.getLogger(__name__)

PROGRAM_CHANGE = 0xC0


def uses_xtouch_feedback_refresh(config: AdapterConfig) -> bool:
    library_id = str(config.options.get("midi_library", "")).strip()
    return library_id == XTOUCH_MINI_LIBRARY_ID


def feedback_refresh_interval_seconds(config: AdapterConfig) -> float:
    raw = config.options.get("feedback_refresh_interval", 0)
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 0.0


def parse_feedback_refresh_interval(value: object) -> float:
    try:
        interval = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("feedback_refresh_interval must be a number") from exc
    if interval < 0:
        raise ValueError("feedback_refresh_interval must be >= 0")
    if interval == 0:
        return 0.0
    if abs(interval * 10 - round(interval * 10)) > 1e-6:
        raise ValueError("feedback_refresh_interval must use 0.1 second steps")
    if interval > 60.0:
        raise ValueError("feedback_refresh_interval must be <= 60")
    return interval


def is_refreshable_target(parameter_id: str, *, category: str) -> bool:
    if category == "feedback":
        return True
    return category == "value" and "_encoder_" in parameter_id and parameter_id.endswith(
        "_value"
    )


def feedback_point_ids(config: AdapterConfig) -> frozenset[str]:
    if not uses_xtouch_feedback_refresh(config):
        return frozenset()
    try:
        library = get_midi_library(XTOUCH_MINI_LIBRARY_ID)
    except KeyError:
        return frozenset()
    return frozenset(
        parameter.id
        for parameter in library.parameters
        if parameter.direction == "target"
        and is_refreshable_target(parameter.id, category=parameter.category)
    )


def is_layer_program_change(
    config: AdapterConfig,
    status: int,
    data: tuple[int, ...],
) -> bool:
    if not uses_xtouch_feedback_refresh(config):
        return False
    if (status & 0xF0) != PROGRAM_CHANGE or not data:
        return False
    channel = (status & 0x0F) + 1
    return channel == xtouch_value_channel(config) and data[0] in {0, 1}


class XTouchFeedbackRefresh:
    """Re-send cached LED feedback values for inactive X-Touch layers."""

    def __init__(self, adapter: MidiAdapter, app_config: AppConfig | None) -> None:
        self._adapter = adapter
        self._app_config = app_config
        self._cache: dict[str, float] = {}
        self._feedback_points: frozenset[str] = frozenset()
        self._task: asyncio.Task[None] | None = None

    def configure(self, config: AdapterConfig, app_config: AppConfig | None) -> None:
        self._app_config = app_config
        self._feedback_points = feedback_point_ids(config)

    def remember(self, point: str, value: float) -> None:
        if point not in self._feedback_points:
            return
        self._cache[point] = value

    async def start(self, config: AdapterConfig) -> None:
        await self.stop()
        if not self._feedback_points:
            self._cache.clear()
            return
        interval = feedback_refresh_interval_seconds(config)
        if interval <= 0:
            return
        self._task = asyncio.create_task(
            self._refresh_loop(interval),
            name=f"xtouch-feedback-refresh-{self._adapter.name}",
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def resend_all(self) -> None:
        await self._resend_cached_values()

    async def _refresh_loop(self, interval: float) -> None:
        try:
            while self._adapter.running:
                await asyncio.sleep(interval)
                await self._resend_cached_values()
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception(
                "X-Touch feedback refresh failed for adapter %s",
                self._adapter.name,
            )

    async def _resend_cached_values(self) -> None:
        if self._app_config is None or not self._cache:
            return
        for point, value in list(self._cache.items()):
            try:
                await self._adapter.send_feedback_target(point, value)
            except ValueError:
                LOGGER.warning(
                    "skipping X-Touch feedback refresh for unknown point %s",
                    point,
                )
            except OSError:
                LOGGER.warning(
                    "X-Touch feedback refresh could not send %s on adapter %s",
                    point,
                    self._adapter.name,
                    exc_info=True,
                )
