#!/bin/sh
set -eu

completed_flag="${GAMEPI_SPLASH_COMPLETED_FLAG:-/run/gamepi-splash-completed}"

had_splash=false
if [ -f /run/gamepi-splash-hold ] || pgrep -x fbi >/dev/null 2>&1; then
  had_splash=true
fi

if [ "$had_splash" = true ]; then
  echo "handing off framebuffer from splash to X" >&2
else
  echo "no active splash; skipping framebuffer handoff" >&2
fi

rm -f /run/gamepi-splash-hold

systemctl stop --no-block gamepi-splash.service 2>/dev/null || true
killall fbi 2>/dev/null || true

wait_loops=0
while pgrep -x fbi >/dev/null 2>&1 && [ "$wait_loops" -lt 50 ]; do
  sleep 0.1
  wait_loops=$((wait_loops + 1))
done

if pgrep -x fbi >/dev/null 2>&1; then
  echo "fbi still running after handoff wait" >&2
  killall -9 fbi 2>/dev/null || true
  sleep 0.2
fi

if [ "$had_splash" = true ]; then
  handoff_script="${GAMEPI_FB_HANDOFF_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-fb-handoff.sh}"
  if [ -x "$handoff_script" ]; then
    GAMEPI_FB_DEVICE="${GAMEPI_FB_DEVICE:-/dev/fb0}" "$handoff_script"
  fi
fi

: >"$completed_flag"

rm -f /run/gamepi-splash.pid
