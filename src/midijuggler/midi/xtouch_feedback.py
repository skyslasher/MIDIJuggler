"""Periodic feedback refresh for Behringer X-Touch controllers."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from midijuggler.config import AdapterConfig, AppConfig
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import DataPointId
from midijuggler.device.types import DeviceConfig
from midijuggler.midi.xtouch_channels import (
    is_xtouch_library,
    xtouch_device_options,
    xtouch_value_channel,
)
from midijuggler.midi_library import get_midi_library

if TYPE_CHECKING:
    from midijuggler.adapters.midi import MidiAdapter

LOGGER = logging.getLogger(__name__)

PROGRAM_CHANGE = 0xC0


def uses_xtouch_feedback_refresh(
    config: AdapterConfig,
    *,
    library_id: str | None = None,
    device: DeviceConfig | None = None,
) -> bool:
    return is_xtouch_library(
        xtouch_device_options(config, device, library_id=library_id).library_id
    )


def feedback_refresh_interval_seconds(
    config: AdapterConfig,
    device: DeviceConfig | None = None,
) -> float:
    return xtouch_device_options(config, device).feedback_refresh_interval


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


def is_refreshable_target(
    parameter_id: str,
    *,
    category: str,
    direction: str,
) -> bool:
    if category == "feedback":
        return True
    if category == "value" and "_encoder_" in parameter_id and parameter_id.endswith(
        "_value"
    ):
        return True
    return category == "fader" and direction == "bidirectional"


def feedback_point_ids(
    config: AdapterConfig,
    *,
    library_id: str | None = None,
    device: DeviceConfig | None = None,
) -> frozenset[str]:
    resolved_library = xtouch_device_options(
        config,
        device,
        library_id=library_id,
    ).library_id
    if not is_xtouch_library(resolved_library):
        return frozenset()
    try:
        library = get_midi_library(resolved_library)
    except KeyError:
        return frozenset()
    return frozenset(
        parameter.id
        for parameter in library.parameters
        if parameter.direction in {"target", "bidirectional"}
        and is_refreshable_target(
            parameter.id,
            category=parameter.category,
            direction=parameter.direction,
        )
    )


def is_layer_program_change(
    config: AdapterConfig,
    status: int,
    data: tuple[int, ...],
    *,
    library_id: str | None = None,
    device: DeviceConfig | None = None,
) -> bool:
    if not uses_xtouch_feedback_refresh(config, library_id=library_id, device=device):
        return False
    if (status & 0xF0) != PROGRAM_CHANGE or not data:
        return False
    channel = (status & 0x0F) + 1
    return channel == xtouch_value_channel(config, device) and data[0] in {0, 1}


class XTouchFeedbackRefresh:
    """Re-send cached LED feedback values for inactive X-Touch layers."""

    def __init__(self, adapter: MidiAdapter, app_config: AppConfig | None) -> None:
        self._adapter = adapter
        self._app_config = app_config
        self._cache: dict[str, float] = {}
        self._feedback_points: frozenset[str] = frozenset()
        self._task: asyncio.Task[None] | None = None
        self._device: DeviceConfig | None = None
        self._store: DataPointStore | None = None
        self._device_id: str = ""

    def configure(
        self,
        config: AdapterConfig,
        app_config: AppConfig | None,
        device: DeviceConfig | None = None,
        *,
        library_id: str | None = None,
        store: DataPointStore | None = None,
        device_id: str = "",
    ) -> None:
        self._app_config = app_config
        self._device = device
        self._store = store
        self._device_id = device_id or (device.id if device is not None else "")
        self._feedback_points = feedback_point_ids(
            config,
            library_id=library_id,
            device=device,
        )
        self._seed_cache_from_store()

    def remember(self, point: str, value: float) -> None:
        if point not in self._feedback_points:
            return
        self._cache[point] = value

    async def start(self, config: AdapterConfig) -> None:
        await self.stop()
        if not self._feedback_points:
            self._cache.clear()
            return
        interval = feedback_refresh_interval_seconds(config, self._device)
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
        self._seed_cache_from_store()
        await self._resend_cached_values()

    def _seed_cache_from_store(self) -> None:
        if self._store is None or not self._device_id:
            return
        for point in self._feedback_points:
            value = self._store.float_value(DataPointId(self._device_id, point))
            if value is not None:
                self._cache[point] = value

    def _value_for_point(self, point: str) -> float | None:
        if self._store is not None and self._device_id:
            value = self._store.float_value(DataPointId(self._device_id, point))
            if value is not None:
                self._cache[point] = value
                return value
        return self._cache.get(point)

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
        if self._app_config is None or not self._feedback_points:
            return
        for point in self._feedback_points:
            value = self._value_for_point(point)
            if value is None:
                continue
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
