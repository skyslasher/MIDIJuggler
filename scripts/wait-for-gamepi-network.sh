#!/bin/sh
set -eu

iface="${GAMEPI_NETWORK_IF:-eth0}"
timeout="${GAMEPI_NETWORK_WAIT_TIMEOUT:-45}"
interval="${GAMEPI_NETWORK_WAIT_INTERVAL:-0.5}"

echo "waiting for ${iface} IPv4 (timeout ${timeout}s)" >&2

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
