#!/bin/sh
# Shell tests for GamePi kiosk launch and splash-stop resilience.
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0
fail=0

assert() {
  desc="$1"
  shift
  if "$@"; then
    pass=$((pass + 1))
    printf 'ok: %s\n' "$desc"
  else
    fail=$((fail + 1))
    printf 'FAIL: %s\n' "$desc" >&2
  fi
}

assert_contains() {
  desc="$1"
  haystack="$2"
  needle="$3"
  if echo "$haystack" | grep -q "$needle"; then
    pass=$((pass + 1))
    printf 'ok: %s\n' "$desc"
  else
    fail=$((fail + 1))
    printf 'FAIL: %s\n' "$desc" >&2
  fi
}

# splash-stop must not fail when completed flag is not writable.
readonly_flag="$tmp/readonly-flag"
mkdir -p "$(dirname "$readonly_flag")"
touch "$readonly_flag"
chmod 444 "$readonly_flag"
out="$(GAMEPI_SPLASH_COMPLETED_FLAG="$readonly_flag" \
  sh "$repo_root/scripts/gamepi-splash-stop.sh" 2>&1)" && rc=0 || rc=$?
assert "splash-stop exits 0 when flag not writable" [ "$rc" -eq 0 ]
assert_contains "splash-stop warns on unwritable flag" "$out" "could not mark splash completed"

# splash-stop writes to a writable tmp path by default.
splash_completed="$tmp/writable-completed"
rm -f "$splash_completed"
GAMEPI_SPLASH_COMPLETED_FLAG="$splash_completed" \
  sh "$repo_root/scripts/gamepi-splash-stop.sh" >/dev/null 2>&1
assert "splash-stop creates completed flag when writable" [ -f "$splash_completed" ]

# launch-kiosk skips splash-stop when splash already completed.
stop_log="$tmp/splash-stop.log"
start_log="$tmp/start-kiosk.log"
: >"$stop_log"
: >"$start_log"
scripts_stub="$tmp/stub-scripts"
mkdir -p "$scripts_stub"
completed_flag="$tmp/already-completed"
: >"$completed_flag"
cp "$repo_root/scripts/gamepi-paths.sh" "$scripts_stub/"
cat >"$scripts_stub/gamepi-splash-stop.sh" <<EOF
#!/bin/sh
echo splash-stop-called >>"$stop_log"
EOF
cat >"$scripts_stub/gamepi-start-kiosk.sh" <<EOF
#!/bin/sh
echo start-kiosk-called >>"$start_log"
exit 0
EOF
chmod +x "$scripts_stub"/*.sh
MIDIJUGGLER_SCRIPTS_DIR="$scripts_stub" \
  GAMEPI_SPLASH_COMPLETED_FLAG="$completed_flag" \
  sh "$repo_root/scripts/gamepi-launch-kiosk.sh" >/dev/null 2>&1
assert "launch-kiosk skips splash-stop when already completed" [ ! -s "$stop_log" ]
assert "launch-kiosk still starts kiosk" [ -s "$start_log" ]

# launch-kiosk runs splash-stop when splash not yet completed.
rm -f "$completed_flag"
: >"$stop_log"
: >"$start_log"
MIDIJUGGLER_SCRIPTS_DIR="$scripts_stub" \
  GAMEPI_SPLASH_COMPLETED_FLAG="$completed_flag" \
  sh "$repo_root/scripts/gamepi-launch-kiosk.sh" >/dev/null 2>&1
assert "launch-kiosk runs splash-stop without completed flag" [ -s "$stop_log" ]
assert "launch-kiosk starts kiosk after splash-stop" [ -s "$start_log" ]

# Chromium kiosk flags for fbdev SPI (no EGL, no unsupported flags).
xsession="$repo_root/configs/gamepi/kiosk.xsession"
assert "kiosk.xsession disables GPU" grep -q -- '--disable-gpu' "$xsession"
assert "kiosk.xsession disables GPU compositing" grep -q -- '--disable-gpu-compositing' "$xsession"
if grep -q 'no-decommit-pooled-pages' "$xsession"; then
  fail=$((fail + 1))
  printf 'FAIL: kiosk.xsession must not use --no-decommit-pooled-pages\n' >&2
else
  pass=$((pass + 1))
  printf 'ok: kiosk.xsession has no unsupported chromium flags\n'
fi

# systemd units expose /run/gamepi state dir.
assert "gamepi-kiosk.service sets splash completed path" \
  grep -q 'GAMEPI_SPLASH_COMPLETED_FLAG=/run/gamepi/splash-completed' \
  "$repo_root/systemd/gamepi-kiosk.service"
assert "gamepi-kiosk.service has RuntimeDirectory" \
  grep -q 'RuntimeDirectory=gamepi' "$repo_root/systemd/gamepi-kiosk.service"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
