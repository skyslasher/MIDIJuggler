#!/bin/sh
# Keep framebuffer, console, and X11 from re-enabling blanking on long-running kiosk use.

set -eu

interval="${GAMEPI_BLANKING_INTERVAL:-15}"
disable_script="${GAMEPI_BLANKING_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-disable-blanking.sh}"

while true; do
  if [ -x "$disable_script" ]; then
    GAMEPI_FB_DEVICE="${GAMEPI_FB_DEVICE:-/dev/fb0}" \
    GAMEPI_X_DISPLAY="${GAMEPI_X_DISPLAY:-:0}" \
    GAMEPI_X_USER="${GAMEPI_X_USER:-dietpi}" \
    GAMEPI_ALLOW_SETTERM="${GAMEPI_ALLOW_SETTERM:-1}" \
      "$disable_script"
  fi

  sleep "$interval"
done
