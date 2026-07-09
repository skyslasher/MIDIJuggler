import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer
from types import SimpleNamespace
from pathlib import Path

from midijuggler.clock import ClockBpmTracker
from midijuggler.config import parse_config
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface


def _interface() -> WebInterface:
    config = parse_config({"master_clock": {"enabled": True}})
    bus = EventBus()
    return WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        MasterClock(config.master_clock, bus),
    )


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
    from midijuggler.web.gamepi_system import request_reboot

    request = SimpleNamespace(remote="203.0.113.1")
    with pytest.raises(PermissionError, match="localhost"):
        request_reboot(request)


def test_gamepi_reboot_uses_sudo_wrapper(monkeypatch, tmp_path: Path) -> None:
    from midijuggler.web import gamepi_system

    script = tmp_path / "gamepi-reboot.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(gamepi_system, "_reboot_script", lambda: script)

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(gamepi_system.subprocess, "run", fake_run)

    payload = gamepi_system.request_reboot(SimpleNamespace(remote="127.0.0.1"))

    assert payload == {"ok": True}
    assert calls == [["sudo", "-n", str(script)]]


def test_gamepi_keep_awake_rejects_non_localhost() -> None:
    from midijuggler.web.gamepi_system import request_display_keep_awake

    request = SimpleNamespace(remote="203.0.113.1")
    with pytest.raises(PermissionError, match="localhost"):
        request_display_keep_awake(request)


def test_gamepi_keep_awake_uses_sudo_wrapper(monkeypatch, tmp_path: Path) -> None:
    from midijuggler.web import gamepi_system

    script = tmp_path / "gamepi-disable-blanking.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(gamepi_system, "_blanking_script", lambda: script)

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(gamepi_system.subprocess, "run", fake_run)

    payload = gamepi_system.request_display_keep_awake(SimpleNamespace(remote="127.0.0.1"))

    assert payload == {"ok": True}
    assert calls == [["sudo", "-n", str(script)]]

    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "src/midijuggler/web/static/clock-gamepi.html"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert 'width=240' in text
    assert "width: 240px" in text
    assert "--inset-right" in text
    assert "Neustart?" in text
    assert "FACE_BUTTON_BPM_BY_CODE" in text
    assert 'KeyX: "bpm_huge_up"' in text
    assert 'KeyY: "bpm_down"' in text
    assert 'KeyB: "bpm_huge_down"' in text
    assert 'a: "bpm_up"' in text
    assert "handleBpmKey" not in text
    assert '"Klick an"' not in text
    assert '"Puls aus"' not in text
    assert 'id="btn-click">Klick</button>' in text
    assert 'id="btn-flash">Puls</button>' in text
    assert "text-align: center" in text
    assert "brightnessTrack," not in text
    assert "/api/gamepi/keep-awake" in text
    assert "startDisplayKeepAwake" in text
    assert "KEEP_AWAKE_INTERVAL_MS = 15000" in text
