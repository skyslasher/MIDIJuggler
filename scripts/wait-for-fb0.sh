#!/bin/sh
set -eu

fb_device="${GAMEPI_FB_DEVICE:-/dev/fb0}"
timeout="${GAMEPI_FB_WAIT_TIMEOUT:-45}"
interval="${GAMEPI_FB_WAIT_INTERVAL:-0.2}"

echo "waiting for ${fb_device} (timeout ${timeout}s)" >&2

deadline=$(($(date +%s) + timeout))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if [ -c "$fb_device" ]; then
    echo "${fb_device} ready" >&2
    exit 0
  fi
  sleep "$interval"
done

echo "timed out waiting for ${fb_device}" >&2
exit 1
