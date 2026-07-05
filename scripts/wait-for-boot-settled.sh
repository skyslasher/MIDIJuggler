#!/bin/sh
set -eu

if ! command -v systemctl >/dev/null 2>&1; then
  exit 0
fi

state="$(systemctl is-system-running 2>/dev/null || true)"
case "$state" in
  running|degraded)
    echo "system is ${state}" >&2
    exit 0
    ;;
esac

timeout="${GAMEPI_BOOT_SETTLE_TIMEOUT:-30}"
echo "waiting for boot to settle (timeout ${timeout}s, now ${state:-unknown})" >&2

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
