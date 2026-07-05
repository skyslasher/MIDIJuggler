#!/bin/sh
set -eu

iface="${GAMEPI_NETWORK_IF:-eth0}"
timeout="${GAMEPI_NETWORK_WAIT_TIMEOUT:-120}"
interval="${GAMEPI_NETWORK_WAIT_INTERVAL:-0.5}"
ifup_unit="ifup@${iface}.service"

echo "waiting for ${iface} (timeout ${timeout}s)" >&2

if systemctl list-unit-files "$ifup_unit" 2>/dev/null | grep -qF "$ifup_unit"; then
  deadline=$(($(date +%s) + timeout))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    state="$(systemctl is-active "$ifup_unit" 2>/dev/null || true)"
    case "$state" in
      active|failed|inactive)
        echo "${ifup_unit} is ${state}" >&2
        break
        ;;
    esac
    sleep "$interval"
  done
fi

deadline=$(($(date +%s) + timeout))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if ip -4 -o addr show dev "$iface" 2>/dev/null | grep -q ' inet '; then
    echo "${iface} has IPv4" >&2
    exit 0
  fi
  sleep "$interval"
done

echo "timed out waiting for ${iface}; continuing" >&2
exit 0
