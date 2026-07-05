#!/bin/sh
# Recover a black GamePi panel: unblank fb0 and refresh X11 blanking settings.

fb_device="${GAMEPI_FB_DEVICE:-/dev/fb0}"
disable_script="${GAMEPI_BLANKING_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-disable-blanking.sh}"
wait_timeout="${GAMEPI_RECOVER_X_WAIT:-45}"

apply_blanking_fixes() {
  if [ -x "$disable_script" ]; then
    GAMEPI_FB_DEVICE="$fb_device" "$disable_script"
  fi

  if [ -S /tmp/.X11-unix/X0 ] && command -v xset >/dev/null 2>&1; then
    DISPLAY=:0 xset s off 2>/dev/null || true
    DISPLAY=:0 xset -dpms 2>/dev/null || true
    DISPLAY=:0 xset s noblank 2>/dev/null || true
    return 0
  fi

  return 1
}

wait_for_x_socket() {
  deadline=$(($(date +%s) + wait_timeout))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if apply_blanking_fixes; then
      return 0
    fi
    sleep 1
  done
  return 1
}

apply_blanking_fixes || true

if apply_blanking_fixes; then
  echo "display recovered on :0" >&2
  exit 0
fi

if systemctl is-active --quiet gamepi-kiosk.service; then
  echo "kiosk active but X socket missing; restarting gamepi-kiosk.service" >&2
  systemctl restart gamepi-kiosk.service
elif systemctl is-enabled gamepi-kiosk.service >/dev/null 2>&1; then
  echo "starting gamepi-kiosk.service" >&2
  systemctl start gamepi-kiosk.service
else
  echo "gamepi-kiosk.service is not enabled" >&2
  exit 1
fi

if wait_for_x_socket; then
  echo "display recovered after kiosk start" >&2
  exit 0
fi

echo "display still unavailable after ${wait_timeout}s; try: sudo reboot" >&2
exit 1
