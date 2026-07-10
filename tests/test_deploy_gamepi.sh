#!/bin/sh
# Static checks for deploy-gamepi.sh (no Pi hardware required).
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
script="${repo_root}/scripts/deploy-gamepi.sh"
fail=0

check_contains() {
  desc="$1"
  needle="$2"
  if grep -q "$needle" "$script"; then
    echo "ok: $desc"
  else
    echo "FAIL: $desc" >&2
    fail=1
  fi
}

if [ ! -f "$script" ]; then
  echo "FAIL: missing $script" >&2
  exit 1
fi

check_contains "requires root" 'id -u'
check_contains "pull-midijuggler-app" 'pull-midijuggler-app.sh'
check_contains "pip install extras" 'pip install -e'
check_contains "install-gamepi13-services" 'install-gamepi13-services.sh'
check_contains "midijuggler sudoers" 'midijuggler-sudoers.example'
check_contains "display health" 'gamepi-display-health.sh'
check_contains "reload after pull" 'gamepi-reload-after-pull.sh'
check_contains "rotary extra default" 'alsa,midi,hid,rotary'
check_contains "kiosk restart opt-in" 'GAMEPI_RESTART_KIOSK:-0'

if grep -q 'gamepi-kiosk-diagnostics.sh' "$script"; then
  echo "FAIL: deploy-gamepi must not reference kiosk diagnostics" >&2
  fail=1
else
  echo "ok: deploy-gamepi has no kiosk diagnostics"
fi

if [ "$fail" -ne 0 ]; then
  exit 1
fi

echo "all deploy-gamepi checks passed"
