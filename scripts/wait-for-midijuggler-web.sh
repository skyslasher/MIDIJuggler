#!/bin/sh
set -eu

url="${MIDIJUGGLER_WAIT_URL:-http://127.0.0.1:8080/static/clock-gamepi.html}"
timeout="${MIDIJUGGLER_WAIT_TIMEOUT:-45}"
interval="${MIDIJUGGLER_WAIT_INTERVAL:-0.5}"
service_wait="${MIDIJUGGLER_SERVICE_WAIT:-30}"

wait_for_midijuggler_service() {
  if ! command -v systemctl >/dev/null 2>&1; then
    return 0
  fi

  deadline=$(($(date +%s) + service_wait))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    state="$(systemctl is-active midijuggler.service 2>/dev/null || true)"
    case "$state" in
      active)
        return 0
        ;;
      failed|inactive|dead)
        if [ "$state" = "failed" ]; then
          echo "midijuggler.service is failed; waiting for web anyway" >&2
          return 0
        fi
        ;;
    esac
    sleep 1
  done

  echo "timed out waiting for midijuggler.service to become active (${service_wait}s); continuing" >&2
  return 0
}

wait_for_midijuggler_service

echo "waiting for ${url} (timeout ${timeout}s)" >&2

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
