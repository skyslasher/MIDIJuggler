#!/bin/sh
set -eu

timeout="${GAMEPI_BOOT_SETTLE_TIMEOUT:-60}"

echo "waiting for boot to settle (timeout ${timeout}s)" >&2

if ! command -v systemctl >/dev/null 2>&1; then
  exit 0
fi

deadline=$(($(date +%s) + timeout))
while [ "$(date +%s)" -lt "$deadline" ]; do
  state="$(systemctl is-system-running 2>/dev/null || true)"
  case "$state" in
    running|degraded)
      echo "system is ${state}" >&2
      exit 0
      ;;
  esac
  sleep 0.5
done

echo "timed out waiting for system running state; continuing" >&2
exit 0
