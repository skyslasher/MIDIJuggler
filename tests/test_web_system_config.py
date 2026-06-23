import asyncio
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import parse_config
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface


def _web_interface() -> WebInterface:
    config = parse_config({"adapters": {"osc": {"enabled": True}}})
    return WebInterface(
        config,
        EventBus(),
        ClockBpmTracker(),
        MasterClock(config.master_clock, EventBus()),
    )


def test_system_config_endpoint_reports_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_interface = _web_interface()
    monkeypatch.setattr("midijuggler.web.server.get_hostname", lambda: "stage-pi")
    monkeypatch.setattr(
        "midijuggler.web.server.can_set_hostname",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "midijuggler.web.server.can_restart_service",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "midijuggler.web.server.capability_message",
        AsyncMock(return_value="sudoers not configured"),
    )

    async def scenario() -> dict:
        app = web_interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.get("/api/system")
            assert response.status == 200
            return await response.json()

    payload = asyncio.run(scenario())
    assert payload["hostname"] == "stage-pi"
    assert payload["can_set_hostname"] is True
    assert payload["can_restart_service"] is False


def test_set_system_hostname_refreshes_mdns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_interface = _web_interface()
    refresh = AsyncMock()
    web_interface.rtp_midi_manager = type(
        "Manager",
        (),
        {"refresh_announcements": refresh},
    )()
    monkeypatch.setattr(
        "midijuggler.web.server.can_set_hostname",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "midijuggler.web.server.apply_hostname",
        AsyncMock(return_value=("stage-pi", True)),
    )

    async def scenario() -> dict:
        app = web_interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/api/system/hostname",
                json={"hostname": "stage-pi"},
            )
            assert response.status == 200
            return await response.json()

    payload = asyncio.run(scenario())
    assert payload["hostname"] == "stage-pi"
    assert payload["mdns_refreshed"] is True
    refresh.assert_awaited_once()


def test_set_system_hostname_rejects_invalid_name() -> None:
    web_interface = _web_interface()

    async def scenario() -> tuple[int, str]:
        app = web_interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/api/system/hostname",
                json={"hostname": "not valid"},
            )
            return response.status, await response.text()

    status, body = asyncio.run(scenario())
    assert status == 400
    assert "hostname" in body.lower()


def test_restart_service_endpoint_schedules_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_interface = _web_interface()
    restart_mock = AsyncMock()
    monkeypatch.setattr(
        "midijuggler.web.server.can_restart_service",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr("midijuggler.web.server.restart_service", restart_mock)
    monkeypatch.setattr("midijuggler.web.server.asyncio.sleep", AsyncMock())

    async def scenario() -> dict:
        app = web_interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post("/api/system/restart")
            assert response.status == 200
            payload = await response.json()
            await asyncio.sleep(0)
            return payload

    payload = asyncio.run(scenario())
    assert payload["restarting"] is True
    restart_mock.assert_awaited_once()


def test_status_payload_includes_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_interface = _web_interface()
    monkeypatch.setattr("midijuggler.web.server.get_hostname", lambda: "stage-pi")
    payload = web_interface._status_payload()
    assert payload["hostname"] == "stage-pi"
