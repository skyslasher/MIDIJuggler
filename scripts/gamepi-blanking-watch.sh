#!/bin/sh
# Keep framebuffer, console, and X11 from re-enabling blanking on long-running kiosk use.

set -eu

interval="${GAMEPI_BLANKING_INTERVAL:-30}"
disable_script="${GAMEPI_BLANKING_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-disable-blanking.sh}"

while true; do
  if [ -x "$disable_script" ]; then
    GAMEPI_FB_DEVICE="${GAMEPI_FB_DEVICE:-/dev/fb0}" "$disable_script"
  fi

  if [ -S /tmp/.X11-unix/X0 ] && command -v xset >/dev/null 2>&1; then
    DISPLAY=:0 xset s off 2>/dev/null || true
    DISPLAY=:0 xset -dpms 2>/dev/null || true
    DISPLAY=:0 xset s noblank 2>/dev/null || true
  fi

  sleep "$interval"
done
