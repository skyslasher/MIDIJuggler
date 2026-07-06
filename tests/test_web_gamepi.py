import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer

from midijuggler.config import parse_config
from midijuggler.eventbus import EventBus
from midijuggler.web.server import WebInterface


def _interface() -> WebInterface:
    config = parse_config({"master_clock": {"enabled": True}})
    return WebInterface(config, EventBus())


def test_gamepi_brightness_status_endpoint() -> None:
    interface = _interface()

    async def scenario() -> dict:
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.get("/api/gamepi/brightness")
            assert response.status == 200
            return await response.json()

    payload = asyncio.run(scenario())
    assert "available" in payload


def test_gamepi_brightness_adjust_requires_integer_delta() -> None:
    interface = _interface()

    async def scenario() -> int:
        app = interface.create_app()
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/api/gamepi/brightness",
                json={"delta": "nope"},
            )
            return response.status

    assert asyncio.run(scenario()) == 400


def test_gamepi_reboot_rejects_non_localhost() -> None:
    from aiohttp.test_utils import make_mocked_request

    from midijuggler.web.gamepi_system import request_reboot

    request = make_mocked_request("POST", "/api/gamepi/reboot", remote="203.0.113.1")
    with pytest.raises(PermissionError, match="localhost"):
        request_reboot(request)


def test_clock_gamepi_static_asset_exists() -> None:
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "src/midijuggler/web/static/clock-gamepi.html"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert 'width=240' in text
    assert "width: 240px" in text
    assert "--inset-right" in text
    assert "Neustart?" in text
    assert "FACE_BUTTON_BPM" in text
    assert 'y: "bpm_huge_up"' in text
    assert 'a: "bpm_up"' in text
    assert "handleBpmKey" not in text
    assert '"Klick an"' not in text
    assert '"Puls aus"' not in text
    assert 'id="btn-click">Klick</button>' in text
    assert 'id="btn-flash">Puls</button>' in text
    assert "text-align: center" in text
    assert "brightnessTrack," not in text
