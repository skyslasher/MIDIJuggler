#!/bin/sh
set -eu

url="${MIDIJUGGLER_WAIT_URL:-http://127.0.0.1:8080/static/clock-remote.html}"
timeout="${MIDIJUGGLER_WAIT_TIMEOUT:-60}"
interval="${MIDIJUGGLER_WAIT_INTERVAL:-0.5}"

deadline=$(($(date +%s) + timeout))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if curl -fsS -o /dev/null "$url"; then
    exit 0
  fi
  sleep "$interval"
done

echo "timed out waiting for ${url}" >&2
exit 1
