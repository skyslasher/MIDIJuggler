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

# splash-stop marks completed flag when writable.
splash_completed="$tmp/writable-completed"
rm -f "$splash_completed"
GAMEPI_SPLASH_COMPLETED_FLAG="$splash_completed" \
  sh "$repo_root/scripts/gamepi-splash-stop.sh" >/dev/null 2>&1
assert "splash-stop creates completed flag when writable" [ -f "$splash_completed" ]

# launch-kiosk always runs splash-stop then start-kiosk (simple handoff).
stop_log="$tmp/splash-stop.log"
start_log="$tmp/start-kiosk.log"
: >"$stop_log"
: >"$start_log"
scripts_stub="$tmp/stub-scripts"
mkdir -p "$scripts_stub"
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
  sh "$repo_root/scripts/gamepi-launch-kiosk.sh" >/dev/null 2>&1
assert "launch-kiosk runs splash-stop" [ -s "$stop_log" ]
assert "launch-kiosk starts kiosk after splash-stop" [ -s "$start_log" ]

# kiosk.xsession should use plain chromium kiosk flags (no EGL workarounds).
xsession="$repo_root/configs/gamepi/kiosk.xsession"
assert "kiosk.xsession starts chromium kiosk" grep -q -- '--kiosk' "$xsession"
if grep -q -- '--disable-gpu' "$xsession"; then
  fail=$((fail + 1))
  printf 'FAIL: kiosk.xsession must not force --disable-gpu\n' >&2
else
  pass=$((pass + 1))
  printf 'ok: kiosk.xsession has no GPU disable flags\n'
fi

assert "gamepi-kiosk.service uses start-kiosk directly" \
  grep -q 'gamepi-start-kiosk.sh' "$repo_root/systemd/gamepi-kiosk.service"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
