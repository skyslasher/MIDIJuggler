#!/bin/sh
# Tests for gamepi-start-held.py and splash resilience (no hardware required).
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

assert_contains "start-held uses evdev setblocking(False)" \
  "$(sed -n '1,80p' "$repo_root/scripts/gamepi-start-held.py")" \
  'setblocking(False)'

# Mock helpers for boot-splash integration.
mock_pressed="$tmp/mock-start-pressed.sh"
cat >"$mock_pressed" <<'EOF'
#!/bin/sh
exit 1
EOF
chmod +x "$mock_pressed"

crash_start_held="$tmp/crash-start-held.py"
cat >"$crash_start_held" <<'EOF'
#!/usr/bin/env python3
raise AttributeError("'InputDevice' object has no attribute 'setblocking'")
EOF
chmod +x "$crash_start_held"

mock_bin="$tmp/bin"
mkdir -p "$mock_bin"
cat >"$mock_bin/fbi" <<'EOF'
#!/bin/sh
echo "mock fbi $*" >&2
touch /tmp/gamepi-test-fbi-ran
exit 0
EOF
chmod +x "$mock_bin/fbi"

splash_image="$tmp/splash.png"
printf 'PNG' >"$splash_image"

noop_fbcon="$tmp/noop-fbcon.sh"
printf '#!/bin/sh\nexit 0\n' >"$noop_fbcon"
chmod +x "$noop_fbcon"

console_flag="$tmp/gamepi-console-boot"
rm -f "$console_flag" /tmp/gamepi-test-fbi-ran

if touch /run/gamepi-splash-hold 2>/dev/null; then
  rm -f /run/gamepi-splash-hold
  out_file="$tmp/boot-splash.out"
  PATH="$mock_bin:$PATH" \
    GAMEPI_CONSOLE_BOOT_FLAG="$console_flag" \
    GAMEPI_START_PRESSED_SCRIPT="$mock_pressed" \
    GAMEPI_START_HELD_SCRIPT="$crash_start_held" \
    GAMEPI_PYTHON="$(command -v python3)" \
    GAMEPI_SPLASH_IMAGE="$splash_image" \
    GAMEPI_FB_DEVICE="$tmp/fake-fb0" \
    GAMEPI_FBCON_SCRIPT="$noop_fbcon" \
    GAMEPI_BLANKING_SCRIPT="$noop_fbcon" \
    sh "$repo_root/scripts/gamepi-boot-splash.sh" >"$out_file" 2>&1 &
  splash_pid=$!

  sleep 1
  if kill -0 "$splash_pid" 2>/dev/null; then
    pass=$((pass + 1))
    printf 'ok: boot-splash survives start-held crash\n'
  else
    fail=$((fail + 1))
    printf 'FAIL: boot-splash exited after start-held crash\n' >&2
    sed -n '1,20p' "$out_file" >&2 || true
  fi

  assert "boot-splash does not select console boot on start-held crash" \
    [ ! -f "$console_flag" ]
  assert_contains "boot-splash reaches splash display after start-held crash" \
    "$(cat "$out_file")" "Showing splash"
  assert "mock fbi invoked after start-held crash" \
    [ -f /tmp/gamepi-test-fbi-ran ]

  rm -f /run/gamepi-splash-hold 2>/dev/null || true
  kill "$splash_pid" 2>/dev/null || true
  wait "$splash_pid" 2>/dev/null || true
  rm -f /tmp/gamepi-test-fbi-ran
else
  pass=$((pass + 1))
  printf 'ok: boot-splash crash test skipped (no /run write access)\n'
fi

# Handoff chain: splash-stop removes hold flag when present.
hold_flag_path="/run/gamepi-splash-hold"
if touch "$hold_flag_path" 2>/dev/null; then
  splash_stop_out="$(GAMEPI_SPLASH_COMPLETED_FLAG="$tmp/splash-completed" \
    GAMEPI_FB_HANDOFF_SCRIPT="$noop_fbcon" \
    sh "$repo_root/scripts/gamepi-splash-stop.sh" 2>&1)" || true
  assert_contains "splash-stop removes hold flag" "$splash_stop_out" "handing off"
  assert "splash-stop clears hold flag file" [ ! -f "$hold_flag_path" ]
  assert "splash-stop marks completed flag" [ -f "$tmp/splash-completed" ]
else
  pass=$((pass + 1))
  printf 'ok: splash-stop handoff test skipped (no /run write access)\n'
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
