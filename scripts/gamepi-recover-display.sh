#!/bin/sh
# Recover a black GamePi panel: unblank fb0 and refresh X11 blanking settings.

fb_device="${GAMEPI_FB_DEVICE:-/dev/fb0}"
disable_script="${GAMEPI_BLANKING_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-disable-blanking.sh}"
wait_timeout="${GAMEPI_RECOVER_X_WAIT:-45}"
settle_timeout="${GAMEPI_RECOVER_X_SETTLE:-5}"
x_display="${GAMEPI_X_DISPLAY:-:0}"
x_user="${GAMEPI_X_USER:-dietpi}"

x_socket_path() {
  display_num="${1:-${x_display#:}}"
  printf '/tmp/.X11-unix/X%s' "$display_num"
}

x_socket_ready() {
  socket="${GAMEPI_X_SOCKET:-$(x_socket_path)}"
  [ -S "$socket" ]
}

run_xset() {
  if ! command -v xset >/dev/null 2>&1; then
    return 0
  fi

  if [ "$(id -un)" != "$x_user" ] && id "$x_user" >/dev/null 2>&1; then
    runuser -u "$x_user" -- env DISPLAY="$x_display" xset s off 2>/dev/null || true
    runuser -u "$x_user" -- env DISPLAY="$x_display" xset -dpms 2>/dev/null || true
    runuser -u "$x_user" -- env DISPLAY="$x_display" xset s noblank 2>/dev/null || true
  else
    DISPLAY="$x_display" xset s off 2>/dev/null || true
    DISPLAY="$x_display" xset -dpms 2>/dev/null || true
    DISPLAY="$x_display" xset s noblank 2>/dev/null || true
  fi
}

apply_blanking_fixes() {
  if [ -x "$disable_script" ]; then
    GAMEPI_FB_DEVICE="$fb_device" "$disable_script"
  fi

  if x_socket_ready; then
    run_xset
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

wait_for_x_settle() {
  deadline=$(($(date +%s) + settle_timeout))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if apply_blanking_fixes; then
      return 0
    fi
    sleep 1
  done
  return 1
}

kiosk_process_alive() {
  pgrep -x Xorg >/dev/null 2>&1 || pgrep -x chromium >/dev/null 2>&1
}

if apply_blanking_fixes; then
  echo "display recovered on ${x_display}" >&2
  exit 0
fi

if wait_for_x_settle; then
  echo "display recovered on ${x_display}" >&2
  exit 0
fi

if systemctl is-active --quiet gamepi-kiosk.service; then
  if kiosk_process_alive; then
    echo "kiosk processes alive but X socket missing; restarting gamepi-kiosk.service" >&2
  else
    echo "kiosk active but X socket missing; restarting gamepi-kiosk.service" >&2
  fi
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
