#!/bin/sh
# Best-effort blanking disable; must never fail callers (systemd ExecStartPre).

fb_device="${GAMEPI_FB_DEVICE:-/dev/fb0}"
fb_name="$(basename "$fb_device")"

blank_path="/sys/class/graphics/${fb_name}/blank"
if [ -w "$blank_path" ]; then
  { echo 0 > "$blank_path"; } 2>/dev/null || true
  # Some SPI panels need a second write after a short delay.
  if [ -r "$blank_path" ] && [ "$(cat "$blank_path" 2>/dev/null)" != "0" ]; then
    sleep 0.1
    { echo 0 > "$blank_path"; } 2>/dev/null || true
  fi
fi

if [ -w /sys/module/kernel/parameters/consoleblank ] 2>/dev/null; then
  { echo 0 > /sys/module/kernel/parameters/consoleblank; } 2>/dev/null || true
fi

if [ -S /tmp/.X11-unix/X0 ] && command -v xset >/dev/null 2>&1; then
  DISPLAY=:0 xset s off 2>/dev/null || true
  DISPLAY=:0 xset -dpms 2>/dev/null || true
  DISPLAY=:0 xset s noblank 2>/dev/null || true
elif [ "${GAMEPI_ALLOW_SETTERM:-0}" = "1" ] && command -v setterm >/dev/null 2>&1; then
  # setterm on tty1 can black out the SPI panel once X/fbdev owns the display.
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
