#!/bin/sh
# Check whether the GamePi kiosk stack looks healthy (fb unblanked, X, Chromium, web UI).

fb_device="${GAMEPI_FB_DEVICE:-/dev/fb0}"
fb_name="$(basename "$fb_device")"
x_display="${GAMEPI_X_DISPLAY:-:0}"
x_socket="${GAMEPI_X_SOCKET:-/tmp/.X11-unix/X${x_display#:}}"
web_url="${GAMEPI_KIOSK_URL:-http://127.0.0.1:8080/static/clock-gamepi.html}"
diagnose="${GAMEPI_DIAGNOSE:-0}"

fb_blank_state() {
  blank_path="/sys/class/graphics/${fb_name}/blank"
  if [ -r "$blank_path" ]; then
    cat "$blank_path" 2>/dev/null || echo "?"
  else
    echo "?"
  fi
}

x_socket_ready() {
  [ -S "$x_socket" ]
}

chromium_running() {
  pgrep -x chromium >/dev/null 2>&1 || pgrep -f '[c]hromium.*clock-gamepi' >/dev/null 2>&1
}

xorg_running() {
  pgrep -x Xorg >/dev/null 2>&1
}

web_ui_ready() {
  if ! command -v curl >/dev/null 2>&1; then
    return 0
  fi
  curl -fsS --connect-timeout 2 --max-time 3 -o /dev/null "$web_url" 2>/dev/null
}

diagnose_line() {
  if [ "$diagnose" = "1" ]; then
    printf '%s\n' "$1" >&2
  fi
}

blank="$(fb_blank_state)"
x_sock="no"
chromium="no"
xorg="no"
web="no"

if x_socket_ready; then
  x_sock="yes"
fi
if chromium_running; then
  chromium="yes"
fi
if xorg_running; then
  xorg="yes"
fi
if web_ui_ready; then
  web="yes"
fi

diagnose_line "diagnose: fb ${fb_name} blank=${blank} (0=on)"
diagnose_line "diagnose: X socket ${x_socket}=${x_sock} Xorg=${xorg}"
diagnose_line "diagnose: chromium=${chromium} web=${web} url=${web_url}"

issues=0

case "$blank" in
  0|'') ;;
  *)
    issues=$((issues + 1))
    diagnose_line "diagnose: framebuffer is blanked"
    ;;
esac

if [ "$x_sock" != "yes" ]; then
  issues=$((issues + 1))
  diagnose_line "diagnose: X socket missing"
fi

if [ "$xorg" != "yes" ]; then
  issues=$((issues + 1))
  diagnose_line "diagnose: Xorg not running"
fi

if [ "$chromium" != "yes" ]; then
  issues=$((issues + 1))
  diagnose_line "diagnose: Chromium not running"
fi

if [ "$web" != "yes" ]; then
  issues=$((issues + 1))
  diagnose_line "diagnose: web UI not reachable"
fi

if [ "$issues" -eq 0 ]; then
  exit 0
fi

exit 1
