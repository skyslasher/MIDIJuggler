#!/bin/sh
# Log kiosk stack health to stderr (journal) during X session startup.

set -eu

health_script="${GAMEPI_DISPLAY_HEALTH_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-display-health.sh}"
web_url="${GAMEPI_KIOSK_URL:-http://127.0.0.1:8080/static/clock-gamepi.html}"

echo "gamepi-kiosk: starting diagnostics for ${web_url}" >&2

if [ -x "$health_script" ]; then
  GAMEPI_KIOSK_URL="$web_url" GAMEPI_DIAGNOSE=1 "$health_script" || true
else
  echo "gamepi-kiosk: health script missing: ${health_script}" >&2
fi

if command -v curl >/dev/null 2>&1; then
  if curl -fsS --connect-timeout 2 --max-time 3 -o /dev/null "$web_url"; then
    echo "gamepi-kiosk: web UI reachable at ${web_url}" >&2
  else
    echo "gamepi-kiosk: web UI NOT reachable at ${web_url}" >&2
  fi
fi

if [ -S /tmp/.X11-unix/X0 ]; then
  echo "gamepi-kiosk: X socket present" >&2
else
  echo "gamepi-kiosk: X socket missing" >&2
fi

blank_path="/sys/class/graphics/fb0/blank"
if [ -r "$blank_path" ]; then
  echo "gamepi-kiosk: fb0 blank=$(cat "$blank_path" 2>/dev/null || echo ?)" >&2
fi
