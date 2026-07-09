"""BandHelper song context: Ableton Link BPM follow and OSC key input."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from midijuggler.config import BandHelperConfig
from midijuggler.datapoint.store import DataPointStore
from midijuggler.datapoint.types import (
    DataPointDirection,
    DataPointId,
    DataPointSpec,
    DataPointValue,
    ValueType,
)
from midijuggler.eventbus import EventBus
from midijuggler.events import BpmChangedEvent, OscMessageEvent
from midijuggler.master_clock import MasterClock, quantize_bpm
from midijuggler.modules.base import InterfaceModule
from midijuggler.modules.interface.bandhelper.key import (
    ParsedKey,
    parse_key,
    parse_key_mode,
    parse_key_root,
)

LOGGER = logging.getLogger(__name__)

BANDHELPER_SOURCE = "bandhelper"

SONG_MODULE = "song"

try:
    from aalink import Link as AbletonLink
except ImportError:  # pragma: no cover - optional dependency
    AbletonLink = None


class BandHelperModule(InterfaceModule):
    """Follow BandHelper tempo via Ableton Link and receive song key via OSC."""

    def __init__(
        self,
        store: DataPointStore,
        config: BandHelperConfig,
        master_clock: MasterClock,
        bus: EventBus,
    ) -> None:
        super().__init__(SONG_MODULE, store)
        self.config = config
        self.master_clock = master_clock
        self.bus = bus
        self._link: Any | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._last_link_tempo: float | None = None
        self._last_applied_link_tempo: float | None = None
        self._last_link_peers: int | None = None
        self._last_skip_reason: str | None = None
        self._last_key: ParsedKey | None = None
        self._applying_from_link = False

    def datapoints(self) -> list[DataPointSpec]:
        return [
            DataPointSpec(
                id=DataPointId(SONG_MODULE, "link_tempo"),
                value_type=ValueType.FLOAT,
                direction=DataPointDirection.INPUT,
                label="Ableton Link tempo",
                value_min=self.master_clock.config.bpm_min,
                value_max=self.master_clock.config.bpm_max,
                protocol="ableton_link",
                category="tempo",
            ),
            DataPointSpec(
                id=DataPointId(SONG_MODULE, "link_peers"),
                value_type=ValueType.INT,
                direction=DataPointDirection.INPUT,
                label="Ableton Link other peer count",
                value_min=0,
                value_max=64,
                protocol="ableton_link",
                category="status",
            ),
            DataPointSpec(
                id=DataPointId(SONG_MODULE, "key_root"),
                value_type=ValueType.INT,
                direction=DataPointDirection.INPUT,
                label="Song key root (0=C .. 11=B)",
                value_min=0,
                value_max=11,
                protocol="bandhelper",
                category="key",
            ),
            DataPointSpec(
                id=DataPointId(SONG_MODULE, "key_minor"),
                value_type=ValueType.BOOL,
                direction=DataPointDirection.INPUT,
                label="Song key mode (true=minor)",
                protocol="bandhelper",
                category="key",
            ),
        ]

    async def start(self) -> None:
        await super().start()
        self._loop = asyncio.get_running_loop()
        self.bus.subscribe(OscMessageEvent, self._on_osc_message)
        self.bus.subscribe(BpmChangedEvent, self._on_bpm_changed)
        if self.config.link_enabled:
            await self._start_link()

    async def stop(self) -> None:
        await self._stop_link()
        await super().stop()

    async def update_config(self, config: BandHelperConfig) -> None:
        previous_link = self.config.link_enabled
        self.config = config
        if not self.running:
            return
        if config.link_enabled and not previous_link:
            await self._start_link()
        elif not config.link_enabled and previous_link:
            await self._stop_link()

    async def _stop_link(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        if self._link is not None:
            self._link.enabled = False
            self._link = None
        self._last_link_tempo = None
        self._last_applied_link_tempo = None
        self._last_link_peers = None

    async def _start_link(self) -> None:
        if AbletonLink is None:
            LOGGER.error(
                "bandhelper link_enabled requires aalink; install with: pip install 'midijuggler[ableton_link]'"
            )
            return

        self._link = AbletonLink(self.config.start_bpm)
        self._link.enabled = True
        self._link.add_tempo_callback(self._on_link_tempo_callback)
        self._poll_task = asyncio.create_task(self._link_poll_loop())
        LOGGER.info(
            "bandhelper Ableton Link enabled (start_bpm=%.2f, other_peers=%d, session_tempo=%.2f)",
            self.config.start_bpm,
            int(self._link.num_peers),
            float(self._link.tempo),
        )
        await self._sync_link_tempo(float(self._link.tempo), int(self._link.num_peers))

    def _on_link_tempo_callback(self, tempo: float) -> None:
        if self._loop is None:
            return

        def schedule() -> None:
            asyncio.create_task(self._sync_link_tempo(float(tempo), peers=None))

        self._loop.call_soon_threadsafe(schedule)

    async def _link_poll_loop(self) -> None:
        interval = max(self.config.poll_interval_ms, 10) / 1000.0
        while self.running and self._link is not None:
            await self._sync_link_tempo(
                float(self._link.tempo),
                int(self._link.num_peers),
            )
            await asyncio.sleep(interval)

    async def _sync_link_tempo(self, tempo: float, peers: int | None) -> None:
        session_tempo_changed = await self._publish_link_status(tempo=tempo, peers=peers)
        if not session_tempo_changed:
            return
        if not self._should_apply_link_tempo(tempo):
            return
        quantized = quantize_bpm(tempo, self.config.quantize_step)
        self._applying_from_link = True
        try:
            await self.master_clock.set_bpm(quantized, source=BANDHELPER_SOURCE)
            await self.master_clock.flush_bpm_notifications()
        finally:
            self._applying_from_link = False
        self._last_applied_link_tempo = quantized
        LOGGER.info(
            "bandhelper applied Link tempo %.2f BPM (raw %.2f)",
            quantized,
            tempo,
        )

    async def _on_bpm_changed(self, event: BpmChangedEvent) -> None:
        if self._applying_from_link or self._link is None or not self.config.link_enabled:
            return
        quantized = quantize_bpm(event.bpm, self.config.quantize_step)
        if abs(float(self._link.tempo) - quantized) < self.config.min_bpm_delta:
            self._last_applied_link_tempo = quantized
            return
        self._link.tempo = quantized
        self._last_applied_link_tempo = quantized
        LOGGER.info(
            "bandhelper pushed local tempo %.2f BPM to Ableton Link",
            quantized,
        )

    def _should_apply_link_tempo(self, tempo: float) -> bool:
        if tempo <= 0:
            self._log_skip("invalid tempo", tempo)
            return False
        if not self.config.follow_when_running and self.master_clock.running:
            self._log_skip("transport running and follow_when_running=false", tempo)
            return False
        if (
            self._last_applied_link_tempo is not None
            and abs(tempo - self._last_applied_link_tempo) < self.config.min_bpm_delta
        ):
            self._log_skip(
                f"link tempo unchanged since last apply ({self._last_applied_link_tempo:.2f})",
                tempo,
            )
            return False
        self._last_skip_reason = None
        return True

    def _log_skip(self, reason: str, tempo: float) -> None:
        message = f"bandhelper skipped Link tempo {tempo:.2f}: {reason}"
        if message == self._last_skip_reason:
            return
        self._last_skip_reason = message
        LOGGER.info(message)

    async def _publish_link_status(
        self,
        *,
        tempo: float,
        peers: int | None,
    ) -> bool:
        tempo_changed = (
            self._last_link_tempo is None
            or abs(self._last_link_tempo - tempo) >= self.config.min_bpm_delta
        )
        if tempo_changed:
            self._last_link_tempo = tempo
            await self.store.write(
                DataPointValue(
                    point_id=DataPointId(SONG_MODULE, "link_tempo"),
                    value_type=ValueType.FLOAT,
                    float_value=tempo,
                    force_notify=True,
                )
            )
            LOGGER.info("bandhelper Link session tempo %.2f BPM", tempo)

        if peers is not None and peers != self._last_link_peers:
            self._last_link_peers = peers
            await self.store.write(
                DataPointValue(
                    point_id=DataPointId(SONG_MODULE, "link_peers"),
                    value_type=ValueType.INT,
                    int_value=peers,
                    force_notify=True,
                )
            )
            LOGGER.info(
                "bandhelper Link reports %d other peer(s) in session",
                peers,
            )
        return tempo_changed

    async def _on_osc_message(self, event: OscMessageEvent) -> None:
        if event.direction != "input":
            return

        address = event.canonical_address or event.address
        if address == self.config.key_osc_address:
            await self._handle_key_message(event.arguments)
            return
        if (
            self.config.key_root_osc_address
            and address == self.config.key_root_osc_address
        ):
            await self._handle_key_root_message(event.arguments)
            return
        if (
            self.config.key_mode_osc_address
            and address == self.config.key_mode_osc_address
        ):
            await self._handle_key_mode_message(event.arguments)

    async def _handle_key_message(self, arguments: tuple[Any, ...]) -> None:
        if not arguments:
            LOGGER.warning("ignored song key OSC message without arguments")
            return
        parsed = parse_key(str(arguments[0]))
        if parsed is None:
            LOGGER.warning("ignored unparseable song key: %s", arguments[0])
            return
        await self._publish_key(parsed)

    async def _handle_key_root_message(self, arguments: tuple[Any, ...]) -> None:
        if not arguments:
            return
        root = parse_key_root(arguments[0])
        if root is None:
            LOGGER.warning("ignored unparseable song key root: %s", arguments[0])
            return
        minor = self._last_key.minor if self._last_key is not None else False
        await self._publish_key(
            ParsedKey(root=root, minor=minor, raw=self._last_key.raw if self._last_key else "")
        )

    async def _handle_key_mode_message(self, arguments: tuple[Any, ...]) -> None:
        if not arguments:
            return
        minor = parse_key_mode(arguments[0])
        if minor is None:
            LOGGER.warning("ignored unparseable song key mode: %s", arguments[0])
            return
        root = self._last_key.root if self._last_key is not None else 0
        await self._publish_key(
            ParsedKey(
                root=root,
                minor=minor,
                raw=self._last_key.raw if self._last_key else "",
            )
        )

    async def _publish_key(self, parsed: ParsedKey) -> None:
        previous = self._last_key
        self._last_key = parsed
        force = (
            previous is None
            or previous.root != parsed.root
            or previous.minor != parsed.minor
        )
        await self.store.write(
            DataPointValue(
                point_id=DataPointId(SONG_MODULE, "key_root"),
                value_type=ValueType.INT,
                int_value=parsed.root,
                force_notify=force,
            )
        )
        await self.store.write(
            DataPointValue(
                point_id=DataPointId(SONG_MODULE, "key_minor"),
                value_type=ValueType.BOOL,
                bool_value=parsed.minor,
                force_notify=force,
            )
        )
        LOGGER.info(
            "bandhelper song key %s%s (%s)",
            parsed.root_name,
            "m" if parsed.minor else "",
            parsed.raw or parsed.mode,
        )
