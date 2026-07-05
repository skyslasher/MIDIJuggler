#!/bin/sh
set -eu

fb_device="${GAMEPI_FB_DEVICE:-/dev/fb0}"
timeout="${GAMEPI_FB_WAIT_TIMEOUT:-45}"
interval="${GAMEPI_FB_WAIT_INTERVAL:-0.05}"
hold_ms="${GAMEPI_START_HOLD_MS:-500}"
console_flag="${GAMEPI_CONSOLE_BOOT_FLAG:-/run/gamepi-console-boot}"
pressed_script="${GAMEPI_START_PRESSED_SCRIPT:-/opt/midijuggler/app/scripts/gamepi-is-start-pressed.sh}"

hold_steps=$((hold_ms / 50))
if [ "$hold_steps" -lt 1 ]; then
  hold_steps=1
fi

echo "waiting for ${fb_device} (timeout ${timeout}s, hold Start ${hold_ms}ms for console)" >&2

held_steps=0
deadline=$(($(date +%s) + timeout))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if [ -f "$console_flag" ]; then
    echo "console boot selected" >&2
    exit 0
  fi

  if [ -x "$pressed_script" ] && "$pressed_script"; then
    held_steps=$((held_steps + 1))
    if [ "$held_steps" -ge "$hold_steps" ]; then
      : >"$console_flag"
      echo "Start held ${hold_ms}ms: console boot" >&2
      exit 0
    fi
  else
    held_steps=0
  fi

  if [ -c "$fb_device" ]; then
    if [ -x "$pressed_script" ] && "$pressed_script"; then
      : # fb0 ready but Start held — finish hold detection first
    else
      echo "${fb_device} ready" >&2
      exit 0
    fi
  fi

  sleep "$interval"
done

if [ -f "$console_flag" ]; then
  exit 0
fi

echo "timed out waiting for ${fb_device}" >&2
exit 1
