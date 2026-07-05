#!/bin/sh
set -eu

image="${GAMEPI_SPLASH_IMAGE:-/etc/midijuggler/splash.png}"
gpio="${GAMEPI_START_GPIO:-26}"
chip="${GAMEPI_START_GPIO_CHIP:-gpiochip0}"
hold_ms="${GAMEPI_START_HOLD_MS:-500}"
fb_device="${GAMEPI_FB_DEVICE:-/dev/fb0}"
python_bin="${GAMEPI_PYTHON:-/opt/midijuggler/venv/bin/python}"
start_held_script="${GAMEPI_START_HELD_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-start-held.py}"
blanking_script="${GAMEPI_BLANKING_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-disable-blanking.sh}"

console_boot_flag=/run/gamepi-console-boot

console_boot_requested() {
  if [ -x "$python_bin" ] && [ -f "$start_held_script" ]; then
    if "$python_bin" "$start_held_script" "$hold_ms"; then
      return 0
    fi
    return 1
  fi

  elapsed=0
  while [ "$elapsed" -lt "$hold_ms" ]; do
    if ! command -v gpioget >/dev/null 2>&1; then
      return 1
    fi
    value="$(gpioget -c "$chip" "$gpio" 2>/dev/null)" || return 1
    if [ "$value" != "0" ]; then
      return 1
    fi
    sleep 0.05
    elapsed=$((elapsed + 50))
  done
  return 0
}

if console_boot_requested; then
  echo "GamePi Start held: keeping boot console on ${fb_device}"
  : >"$console_boot_flag"
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

echo "Showing splash on ${fb_device}: ${image}"
# Stay on screen until gamepi-launch-kiosk.sh kills fbi (-once exits after one frame).
exec fbi -d "$fb_device" -T 1 -a -noverbose -t 0 "$image"
