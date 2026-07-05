#!/bin/sh
set -eu

echo "handing off framebuffer from splash to X" >&2

systemctl stop gamepi-splash.service 2>/dev/null || true
killall fbi 2>/dev/null || true

wait_loops=0
while pgrep -x fbi >/dev/null 2>&1 && [ "$wait_loops" -lt 50 ]; do
  sleep 0.1
  wait_loops=$((wait_loops + 1))
done

if pgrep -x fbi >/dev/null 2>&1; then
  echo "fbi still running after handoff wait" >&2
  killall -9 fbi 2>/dev/null || true
  sleep 0.2
fi

rm -f /run/gamepi-splash.pid
