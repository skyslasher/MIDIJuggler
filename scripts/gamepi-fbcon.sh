#!/bin/sh
set -eu

fb_device="${GAMEPI_FB_DEVICE:-/dev/fb0}"
fb_name="$(basename "$fb_device")"
action="${1:-off}"

if [ -w "/sys/class/graphics/${fb_name}/blank" ]; then
  echo 0 > "/sys/class/graphics/${fb_name}/blank"
fi

case "$action" in
  off)
    for vtcon in /sys/class/vtconsole/vtcon*; do
      [ -f "${vtcon}/bind" ] || continue
      name="$(cat "${vtcon}/name" 2>/dev/null || true)"
      case "$name" in
        *framebuffer*)
          echo 0 > "${vtcon}/bind" 2>/dev/null || true
          ;;
      esac
    done
    ;;
  on)
    for vtcon in /sys/class/vtconsole/vtcon*; do
      [ -f "${vtcon}/bind" ] || continue
      name="$(cat "${vtcon}/name" 2>/dev/null || true)"
      case "$name" in
        *framebuffer*)
          echo 1 > "${vtcon}/bind" 2>/dev/null || true
          ;;
      esac
    done
    ;;
  *)
    echo "usage: $0 [off|on]" >&2
    exit 1
    ;;
esac
