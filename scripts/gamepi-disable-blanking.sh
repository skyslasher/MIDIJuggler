#!/bin/sh
set -eu

fb_device="${GAMEPI_FB_DEVICE:-/dev/fb0}"

if [ -w "${fb_device}" ] || [ -w "/sys/class/graphics/fb0/blank" ]; then
  if [ -w "/sys/class/graphics/fb0/blank" ]; then
    echo 0 > /sys/class/graphics/fb0/blank
  fi
fi

if command -v setterm >/dev/null 2>&1; then
  setterm -blank 0 -powerdown 0 -powersave off >/dev/tty1 2>/dev/null \
    || setterm -blank 0 -powerdown 0 -powersave off 2>/dev/null \
    || true
fi

if command -v xset >/dev/null 2>&1 && [ -n "${DISPLAY:-}" ]; then
  xset s off
  xset -dpms
  xset s noblank
fi
