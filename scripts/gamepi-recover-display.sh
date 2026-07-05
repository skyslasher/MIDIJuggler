#!/bin/sh
# Recover a black GamePi panel: unblank fb0 and refresh X11 blanking settings.

set -eu

fb_device="${GAMEPI_FB_DEVICE:-/dev/fb0}"
disable_script="${GAMEPI_BLANKING_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-disable-blanking.sh}"

if [ -x "$disable_script" ]; then
  GAMEPI_FB_DEVICE="$fb_device" "$disable_script"
fi

if [ -S /tmp/.X11-unix/X0 ] && command -v xset >/dev/null 2>&1; then
  DISPLAY=:0 xset s off 2>/dev/null || true
  DISPLAY=:0 xset -dpms 2>/dev/null || true
  DISPLAY=:0 xset s noblank 2>/dev/null || true
  echo "X11 blanking disabled on :0" >&2
  exit 0
fi

if systemctl is-active --quiet gamepi-kiosk.service; then
  echo "kiosk active but X socket missing; restarting gamepi-kiosk.service" >&2
  systemctl restart gamepi-kiosk.service
  exit 0
fi

echo "starting gamepi-kiosk.service" >&2
systemctl start gamepi-kiosk.service
