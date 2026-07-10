#!/bin/sh
set -eu

completed_flag="${GAMEPI_SPLASH_COMPLETED_FLAG:-/run/gamepi-splash-completed}"
image="${GAMEPI_SPLASH_IMAGE:-/etc/midijuggler/splash.png}"
gpio="${GAMEPI_START_GPIO:-26}"
chip="${GAMEPI_START_GPIO_CHIP:-gpiochip0}"
hold_ms="${GAMEPI_START_HOLD_MS:-500}"
fb_device="${GAMEPI_FB_DEVICE:-/dev/fb0}"
python_bin="${GAMEPI_PYTHON:-/opt/midijuggler/venv/bin/python}"
start_held_script="${GAMEPI_START_HELD_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-start-held.py}"
blanking_script="${GAMEPI_BLANKING_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-disable-blanking.sh}"

console_boot_flag="${GAMEPI_CONSOLE_BOOT_FLAG:-/run/gamepi-console-boot}"

if [ -f "$completed_flag" ]; then
  echo "Splash already handed off this boot; skipping re-display" >&2
  exit 0
fi

if [ -f "$console_boot_flag" ]; then
  echo "Console boot: skipping splash" >&2
  fbcon_script="${GAMEPI_FBCON_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-fbcon.sh}"
  if [ -x "$fbcon_script" ]; then
    GAMEPI_FB_DEVICE="$fb_device" "$fbcon_script" on
  fi
  systemctl start getty@tty1.service 2>/dev/null || true
  exit 0
fi

pressed_script="${GAMEPI_START_PRESSED_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-is-start-pressed.sh}"

gpio_hold_detected() {
  if [ ! -x "$pressed_script" ]; then
    return 1
  fi
  elapsed=0
  while [ "$elapsed" -lt "$hold_ms" ]; do
    if ! "$pressed_script"; then
      return 1
    fi
    sleep 0.05
    elapsed=$((elapsed + 50))
  done
  return 0
}

console_boot_requested() {
  if gpio_hold_detected; then
    return 0
  fi

  if [ -x "$python_bin" ] && [ -f "$start_held_script" ]; then
    if "$python_bin" "$start_held_script" "$hold_ms"; then
      return 0
    fi
  fi

  return 1
}

if console_boot_requested; then
  echo "GamePi Start held: keeping boot console on ${fb_device}"
  : >"$console_boot_flag"
  if [ -x "${GAMEPI_FBCON_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-fbcon.sh}" ]; then
    GAMEPI_FB_DEVICE="$fb_device" "${GAMEPI_FBCON_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-fbcon.sh}" on
  fi
  systemctl start getty@tty1.service 2>/dev/null || true
  exit 0
fi

if [ ! -f "$image" ]; then
  echo "Splash image missing: ${image}" >&2
  exit 0
fi

if ! command -v fbi >/dev/null 2>&1; then
  echo "fbi not installed; skipping splash (install: apt install fbi)" >&2
  exit 0
fi

if [ -x "$blanking_script" ]; then
  GAMEPI_FB_DEVICE="$fb_device" "$blanking_script"
fi

systemctl stop getty@tty1.service 2>/dev/null || true

if command -v chvt >/dev/null 2>&1; then
  chvt 1 2>/dev/null || true
fi

fbcon_script="${GAMEPI_FBCON_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-fbcon.sh}"
if [ -x "$fbcon_script" ]; then
  GAMEPI_FB_DEVICE="$fb_device" "$fbcon_script" off
fi

hold_flag=/run/gamepi-splash-hold
: >"$hold_flag"

killall fbi 2>/dev/null || true

start_fbi() {
  fbi -d "$fb_device" -T 1 -a -noverbose "$image" &
  sleep 0.5
}

echo "Showing splash on ${fb_device}: ${image} (until kiosk handoff)" >&2
start_fbi

poll_interval="${GAMEPI_SPLASH_POLL_INTERVAL:-2}"
while [ -f "$hold_flag" ]; do
  if ! pgrep -x fbi >/dev/null 2>&1; then
    echo "fbi not running, restarting once" >&2
    start_fbi
  fi
  sleep "$poll_interval"
done

killall fbi 2>/dev/null || true
