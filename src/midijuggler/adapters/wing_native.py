"""Wing native TCP adapter."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from midijuggler.adapters.base import Adapter
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus
from midijuggler.events import AdapterStatusEvent, MappedEvent, OscMessageEvent
from midijuggler.midi.echo_guard import (
    DEFAULT_ECHO_GUARD_MS,
    OscEchoGuard,
    parse_echo_guard_ms,
)
from midijuggler.wing.native.client import KEEPALIVE_INTERVAL_SECONDS, WingNativeClient
from midijuggler.wing.native.connectivity import WingNativeConnectivity
from midijuggler.wing.native.decoder import WingNodeData
from midijuggler.osc_library import get_osc_library

LOGGER = logging.getLogger(__name__)


class WingNativeAdapter(Adapter):
    protocol = "Wing Native"

    def __init__(self, name: str, config: AdapterConfig, bus: EventBus) -> None:
        super().__init__(name, config, bus)
        self._apply_options(config.options)
        self._client: WingNativeClient | None = None
        self._read_task: asyncio.Task[None] | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._echo_guard = OscEchoGuard()
        self._connectivity = WingNativeConnectivity()
        self._last_status_detail = ""

    def connectivity_snapshot(self) -> dict[str, Any]:
        if self._client is not None:
            self._connectivity.paths_cached = self._client.path_cache_size
        return self._connectivity.as_dict()

    def _apply_options(self, options: dict[str, Any]) -> None:
        self._remote_host = str(options.get("remote_host", "")).strip()
        self._native_port = int(options.get("native_port", 2222))
        self._wing_library = str(options.get("wing_library", "behringer_wing")).strip()

    def _configure_echo_guard(self) -> None:
        self._echo_guard.configure(
            parse_echo_guard_ms(self.config.options.get("echo_guard_ms"))
        )

    async def start(self) -> None:
        self._apply_options(self.config.options)
        self._configure_echo_guard()
        if not self._remote_host:
            raise OSError(f"Wing native adapter {self.name} requires remote_host")

        self._connectivity.note_connecting(self._remote_host, self._native_port)
        await self._publish_connectivity_status(force=True)

        self._client = WingNativeClient(self._remote_host, port=self._native_port)
        try:
            await self._client.connect()
        except OSError as exc:
            self._connectivity.note_error(str(exc))
            await self._publish_connectivity_status(force=True)
            raise

        self.running = True
        warmup_failed = await self._warm_path_cache()
        self._connectivity.paths_warmup_failed = warmup_failed
        self._connectivity.note_connected(self._remote_host, self._native_port)
        self._connectivity.paths_cached = self._client.path_cache_size
        await self._publish_connectivity_status(force=True)

        self._read_task = asyncio.create_task(self._read_loop(), name=f"wing-native-read-{self.name}")
        self._keepalive_task = asyncio.create_task(
            self._keepalive_loop(),
            name=f"wing-native-keepalive-{self.name}",
        )

    async def reload(self, config: AdapterConfig) -> None:
        previous_host = self._remote_host
        previous_port = self._native_port
        self.config = config
        self._apply_options(config.options)
        self._configure_echo_guard()
        if not self.running:
            return
        if previous_host == self._remote_host and previous_port == self._native_port:
            return
        await self.stop()
        await self.start()

    async def stop(self) -> None:
        self.running = False
        for task in (self._read_task, self._keepalive_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._read_task = None
        self._keepalive_task = None
        if self._client is not None:
            await self._client.close()
            self._client = None

        self._connectivity.note_stopped()
        await self._publish_connectivity_status(force=True)

    async def send(self, event: MappedEvent) -> None:
        address = _target_address(self.name, event.target)
        if address is None:
            await super().send(event)
            return
        if self._client is None or not self.running:
            LOGGER.warning("Wing native adapter %s is not running", self.name)
            return

        node_id = await self._client.resolve_path(address)
        value = float(event.value)
        await self._client.set_float(node_id, value)
        self._connectivity.note_send()
        self._echo_guard.record(address, value)
        await self.bus.publish(
            OscMessageEvent(
                source=self.name,
                address=address,
                arguments=(value,),
                target=event.target,
                direction="output",
                canonical_address=address,
            )
        )

    async def _keepalive_loop(self) -> None:
        try:
            while self.running:
                await asyncio.sleep(KEEPALIVE_INTERVAL_SECONDS)
                if not self.running or self._client is None:
                    break
                await self._client.keepalive()
                self._connectivity.note_keepalive()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.exception("Wing native keepalive failed for %s", self.name)
            self._connectivity.note_error(f"keepalive failed: {exc}")
            await self._publish_connectivity_status(force=True)

    async def _read_loop(self) -> None:
        assert self._client is not None
        try:
            while self.running:
                events = await self._client.read_events()
                handled = self._client.handle_events(events)
                for item in handled:
                    if isinstance(item, WingNodeData):
                        await self._publish_node_data(item)
        except asyncio.CancelledError:
            raise
        except ConnectionError as exc:
            LOGGER.warning("Wing native connection closed for %s", self.name)
            self._connectivity.note_error(str(exc) or "connection closed")
            await self._publish_connectivity_status(force=True)
        except Exception as exc:
            LOGGER.exception("Wing native read loop failed for %s", self.name)
            self._connectivity.note_error(str(exc))
            await self._publish_connectivity_status(force=True)

    async def _publish_node_data(self, data: WingNodeData) -> None:
        if self._client is None:
            return
        path = self._client.path_for_node(data.node_id)
        if path is None:
            LOGGER.debug(
                "Wing native adapter %s ignored update for unknown node id %s",
                self.name,
                data.node_id,
            )
            return

        numeric_value = data.float_value
        if numeric_value is None and data.int_value is not None:
            numeric_value = float(data.int_value)
        if numeric_value is None:
            return

        is_echo = self._echo_guard.is_echo(path, numeric_value)
        await self.bus.publish(
            OscMessageEvent(
                source=self.name,
                address=path,
                arguments=(numeric_value,),
                direction="input",
                canonical_address=path,
                echo_suppressed=is_echo,
            )
        )
        if is_echo:
            return
        self._connectivity.note_feedback(path, numeric_value)
        await self._publish_connectivity_status()
        LOGGER.info(
            "Wing native adapter %s input %s %s",
            self.name,
            path,
            numeric_value,
        )

    async def _warm_path_cache(self) -> int:
        if self._client is None or not self._wing_library:
            return 0
        try:
            library = get_osc_library(self._wing_library)
        except KeyError:
            LOGGER.warning(
                "Wing native adapter %s could not load library %s for path warm-up",
                self.name,
                self._wing_library,
            )
            return 0

        failed = 0
        for parameter in library.parameters:
            address = parameter.address if parameter.address.startswith("/") else f"/{parameter.id}"
            try:
                await self._client.resolve_path(address)
            except KeyError:
                failed += 1
                LOGGER.debug(
                    "Wing native adapter %s could not resolve %s during warm-up",
                    self.name,
                    address,
                )
            except Exception:
                failed += 1
                LOGGER.exception(
                    "Wing native adapter %s failed resolving %s during warm-up",
                    self.name,
                    address,
                )
        return failed

    def _connection_detail(self) -> str:
        snapshot = self.connectivity_snapshot()
        host = snapshot["remote_host"]
        port = snapshot["native_port"]
        phase = snapshot["connection_phase"]

        if phase == "stopped":
            return "Wing native adapter stopped"
        if phase == "connecting":
            return f"Wing native connecting to {host}:{port}"
        if phase == "error":
            error = snapshot["last_error"] or "unknown error"
            return f"Wing native error on {host}:{port}: {error}"

        parts = [
            f"Wing native connected to {host}:{port}",
            f"{snapshot['paths_cached']} paths cached",
        ]
        if snapshot["paths_warmup_failed"]:
            parts.append(f"{snapshot['paths_warmup_failed']} warm-up misses")
        feedback_age = snapshot.get("last_feedback_age_s")
        if snapshot.get("last_feedback_path") and feedback_age is not None:
            parts.append(
                f"last feedback {feedback_age:.1f}s ago {snapshot['last_feedback_path']}"
            )
        elif feedback_age is None and snapshot.get("connected_age_s") is not None:
            parts.append("no feedback yet")
        keepalive_age = snapshot.get("last_keepalive_age_s")
        if keepalive_age is not None:
            parts.append(f"keepalive {keepalive_age:.1f}s ago")
        return "; ".join(parts)

    async def _publish_connectivity_status(self, *, force: bool = False) -> None:
        detail = self._connection_detail()
        if not force and detail == self._last_status_detail:
            return
        self._last_status_detail = detail
        phase = self._connectivity.connection_phase
        status = "stopped" if phase == "stopped" else "started"
        if phase == "error":
            status = "error"
        await self.bus.publish(
            AdapterStatusEvent(
                source=self.name,
                adapter=self.name,
                status=status,
                detail=detail,
                connection_phase=phase,
            )
        )


def _target_address(adapter_name: str, target: str) -> str | None:
    prefix = f"{adapter_name}:"
    if not target.startswith(prefix):
        return None
    address = target[len(prefix) :].strip()
    if not address.startswith("/"):
        address = f"/{address}"
    return address
