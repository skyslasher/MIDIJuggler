#!/bin/sh
set -eu

timeout="${GAMEPI_BOOT_SETTLE_TIMEOUT:-180}"
interval="${GAMEPI_BOOT_SETTLE_INTERVAL:-0.5}"

echo "waiting for boot to settle (timeout ${timeout}s)" >&2

if command -v systemctl >/dev/null 2>&1; then
  systemctl is-system-running --wait 2>/dev/null || true
fi

deadline=$(($(date +%s) + timeout))
while [ "$(date +%s)" -lt "$deadline" ]; do
  pending="$(systemctl list-jobs --no-legend 2>/dev/null | wc -l | tr -d ' ')"
  if [ "${pending:-1}" = "0" ]; then
    echo "no pending systemd jobs" >&2
    exit 0
  fi
  sleep "$interval"
done

echo "timed out waiting for pending jobs; continuing" >&2
exit 0
