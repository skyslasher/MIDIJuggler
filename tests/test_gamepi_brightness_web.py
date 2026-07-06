from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import parse_config
from midijuggler.datapoint.store import DataPointStore
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.modules.interface.gamepi_brightness import (
    BRIGHTNESS_POINT,
    BRIGHTNESS_SET_POINT,
    GamePiBrightnessModule,
    publish_brightness_to_store,
    status_to_datapoint_value,
)
from midijuggler.datapoint.types import DataPointDirection, float_value
from midijuggler.web import gamepi_brightness


@pytest.fixture(autouse=True)
def reset_brightness_cache() -> None:
    gamepi_brightness._invalidate_status_cache()
    yield
    gamepi_brightness._invalidate_status_cache()


def test_gamepi_brightness_datapoint_directions_match_connection_roles() -> None:
    store = DataPointStore()
    specs = {str(spec.id): spec for spec in GamePiBrightnessModule(store).datapoints()}

    assert specs["gamepi.brightness"].direction == DataPointDirection.INPUT
    assert specs["gamepi.brightness_set"].direction == DataPointDirection.OUTPUT


def test_brightness_set_datapoint_applies_level_and_republishes_state(monkeypatch) -> None:
    store = DataPointStore()
    module = GamePiBrightnessModule(store, state_path=Path("/tmp/unused-gamepi-brightness"))
    store.register_many(module.datapoints())
    set_calls: list[int] = []

    monkeypatch.setattr(
        gamepi_brightness,
        "set_brightness_payload",
        lambda level: set_calls.append(level)
        or {"ok": True, "available": True, "mode": "software", "level": level, "max": 255},
    )
    monkeypatch.setattr(
        gamepi_brightness,
        "_direct_brightness_status",
        lambda: {"available": True, "mode": "software", "level": 120, "max": 255},
    )

    async def scenario() -> None:
        await module.start()
        try:
            await store.write(float_value(BRIGHTNESS_SET_POINT, 180.0))
            snapshot = store.snapshot()
            assert snapshot["gamepi.brightness"]["int_value"] == 180
        finally:
            await module.stop()

    asyncio.run(scenario())

    assert set_calls == [180]


def test_parse_connection_with_gamepi_brightness_endpoints() -> None:
    from midijuggler.config import parse_config

    config = parse_config(
        {
            "connections": [
                {
                    "id": "fader-to-gamepi-brightness",
                    "source": "midi.cc_0_1",
                    "target": "gamepi.brightness_set",
                },
                {
                    "id": "gamepi-brightness-to-osc",
                    "source": "gamepi.brightness",
                    "target": "osc./monitor/brightness",
                },
            ],
            "devices": [
                {
                    "uid": "midi",
                    "name": "MIDI",
                    "adapter": "midi",
                    "library_kind": "midi",
                    "library": "generic_cc",
                },
                {
                    "uid": "osc",
                    "name": "OSC",
                    "adapter": "osc",
                    "library_kind": "osc",
                    "custom_points": [
                        {
                            "id": "/monitor/brightness",
                            "direction": "target",
                            "value_min": 0,
                            "value_max": 255,
                        }
                    ],
                },
            ],
            "adapters": {
                "midi": {"enabled": True},
                "osc": {"enabled": True, "type": "osc", "host": "127.0.0.1", "port": 9000},
            },
        }
    )

    assert config.connections[0].target == "gamepi.brightness_set"
    assert config.connections[1].source == "gamepi.brightness"


def test_status_to_datapoint_value_maps_level_max_and_available() -> None:
    value = status_to_datapoint_value(
        {"available": True, "mode": "software", "level": 180, "max": 255}
    )

    assert value.point_id == BRIGHTNESS_POINT
    assert value.int_value == 180
    assert value.bool_value is True
    assert value.float_value == 255.0


def test_status_to_datapoint_value_marks_unavailable() -> None:
    value = status_to_datapoint_value({"available": False, "mode": "none"})

    assert value.int_value == 0
    assert value.bool_value is False


def test_publish_brightness_to_store_writes_datapoint(monkeypatch) -> None:
    store = DataPointStore()
    module = GamePiBrightnessModule(store, state_path=Path("/tmp/unused-gamepi-brightness"))
    store.register_many(module.datapoints())
    monkeypatch.setattr(
        gamepi_brightness,
        "_direct_brightness_status",
        lambda: {"available": True, "mode": "software", "level": 150, "max": 255},
    )

    async def scenario() -> None:
        await publish_brightness_to_store(store)

    asyncio.run(scenario())

    snapshot = store.snapshot()
    assert snapshot["gamepi.brightness"]["int_value"] == 150
    assert snapshot["gamepi.brightness"]["bool_value"] is True
    assert snapshot["gamepi.brightness"]["float_value"] == 255.0


def test_module_start_publishes_initial_brightness(monkeypatch) -> None:
    store = DataPointStore()
    module = GamePiBrightnessModule(store, state_path=Path("/tmp/unused-gamepi-brightness"))
    monkeypatch.setattr(
        gamepi_brightness,
        "_direct_brightness_status",
        lambda: {"available": True, "mode": "software", "level": 200, "max": 255},
    )

    async def scenario() -> None:
        await module.start()
        try:
            snapshot = store.snapshot()
            assert snapshot["gamepi.brightness"]["int_value"] == 200
        finally:
            await module.stop()

    asyncio.run(scenario())


def test_poll_mtime_triggers_refresh_on_mtime_change(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / "brightness"
    state_path.write_text("120\n", encoding="utf-8")
    store = DataPointStore()
    module = GamePiBrightnessModule(store, state_path=state_path)
    module.running = True
    module._inotify = None
    module._last_mtime_ns = state_path.stat().st_mtime_ns
    refresh_calls = {"count": 0}
    original_refresh = module.refresh

    async def counting_refresh() -> None:
        refresh_calls["count"] += 1
        await original_refresh()

    module.refresh = counting_refresh  # type: ignore[method-assign]

    async def instant_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", instant_sleep)
    monkeypatch.setattr(
        "midijuggler.web.gamepi_brightness.brightness_status_payload",
        lambda **_: {"available": True, "mode": "software", "level": 140, "max": 255},
    )

    async def scenario() -> None:
        state_path.write_text("140\n", encoding="utf-8")
        await module._poll_mtime()
        assert refresh_calls["count"] == 1

    asyncio.run(scenario())


def test_adjust_endpoint_publishes_brightness(monkeypatch) -> None:
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    from midijuggler.web.server import WebInterface

    config = parse_config({})
    bus = EventBus()
    store = DataPointStore()
    web_iface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        MasterClock(config.master_clock, bus),
        datapoint_store=store,
    )
    store.register_many(GamePiBrightnessModule(store, state_path=Path("/tmp/unused")).datapoints())
    writes: list[int] = []

    async def capture_write(value) -> None:
        writes.append(value.int_value or 0)

    store.subscribe("gamepi.brightness", capture_write)

    monkeypatch.setattr(
        "midijuggler.web.gamepi_brightness.adjust_brightness_payload",
        lambda delta: {
            "ok": True,
            "available": True,
            "mode": "software",
            "level": 170,
            "max": 255,
            "delta": delta,
        },
    )

    async def scenario() -> None:
        app = web_iface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post("/api/gamepi/brightness", json={"delta": 10})
            assert response.status == 200
            payload = await response.json()
            assert payload["level"] == 170

    asyncio.run(scenario())

    assert writes
    assert writes[-1] == 170


def test_web_interface_broadcasts_brightness_datapoint(monkeypatch) -> None:
    from midijuggler.modules.interface.web import WebInterfaceModule
    from midijuggler.web.server import WebInterface

    config = parse_config({})
    bus = EventBus()
    store = DataPointStore()
    web = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        MasterClock(config.master_clock, bus),
    )
    web.broadcast_datapoint_update = AsyncMock()
    module = WebInterfaceModule(web, store)

    async def scenario() -> None:
        await module.start()
        await publish_brightness_to_store(
            store,
            {"available": True, "mode": "software", "level": 190, "max": 255},
        )

    asyncio.run(scenario())
    web.broadcast_datapoint_update.assert_awaited_once()
    payload = web.broadcast_datapoint_update.await_args.args[0]
    assert payload["id"] == "gamepi.brightness"
    assert payload["int_value"] == 190


def test_brightness_status_uses_direct_read_without_sudo(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_direct() -> dict[str, int | bool | str]:
        return {"available": True, "mode": "software", "level": 180, "max": 255}

    def fake_cli(*args: str) -> dict[str, int | bool | str]:
        calls.append(list(args))
        return {"available": False, "mode": "none"}

    monkeypatch.setattr(gamepi_brightness, "_direct_brightness_status", fake_direct)
    monkeypatch.setattr(gamepi_brightness, "_run_brightness_cli", fake_cli)

    payload = gamepi_brightness.brightness_status_payload()

    assert payload == {"available": True, "mode": "software", "level": 180, "max": 255}
    assert calls == []


def test_brightness_status_falls_back_to_sudo_when_direct_read_fails(monkeypatch) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(gamepi_brightness, "_direct_brightness_status", lambda: None)

    def fake_cli(*args: str) -> dict[str, int | bool | str]:
        calls.append(list(args))
        return {"available": True, "mode": "software", "level": 200, "max": 255}

    monkeypatch.setattr(gamepi_brightness, "_run_brightness_cli", fake_cli)

    payload = gamepi_brightness.brightness_status_payload()

    assert payload["level"] == 200
    assert calls == [["--status"]]


def test_refresh_reads_fresh_brightness_after_cache_warmup(monkeypatch) -> None:
    store = DataPointStore()
    module = GamePiBrightnessModule(store, state_path=Path("/tmp/unused-gamepi-brightness"))
    store.register_many(module.datapoints())
    reads = {"count": 0}

    def fake_direct() -> dict[str, int | bool | str]:
        reads["count"] += 1
        level = 120 if reads["count"] == 1 else 150
        return {"available": True, "mode": "software", "level": level, "max": 255}

    monkeypatch.setattr(gamepi_brightness, "_direct_brightness_status", fake_direct)
    monkeypatch.setattr(gamepi_brightness, "_STATUS_CACHE_TTL", 60.0)

    async def scenario() -> None:
        gamepi_brightness.brightness_status_payload()
        assert reads["count"] == 1
        await module.refresh()
        assert store.snapshot()["gamepi.brightness"]["int_value"] == 150
        assert reads["count"] == 2

    asyncio.run(scenario())


def test_brightness_status_is_cached(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_direct() -> dict[str, int | bool | str]:
        calls["count"] += 1
        return {"available": True, "mode": "software", "level": 150, "max": 255}

    monkeypatch.setattr(gamepi_brightness, "_direct_brightness_status", fake_direct)
    monkeypatch.setattr(gamepi_brightness, "_STATUS_CACHE_TTL", 60.0)

    first = gamepi_brightness.brightness_status_payload()
    second = gamepi_brightness.brightness_status_payload()

    assert first == second
    assert calls["count"] == 1


def test_adjust_brightness_invalidates_cache_and_uses_sudo(monkeypatch) -> None:
    calls: list[list[str]] = []
    direct_reads = {"count": 0, "level": 150}

    def fake_direct() -> dict[str, int | bool | str]:
        direct_reads["count"] += 1
        return {
            "available": True,
            "mode": "software",
            "level": direct_reads["level"],
            "max": 255,
        }

    def fake_cli(*args: str) -> dict[str, int | bool | str]:
        calls.append(list(args))
        return {"available": True, "mode": "software", "level": 170, "max": 255, "ok": True}

    monkeypatch.setattr(gamepi_brightness, "_direct_brightness_status", fake_direct)
    monkeypatch.setattr(gamepi_brightness, "_run_brightness_cli", fake_cli)

    gamepi_brightness.brightness_status_payload()
    assert direct_reads["count"] == 1
    payload = gamepi_brightness.adjust_brightness_payload(10)
    direct_reads["level"] = 165
    refreshed = gamepi_brightness.brightness_status_payload()

    assert payload["level"] == 170
    assert refreshed["level"] == 165
    assert direct_reads["count"] == 2
    assert calls == [["--delta", "10"]]


def test_quiet_access_paths_filter() -> None:
    from midijuggler.web.server import _QuietAccessPathsFilter

    quiet = _QuietAccessPathsFilter()
    logger = logging.getLogger("test.gamepi.access")

    assert quiet.filter(
        logger.makeRecord(
            logger.name,
            logging.INFO,
            __file__,
            1,
            '127.0.0.1 [06/Jul/2026:12:00:00 +0000] "GET /api/gamepi/brightness HTTP/1.1" 200 123 "-" "curl"',
            (),
            None,
        )
    ) is False
    assert quiet.filter(
        logger.makeRecord(
            logger.name,
            logging.INFO,
            __file__,
            1,
            '127.0.0.1 [06/Jul/2026:12:00:00 +0000] "POST /api/gamepi/brightness HTTP/1.1" 200 123 "-" "curl"',
            (),
            None,
        )
    ) is True
