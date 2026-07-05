#!/bin/sh
# Safe post-deploy reload: do not restart boot-only splash/kiosk-ready units on a live session.

set -eu

app_root="${MIDIJUGGLER_APP_ROOT:-/opt/midijuggler/app}"

echo "Restarting midijuggler.service..." >&2
systemctl restart midijuggler.service

if systemctl is-enabled gamepi-blanking-watch.service >/dev/null 2>&1; then
  echo "Restarting gamepi-blanking-watch.service..." >&2
  systemctl restart gamepi-blanking-watch.service
fi

if systemctl is-active --quiet gamepi-kiosk.service; then
  echo "Restarting gamepi-kiosk.service..." >&2
  systemctl restart gamepi-kiosk.service
else
  echo "gamepi-kiosk.service not active; leaving splash/boot units untouched." >&2
  echo "Reboot to replay splash and kiosk boot sequence." >&2
fi

echo "Done. For a full display stack reset, reboot instead." >&2
