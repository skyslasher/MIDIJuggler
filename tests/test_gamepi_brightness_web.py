from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from midijuggler.web import gamepi_brightness
from midijuggler.web.server import _QuietAccessPathsFilter


@pytest.fixture(autouse=True)
def reset_brightness_cache() -> None:
    gamepi_brightness._invalidate_status_cache()
    yield
    gamepi_brightness._invalidate_status_cache()


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
