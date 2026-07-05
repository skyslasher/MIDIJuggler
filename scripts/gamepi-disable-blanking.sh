#!/bin/sh
# Best-effort blanking disable; must never fail callers (systemd ExecStartPre).

fb_device="${GAMEPI_FB_DEVICE:-/dev/fb0}"
fb_name="$(basename "$fb_device")"

if [ -w "/sys/class/graphics/${fb_name}/blank" ]; then
  echo 0 > "/sys/class/graphics/${fb_name}/blank" 2>/dev/null || true
fi

if command -v fbset >/dev/null 2>&1; then
  fbset -blank 0 -fb "${fb_device}" 2>/dev/null || fbset -blank 0 2>/dev/null || true
fi

if [ -r /sys/module/kernel/parameters/consoleblank ]; then
  if [ -w /sys/module/kernel/parameters/consoleblank ]; then
    echo 0 > /sys/module/kernel/parameters/consoleblank 2>/dev/null || true
  fi
fi

if [ -S /tmp/.X11-unix/X0 ] && command -v xset >/dev/null 2>&1; then
  DISPLAY=:0 xset s off 2>/dev/null || true
  DISPLAY=:0 xset -dpms 2>/dev/null || true
  DISPLAY=:0 xset s noblank 2>/dev/null || true
elif command -v setterm >/dev/null 2>&1; then
  if [ -w /dev/tty1 ]; then
    setterm -blank 0 -powerdown 0 -powersave off </dev/tty1 >/dev/tty1 2>&1 || true
  fi
  setterm -blank 0 -powerdown 0 -powersave off 2>/dev/null || true
fi

if command -v xset >/dev/null 2>&1 && [ -n "${DISPLAY:-}" ]; then
  xset s off 2>/dev/null || true
  xset -dpms 2>/dev/null || true
  xset s noblank 2>/dev/null || true
fi
