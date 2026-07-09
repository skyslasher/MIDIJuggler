#!/bin/sh
# Best-effort blanking disable; must never fail callers (systemd ExecStartPre).

fb_device="${GAMEPI_FB_DEVICE:-/dev/fb0}"
fb_name="$(basename "$fb_device")"
x_display="${GAMEPI_X_DISPLAY:-:0}"
x_user="${GAMEPI_X_USER:-dietpi}"
x_home="${GAMEPI_X_HOME:-/home/${x_user}}"
xauthority="${GAMEPI_XAUTHORITY:-${x_home}/.Xauthority}"
display_num="${x_display#:}"
x_socket="/tmp/.X11-unix/X${display_num}"

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

run_xset() {
  if ! command -v xset >/dev/null 2>&1; then
    return 0
  fi
  if [ ! -S "$x_socket" ]; then
    return 0
  fi

  xset_env="DISPLAY=${x_display}"
  if [ -f "$xauthority" ]; then
    xset_env="${xset_env} XAUTHORITY=${xauthority}"
  fi

  if [ "$(id -u)" -eq 0 ] && id "$x_user" >/dev/null 2>&1; then
    runuser -u "$x_user" -- env $xset_env xset s off 2>/dev/null || true
    runuser -u "$x_user" -- env $xset_env xset -dpms 2>/dev/null || true
    runuser -u "$x_user" -- env $xset_env xset s noblank 2>/dev/null || true
    runuser -u "$x_user" -- env $xset_env xset dpms force on 2>/dev/null || true
  else
    env $xset_env xset s off 2>/dev/null || true
    env $xset_env xset -dpms 2>/dev/null || true
    env $xset_env xset s noblank 2>/dev/null || true
    env $xset_env xset dpms force on 2>/dev/null || true
  fi
}

run_xset

if [ "${GAMEPI_ALLOW_SETTERM:-0}" = "1" ] && command -v setterm >/dev/null 2>&1; then
  # setterm on tty1 can black out the SPI panel once X/fbdev owns the display.
  if [ -w /dev/tty1 ]; then
    setterm -blank 0 -powerdown 0 -powersave off </dev/tty1 >/dev/tty1 2>&1 || true
  fi
  setterm -blank 0 -powerdown 0 -powersave off 2>/dev/null || true
fi
