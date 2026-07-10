#!/bin/sh
# Verify GamePi systemd units do not invoke setterm during kiosk handoff.
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
fail=0

check_no_setterm() {
  file="$1"
  if grep -q 'GAMEPI_ALLOW_SETTERM=1' "$file"; then
    echo "FAIL: $file still enables setterm" >&2
    fail=1
  else
    echo "ok: $file has no setterm enable"
  fi
}

check_no_setterm "$repo_root/systemd/gamepi-kiosk-ready.service"
check_no_setterm "$repo_root/systemd/gamepi-splash.service"

if grep -q 'GAMEPI_ALLOW_SETTERM=1' "$repo_root/scripts/gamepi-boot-splash.sh"; then
  echo "FAIL: gamepi-boot-splash.sh still enables setterm" >&2
  fail=1
else
  echo "ok: gamepi-boot-splash.sh has no setterm enable"
fi

if [ "$fail" -ne 0 ]; then
  exit 1
fi

echo "all GamePi systemd checks passed"
