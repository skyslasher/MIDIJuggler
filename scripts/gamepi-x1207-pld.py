#!/usr/bin/env python3
"""Shut down cleanly when the X1207 UPS reports mains power loss."""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

LOGGER = logging.getLogger("gamepi-x1207-pld")


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _pld_gpio() -> int:
    return int(os.environ.get("GAMEPI_X1207_PLD_GPIO", "6"))


def _poweroff_delay_s() -> float:
    return float(os.environ.get("GAMEPI_X1207_POWEROFF_DELAY", "5"))


def _autodetect_gpiochip(pld_gpio: int) -> str:
    import gpiod

    last_error: Exception | None = None
    for chip_path in sorted(Path("/dev").glob("gpiochip*"), key=lambda path: path.name):
        try:
            with gpiod.request_lines(
                str(chip_path),
                consumer="gamepi-x1207-pld-probe",
                config={
                    pld_gpio: gpiod.LineSettings(direction=gpiod.line.Direction.INPUT),
                },
            ) as request:
                request.get_values()
            return str(chip_path)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(
        f"Could not open PLD GPIO {pld_gpio} on any /dev/gpiochip* (last error: {last_error})"
    )


def _resolve_gpiochip(pld_gpio: int) -> str:
    chip = os.environ.get("GAMEPI_X1207_GPIOCHIP", "auto").strip()
    if chip and chip != "auto":
        return chip
    detected = _autodetect_gpiochip(pld_gpio)
    LOGGER.info("auto-detected gpiochip for PLD GPIO %s: %s", pld_gpio, detected)
    return detected


def _mains_ok(request) -> bool:
    import gpiod

    return request.get_values()[0] == gpiod.line.Value.ACTIVE


def main() -> int:
    _configure_logging()
    pld_gpio = _pld_gpio()
    delay_s = _poweroff_delay_s()

    try:
        import gpiod
    except ImportError:
        LOGGER.error("python3-libgpiod is required (apt install python3-libgpiod)")
        return 1

    try:
        chip_path = _resolve_gpiochip(pld_gpio)
    except RuntimeError as exc:
        LOGGER.error("%s", exc)
        return 1

    LOGGER.info(
        "monitoring X1207 PLD on %s line %s (poweroff after %.1fs without mains)",
        chip_path,
        pld_gpio,
        delay_s,
    )

    try:
        with gpiod.request_lines(
            chip_path,
            consumer="gamepi-x1207-pld",
            config={
                pld_gpio: gpiod.LineSettings(direction=gpiod.line.Direction.INPUT),
            },
        ) as request:
            while True:
                if _mains_ok(request):
                    time.sleep(0.2)
                    continue

                LOGGER.warning("mains power lost — waiting %.1fs before shutdown", delay_s)
                deadline = time.monotonic() + delay_s
                while time.monotonic() < deadline:
                    if _mains_ok(request):
                        LOGGER.info("mains power restored — shutdown cancelled")
                        break
                    time.sleep(0.1)
                else:
                    if not _mains_ok(request):
                        LOGGER.warning("mains still off — powering down")
                        subprocess.run(["systemctl", "poweroff"], check=False)
                        return 0
    except Exception:
        LOGGER.exception("X1207 PLD monitor failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
