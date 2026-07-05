#!/bin/sh
# Safe post-deploy reload: do not restart boot-only splash/kiosk-ready units on a live session.

set -eu

app_root="${MIDIJUGGLER_APP_ROOT:-/opt/midijuggler/app}"
wait_script="${MIDIJUGGLER_WAIT_SCRIPT:-${app_root}/scripts/wait-for-midijuggler-web.sh}"

echo "Restarting midijuggler.service..." >&2
systemctl restart midijuggler.service

if systemctl is-active --quiet gamepi-kiosk.service; then
  if [ -x "$wait_script" ]; then
    echo "Waiting for MIDIJuggler web UI before kiosk restart..." >&2
    "$wait_script"
  else
    delay="${GAMEPI_RELOAD_KIOSK_DELAY:-5}"
    echo "Wait script missing; sleeping ${delay}s before kiosk restart..." >&2
    sleep "$delay"
  fi
  echo "Restarting gamepi-kiosk.service..." >&2
  systemctl restart gamepi-kiosk.service
else
  echo "gamepi-kiosk.service not active; leaving splash/boot units untouched." >&2
  echo "Reboot to replay splash and kiosk boot sequence." >&2
fi

if systemctl is-enabled gamepi-blanking-watch.service >/dev/null 2>&1; then
  echo "Restarting gamepi-blanking-watch.service..." >&2
  systemctl restart gamepi-blanking-watch.service
fi

echo "Done. For a full display stack reset, reboot instead." >&2
