#!/bin/sh
# Apply display brightness on the GamePi kiosk X session (software fallback).
# xgamma alone often has no effect on the SPI fbdev panel; try xrandr first.
set -eu

gamma="${1:-1.0}"
display="${GAMEPI_X_DISPLAY:-:0}"
x_user="${GAMEPI_X_USER:-dietpi}"
x_home="${GAMEPI_X_HOME:-/home/${x_user}}"
xauthority="${GAMEPI_XAUTHORITY:-${x_home}/.Xauthority}"

if [ ! -f "$xauthority" ]; then
  echo "missing Xauthority: ${xauthority}" >&2
  exit 1
fi

run_x() {
  if [ "$(id -u)" -eq 0 ]; then
    runuser -u "$x_user" -- env DISPLAY="$display" XAUTHORITY="$xauthority" "$@"
  else
    env DISPLAY="$display" XAUTHORITY="$xauthority" "$@"
  fi
}

if command -v xrandr >/dev/null 2>&1; then
  outputs=$(run_x xrandr -q 2>/dev/null | awk '/ connected/{print $1}' || true)
  if [ -n "$outputs" ]; then
    applied=0
    for output in $outputs; do
      if run_x xrandr --output "$output" --brightness "$gamma" 2>/dev/null; then
        applied=1
      fi
    done
    if [ "$applied" -eq 1 ]; then
      exit 0
    fi
  fi
  if run_x xrandr --gamma "${gamma}:${gamma}:${gamma}" 2>/dev/null; then
    exit 0
  fi
fi

if ! command -v xgamma >/dev/null 2>&1; then
  echo "xgamma not installed (apt install x11-xserver-utils)" >&2
  exit 1
fi

run_x xgamma -gamma "$gamma"
