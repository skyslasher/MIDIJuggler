#!/bin/sh
# Shell tests for GamePi console-boot detection (no hardware required).
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

mock_pressed="$tmp/mock-start-pressed.sh"
cat >"$mock_pressed" <<'EOF'
#!/bin/sh
state_file="/tmp/gamepi-test-start-state"
[ -f "$state_file" ] && [ "$(cat "$state_file")" = "1" ]
EOF
chmod +x "$mock_pressed"

noop_fbcon="$tmp/noop-fbcon.sh"
printf '#!/bin/sh\nexit 0\n' >"$noop_fbcon"
chmod +x "$noop_fbcon"

console_flag="$tmp/gamepi-console-boot"
missing_fb="$tmp/no-such-fb0"
export GAMEPI_FB_WAIT_TIMEOUT=2
export GAMEPI_FB_WAIT_INTERVAL=0.05
export GAMEPI_START_HOLD_MS=250
export GAMEPI_CONSOLE_BOOT_FLAG="$console_flag"
export GAMEPI_START_PRESSED_SCRIPT="$mock_pressed"

# Start not pressed, no fb: times out.
printf '0' > /tmp/gamepi-test-start-state
rm -f "$console_flag"
GAMEPI_FB_DEVICE="$missing_fb" \
  sh "$repo_root/scripts/wait-for-fb0.sh" >/dev/null 2>&1 && rc=0 || rc=$?
assert "times out when fb missing and Start not held" [ "$rc" -ne 0 ]

# Start held 250ms with no fb: flag created before timeout.
printf '1' > /tmp/gamepi-test-start-state
rm -f "$console_flag"
GAMEPI_FB_DEVICE="$missing_fb" \
  sh "$repo_root/scripts/wait-for-fb0.sh" >/dev/null 2>&1
assert "Start held sets console flag during fb wait" [ -f "$console_flag" ]

# boot-splash skips fbi when flag pre-set.
rm -f /tmp/gamepi-test-start-state
: >"$console_flag"
out="$(GAMEPI_FB_DEVICE="$missing_fb" \
  GAMEPI_CONSOLE_BOOT_FLAG="$console_flag" \
  GAMEPI_SPLASH_IMAGE="$tmp/missing-splash.png" \
  GAMEPI_FBCON_SCRIPT="$noop_fbcon" \
  sh "$repo_root/scripts/gamepi-boot-splash.sh" 2>&1)" || true
assert_contains "boot-splash skips when console flag exists" "$out" "Console boot"

# pressed helper must be executable for wait-for-fb0 to use it.
nonexec="$tmp/not-executable.sh"
printf '#!/bin/sh\nexit 0\n' >"$nonexec"
chmod -x "$nonexec" 2>/dev/null || true
printf '1' > /tmp/gamepi-test-start-state
rm -f "$console_flag"
GAMEPI_FB_DEVICE="$missing_fb" \
  GAMEPI_START_PRESSED_SCRIPT="$nonexec" \
  sh "$repo_root/scripts/wait-for-fb0.sh" >/dev/null 2>&1 && rc=0 || rc=$?
assert "non-executable pressed script prevents console flag" [ ! -f "$console_flag" ] && [ "$rc" -ne 0 ]

rm -f /tmp/gamepi-test-start-state

# boot-splash skips fbi when splash already handed off this boot.
rm -f /tmp/gamepi-test-start-state
completed_flag="$tmp/gamepi-splash-completed"
: >"$completed_flag"
out="$(GAMEPI_SPLASH_COMPLETED_FLAG="$completed_flag" \
  GAMEPI_FB_DEVICE="$missing_fb" \
  GAMEPI_SPLASH_IMAGE="$tmp/missing-splash.png" \
  GAMEPI_FBCON_SCRIPT="$noop_fbcon" \
  sh "$repo_root/scripts/gamepi-boot-splash.sh" 2>&1)" || true
assert_contains "boot-splash skips when splash already completed" "$out" "already handed off"

# splash-stop skips fb handoff when splash never ran.
noop_handoff="$tmp/noop-handoff.sh"
splash_completed="$tmp/splash-completed-by-stop"
rm -f "$splash_completed"
printf '#!/bin/sh\necho handoff-called >&2\n' >"$noop_handoff"
chmod +x "$noop_handoff"
out="$(GAMEPI_FB_HANDOFF_SCRIPT="$noop_handoff" \
  GAMEPI_SPLASH_COMPLETED_FLAG="$splash_completed" \
  sh "$repo_root/scripts/gamepi-splash-stop.sh" 2>&1)" || true
assert_contains "splash-stop skips handoff without active splash" "$out" "skipping framebuffer handoff"
if echo "$out" | grep -q handoff-called; then
  fail=$((fail + 1))
  printf 'FAIL: handoff script invoked without splash\n' >&2
else
  pass=$((pass + 1))
  printf 'ok: handoff script not invoked without splash\n'
fi

if [ -f "$splash_completed" ]; then
  pass=$((pass + 1))
  printf 'ok: splash-stop marks splash completed\n'
else
  fail=$((fail + 1))
  printf 'FAIL: splash-stop did not mark splash completed\n' >&2
fi

chromium_profile="$tmp/chromium-kiosk"
rm -rf "$chromium_profile"
mkdir -p "$chromium_profile"
touch "$chromium_profile/stale"
GAMEPI_CHROMIUM_USER_DATA_DIR="$chromium_profile" \
  sh "$repo_root/scripts/gamepi-clear-chromium-cache.sh"
assert "clear-chromium-cache recreates profile directory" [ -d "$chromium_profile" ]
assert "clear-chromium-cache removes stale files" [ ! -f "$chromium_profile/stale" ]

mock_bin="$tmp/bin"
mkdir -p "$mock_bin"
cat >"$mock_bin/systemctl" <<'EOF'
#!/bin/sh
case "$1" in
  restart)
    echo "systemctl restart $2" >&2
    ;;
  is-active)
    service="$2"
    if [ "$service" = "--quiet" ]; then
      service="$3"
    fi
    [ "$service" = "gamepi-kiosk.service" ]
    ;;
  is-enabled)
    exit 1
    ;;
  *)
    echo "unexpected: systemctl $*" >&2
    exit 1
    ;;
esac
EOF
chmod +x "$mock_bin/systemctl"

wait_log="$tmp/wait-log"
cat >"$tmp/mock-wait.sh" <<'EOF'
#!/bin/sh
echo waited >>"$WAIT_LOG"
EOF
chmod +x "$tmp/mock-wait.sh"
WAIT_LOG="$wait_log" PATH="$mock_bin:$PATH" \
  MIDIJUGGLER_WAIT_SCRIPT="$tmp/mock-wait.sh" \
  sh "$repo_root/scripts/gamepi-reload-after-pull.sh" >/dev/null 2>&1
assert "reload-after-pull waits for web before kiosk" [ -f "$wait_log" ]
assert_contains "reload-after-pull restarts kiosk after wait" "$(cat "$wait_log")" "waited"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
