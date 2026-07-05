#!/bin/sh
# Safe post-deploy reload: restart midijuggler without tearing down X by default.

set -eu

app_root="${MIDIJUGGLER_APP_ROOT:-/opt/midijuggler/app}"
wait_script="${MIDIJUGGLER_WAIT_SCRIPT:-${app_root}/scripts/wait-for-midijuggler-web.sh}"
recover_script="${GAMEPI_RECOVER_DISPLAY_SCRIPT:-${app_root}/scripts/gamepi-recover-display.sh}"

echo "Restarting midijuggler.service..." >&2
systemctl restart midijuggler.service

if [ -x "$wait_script" ]; then
  echo "Waiting for MIDIJuggler web UI..." >&2
  "$wait_script"
fi

if [ "${GAMEPI_RELOAD_KIOSK:-0}" = "1" ] && systemctl is-active --quiet gamepi-kiosk.service; then
  echo "Restarting gamepi-kiosk.service (GAMEPI_RELOAD_KIOSK=1)..." >&2
  systemctl restart gamepi-kiosk.service
  if [ -x "$recover_script" ]; then
    sleep 2
    "$recover_script"
  fi
else
  echo "Leaving gamepi-kiosk.service running (set GAMEPI_RELOAD_KIOSK=1 to restart UI)." >&2
  if [ -x "$recover_script" ]; then
    "$recover_script"
  fi
fi

if systemctl is-enabled gamepi-blanking-watch.service >/dev/null 2>&1; then
  systemctl restart gamepi-blanking-watch.service 2>/dev/null || true
fi

echo "Done. Reboot for a full splash/boot reset if the panel stays black." >&2
