#!/bin/sh
# Verify GamePi systemd units use the simple splash -> startx kiosk flow.
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
fail=0

check_contains() {
  file="$1"
  needle="$2"
  desc="$3"
  if grep -q "$needle" "$file"; then
    echo "ok: $desc"
  else
    echo "FAIL: $desc" >&2
    fail=1
  fi
}

check_contains "$repo_root/systemd/gamepi-kiosk.service" \
  'gamepi-start-kiosk.sh' \
  'gamepi-kiosk.service uses gamepi-start-kiosk.sh directly'

check_contains "$repo_root/systemd/gamepi-splash.service" \
  'GAMEPI_ALLOW_SETTERM=1' \
  'gamepi-splash.service enables setterm before splash'

check_contains "$repo_root/systemd/gamepi-kiosk-ready.service" \
  'gamepi-splash-stop.sh' \
  'gamepi-kiosk-ready.service stops splash after web UI is ready'

if grep -q 'gamepi-launch-kiosk.sh' "$repo_root/systemd/gamepi-kiosk.service"; then
  echo "FAIL: gamepi-kiosk.service must not use gamepi-launch-kiosk.sh wrapper" >&2
  fail=1
else
  echo "ok: gamepi-kiosk.service has no launch wrapper"
fi

if [ "$fail" -ne 0 ]; then
  exit 1
fi

echo "all GamePi systemd checks passed"
