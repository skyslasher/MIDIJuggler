#!/bin/sh
# Release the SPI framebuffer from the kernel text console before X fbdev opens it.

fb_device="${GAMEPI_FB_DEVICE:-/dev/fb0}"
fb_name="$(basename "$fb_device")"

if [ -w "/sys/class/graphics/${fb_name}/blank" ]; then
  echo 0 > "/sys/class/graphics/${fb_name}/blank" 2>/dev/null || true
fi

if command -v chvt >/dev/null 2>&1; then
  chvt 1 2>/dev/null || true
fi

for vtcon in /sys/class/vtconsole/vtcon*; do
  [ -f "${vtcon}/bind" ] || continue
  name="$(cat "${vtcon}/name" 2>/dev/null || true)"
  case "$name" in
    *framebuffer*)
      echo 0 > "${vtcon}/bind" 2>/dev/null || true
      ;;
  esac
done

sleep "${GAMEPI_FB_HANDOFF_DELAY:-0.5}"

if [ -w "/sys/class/graphics/${fb_name}/blank" ]; then
  echo 0 > "/sys/class/graphics/${fb_name}/blank" 2>/dev/null || true
fi
