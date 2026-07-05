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

# splash-stop skips fb handoff when splash never ran.
noop_handoff="$tmp/noop-handoff.sh"
printf '#!/bin/sh\necho handoff-called >&2\n' >"$noop_handoff"
chmod +x "$noop_handoff"
out="$(GAMEPI_FB_HANDOFF_SCRIPT="$noop_handoff" \
  sh "$repo_root/scripts/gamepi-splash-stop.sh" 2>&1)" || true
assert_contains "splash-stop skips handoff without active splash" "$out" "skipping framebuffer handoff"
if echo "$out" | grep -q handoff-called; then
  fail=$((fail + 1))
  printf 'FAIL: handoff script invoked without splash\n' >&2
else
  pass=$((pass + 1))
  printf 'ok: handoff script not invoked without splash\n'
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
