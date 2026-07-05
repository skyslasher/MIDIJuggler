#!/bin/sh
set -eu

url="${MIDIJUGGLER_WAIT_URL:-http://127.0.0.1:8080/static/clock-remote.html}"
timeout="${MIDIJUGGLER_WAIT_TIMEOUT:-45}"
interval="${MIDIJUGGLER_WAIT_INTERVAL:-0.5}"

deadline=$(($(date +%s) + timeout))
last_log=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  if curl -fsS --connect-timeout 2 --max-time 3 -o /dev/null "$url"; then
    echo "web UI ready: ${url}" >&2
    exit 0
  fi
  now=$(date +%s)
  if [ $((now - last_log)) -ge 10 ]; then
    echo "still waiting for ${url}" >&2
    last_log=$now
  fi
  sleep "$interval"
done

echo "timed out waiting for ${url}" >&2
exit 1
