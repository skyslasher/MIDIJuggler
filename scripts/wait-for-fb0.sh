#!/bin/sh
set -eu

fb_device="${GAMEPI_FB_DEVICE:-/dev/fb0}"
timeout="${GAMEPI_FB_WAIT_TIMEOUT:-30}"
interval="${GAMEPI_FB_WAIT_INTERVAL:-0.2}"

deadline=$(($(date +%s) + timeout))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if [ -c "$fb_device" ]; then
    exit 0
  fi
  sleep "$interval"
done

echo "timed out waiting for ${fb_device}" >&2
exit 1
