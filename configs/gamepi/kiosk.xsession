#!/bin/sh
export FRAMEBUFFER=/dev/fb0
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-${HOME}/.Xauthority}"

xsession_pid=$$

(
  while sleep 2; do
    if [ -S /tmp/.X11-unix/X0 ]; then
      continue
    fi
    kill -TERM "$xsession_pid" 2>/dev/null || true
    exit 0
  done
) &

while [ ! -S /tmp/.X11-unix/X0 ]; do
  sleep 0.1
done

/opt/midijuggler/app/scripts/gamepi-disable-blanking.sh

if command -v unclutter >/dev/null 2>&1; then
  unclutter -idle 0 &
fi

if command -v xset >/dev/null 2>&1; then
  xset s off
  xset -dpms
  xset s noblank
  xset dpms force on
fi

(
  while sleep 3; do
    /opt/midijuggler/app/scripts/gamepi-disable-blanking.sh
  done
) &

CHROMIUM_USER_DATA_DIR="${GAMEPI_CHROMIUM_USER_DATA_DIR:-${HOME:-/home/dietpi}/.cache/midijuggler-kiosk}"
CLEAR_SCRIPT="${GAMEPI_CLEAR_CHROMIUM_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-clear-chromium-cache.sh}"
if [ -x "$CLEAR_SCRIPT" ]; then
  GAMEPI_CHROMIUM_USER_DATA_DIR="$CHROMIUM_USER_DATA_DIR" "$CLEAR_SCRIPT"
fi

WAIT_SCRIPT="${MIDIJUGGLER_WAIT_SCRIPT:-/opt/midijuggler/app/scripts/wait-for-midijuggler-web.sh}"
if [ -x "$WAIT_SCRIPT" ]; then
  "$WAIT_SCRIPT" || echo "web UI wait failed; starting Chromium anyway" >&2
fi

exec chromium --kiosk --noerrdialogs --disable-infobars \
  --disable-features=Translate,IdleDetection \
  --disable-background-timer-throttling \
  --disable-renderer-backgrounding \
  --user-data-dir="$CHROMIUM_USER_DATA_DIR" \
  --disk-cache-size=1 \
  --lang=de \
  --window-size=240,240 \
  http://127.0.0.1:8080/static/clock-gamepi.html
