#!/bin/sh
# Recover a black GamePi panel: unblank fb0, verify kiosk stack, restart when needed.
#
# When invoked directly (user recovery), restarts the kiosk unless the full stack
# is healthy after blanking fixes. Reload scripts set GAMEPI_RECOVER_FORCE=0 for
# a lighter check that still restarts kiosk when X or Chromium is missing.

fb_device="${GAMEPI_FB_DEVICE:-/dev/fb0}"
disable_script="${GAMEPI_BLANKING_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-disable-blanking.sh}"
handoff_script="${GAMEPI_FB_HANDOFF_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-fb-handoff.sh}"
health_script="${GAMEPI_DISPLAY_HEALTH_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-display-health.sh}"
wait_timeout="${GAMEPI_RECOVER_X_WAIT:-45}"
settle_timeout="${GAMEPI_RECOVER_X_SETTLE:-5}"
x_display="${GAMEPI_X_DISPLAY:-:0}"
x_user="${GAMEPI_X_USER:-dietpi}"

if [ -z "${GAMEPI_RECOVER_FORCE:-}" ]; then
  case "$0" in
    *gamepi-recover-display.sh)
      GAMEPI_RECOVER_FORCE=1
      ;;
    *)
      GAMEPI_RECOVER_FORCE=0
      ;;
  esac
fi

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
    if [ -x "$handoff_script" ]; then
      GAMEPI_FB_DEVICE="$fb_device" GAMEPI_FB_HANDOFF_DELAY="${GAMEPI_FB_HANDOFF_DELAY:-0.2}" \
        "$handoff_script"
    fi
    return 0
  fi

  return 1
}

display_health_ok() {
  if [ ! -x "$health_script" ]; then
    x_socket_ready
    return $?
  fi

  GAMEPI_FB_DEVICE="$fb_device" \
    GAMEPI_X_DISPLAY="$x_display" \
    GAMEPI_X_SOCKET="${GAMEPI_X_SOCKET:-$(x_socket_path)}" \
    GAMEPI_DIAGNOSE=1 \
    "$health_script"
}

wait_for_health() {
  deadline=$(($(date +%s) + wait_timeout))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    apply_blanking_fixes || true
    if display_health_ok; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_for_x_settle() {
  deadline=$(($(date +%s) + settle_timeout))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    apply_blanking_fixes || true
    if x_socket_ready; then
      return 0
    fi
    sleep 1
  done
  return 1
}

restart_kiosk() {
  reason="$1"
  echo "$reason" >&2
  if systemctl is-active --quiet gamepi-kiosk.service; then
    systemctl restart gamepi-kiosk.service
  elif systemctl is-enabled gamepi-kiosk.service >/dev/null 2>&1; then
    systemctl start gamepi-kiosk.service
  else
    echo "gamepi-kiosk.service is not enabled" >&2
    return 1
  fi
}

echo "checking GamePi display health..." >&2
apply_blanking_fixes || true

if display_health_ok; then
  echo "display healthy on ${x_display}" >&2
  exit 0
fi

if [ "$GAMEPI_RECOVER_FORCE" = "1" ]; then
  if restart_kiosk "recover: restarting gamepi-kiosk.service"; then
    if wait_for_health; then
      echo "display recovered after kiosk restart on ${x_display}" >&2
      exit 0
    fi
    echo "display still unhealthy after kiosk restart (${wait_timeout}s)" >&2
    display_health_ok || true
    exit 1
  fi
  exit 1
fi

if wait_for_x_settle && display_health_ok; then
  echo "display recovered on ${x_display}" >&2
  exit 0
fi

if x_socket_ready && ! pgrep -x chromium >/dev/null 2>&1; then
  if restart_kiosk "X running but Chromium missing; restarting gamepi-kiosk.service"; then
    if wait_for_health; then
      echo "display recovered after kiosk restart on ${x_display}" >&2
      exit 0
    fi
  fi
elif ! x_socket_ready; then
  if pgrep -x Xorg >/dev/null 2>&1 || pgrep -x chromium >/dev/null 2>&1; then
    restart_reason="kiosk processes alive but X socket missing; restarting gamepi-kiosk.service"
  else
    restart_reason="kiosk active but X socket missing; restarting gamepi-kiosk.service"
  fi
  if restart_kiosk "$restart_reason"; then
    if wait_for_health; then
      echo "display recovered after kiosk start on ${x_display}" >&2
      exit 0
    fi
  fi
else
  apply_blanking_fixes || true
  if display_health_ok; then
    echo "display recovered on ${x_display}" >&2
    exit 0
  fi
fi

echo "display still unavailable after recovery; try: sudo reboot" >&2
display_health_ok || true
exit 1
