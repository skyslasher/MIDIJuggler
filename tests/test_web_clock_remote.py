import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import parse_config
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface


def _clock_interface(*, enabled: bool = True, bpm: float = 120.0) -> WebInterface:
    config = parse_config(
        {
            "master_clock": {
                "enabled": enabled,
                "bpm": bpm,
                "bpm_min": 40.0,
                "bpm_max": 240.0,
            }
        }
    )
    return WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )


def test_apply_clock_trigger_bpm_up_increases_bpm_direct_fallback() -> None:
    interface = _clock_interface(bpm=120.0)

    async def scenario() -> None:
        result = await interface.apply_clock_trigger("bpm_up")
        await interface.master_clock.flush_bpm_notifications()
        assert result["master_clock"]["bpm"] == pytest.approx(121.0)
        assert interface.master_clock.config.bpm == pytest.approx(121.0)

    asyncio.run(scenario())


def test_apply_clock_trigger_rejects_unknown_point() -> None:
    interface = _clock_interface()

    with pytest.raises(ValueError, match="unknown clock trigger point"):
        asyncio.run(interface.apply_clock_trigger("invalid"))


def test_apply_clock_trigger_rejects_disabled_master_clock() -> None:
    interface = _clock_interface(enabled=False)

    with pytest.raises(ValueError, match="master clock is disabled"):
        asyncio.run(interface.apply_clock_trigger("bpm_up"))


def test_apply_clock_trigger_click_toggle_broadcasts_click_enabled_status() -> None:
    config = parse_config({"master_clock": {"enabled": True, "click_enabled": False}})
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )
    payloads: list[dict] = []

    async def capture(payload: dict) -> None:
        payloads.append(payload)

    interface._broadcast_payload = capture  # type: ignore[method-assign]
    interface._websockets = [object()]  # noqa: SLF001

    async def scenario() -> None:
        result = await interface.apply_clock_trigger("click_toggle")
        assert result["master_clock"]["click_enabled"] is True

    asyncio.run(scenario())

    status_payloads = [payload for payload in payloads if payload.get("type") == "status"]
    assert status_payloads
    assert status_payloads[-1]["payload"]["master_clock"]["click_enabled"] is True


def test_status_payload_includes_click_enabled() -> None:
    config = parse_config(
        {"master_clock": {"enabled": True, "click_enabled": True}}
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    payload = interface._status_payload()

    assert payload["master_clock"]["click_enabled"] is True


def test_status_payload_includes_bpm_steps() -> None:
    config = parse_config(
        {
            "master_clock": {
                "enabled": True,
                "bpm_step": 1.0,
                "bpm_huge_step": 5.0,
            }
        }
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    payload = interface._status_payload()

    assert payload["master_clock"]["bpm_step"] == pytest.approx(1.0)
    assert payload["master_clock"]["bpm_huge_step"] == pytest.approx(5.0)


def test_status_payload_includes_beat_flash_ms() -> None:
    config = parse_config(
        {"master_clock": {"enabled": True, "beat_flash_ms": 80.0}}
    )
    interface = WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )

    payload = interface._status_payload()

    assert payload["master_clock"]["beat_flash_ms"] == pytest.approx(80.0)


def test_clock_trigger_http_endpoint() -> None:
    interface = _clock_interface(bpm=100.0)

    async def scenario() -> dict:
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/api/clock/trigger",
                json={"point": "bpm_up"},
            )
            assert response.status == 200
            return await response.json()

    payload = asyncio.run(scenario())
    assert payload["master_clock"]["bpm"] == pytest.approx(101.0)


def test_clock_trigger_http_rejects_unknown_point() -> None:
    interface = _clock_interface()

    async def scenario() -> tuple[int, str]:
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/api/clock/trigger",
                json={"point": "not_a_point"},
            )
            return response.status, await response.text()

    status, body = asyncio.run(scenario())
    assert status == 400
    assert "unknown clock trigger point" in body


def test_clock_remote_cors_on_options() -> None:
    interface = _clock_interface()

    async def scenario() -> dict[str, str]:
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.options("/api/clock/trigger")
            assert response.status == 204
            return {
                key: response.headers.get(key, "")
                for key in (
                    "Access-Control-Allow-Origin",
                    "Access-Control-Allow-Methods",
                    "Access-Control-Allow-Headers",
                )
            }

    headers = asyncio.run(scenario())
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert "POST" in headers["Access-Control-Allow-Methods"]
    assert "Content-Type" in headers["Access-Control-Allow-Headers"]


def test_clock_remote_cors_on_post_response() -> None:
    interface = _clock_interface()

    async def scenario() -> str:
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/api/clock/trigger",
                json={"point": "start"},
            )
            assert response.status == 200
            return response.headers.get("Access-Control-Allow-Origin", "")

    origin = asyncio.run(scenario())
    assert origin == "*"
