#!/bin/sh
# Apply display gamma on the GamePi kiosk X session (software brightness fallback).
set -eu

gamma="${1:-1.0}"
display="${GAMEPI_X_DISPLAY:-:0}"
x_user="${GAMEPI_X_USER:-dietpi}"
x_home="${GAMEPI_X_HOME:-/home/${x_user}}"
xauthority="${GAMEPI_XAUTHORITY:-${x_home}/.Xauthority}"

if ! command -v xgamma >/dev/null 2>&1; then
  echo "xgamma not installed (apt install x11-xserver-utils)" >&2
  exit 1
fi

if [ ! -f "$xauthority" ]; then
  echo "missing Xauthority: ${xauthority}" >&2
  exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
  exec runuser -u "$x_user" -- env DISPLAY="$display" XAUTHORITY="$xauthority" xgamma -gamma "$gamma"
fi

exec env DISPLAY="$display" XAUTHORITY="$xauthority" xgamma -gamma "$gamma"
