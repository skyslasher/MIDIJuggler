#!/bin/sh
set -eu

export FRAMEBUFFER="${FRAMEBUFFER:-/dev/fb0}"
export HOME="${HOME:-/home/dietpi}"
xsession="/opt/midijuggler/app/configs/gamepi/kiosk.xsession"
startx_args="/usr/bin/startx ${xsession} -- :0 vt1 -nolisten tcp -nocursor"

cd "$HOME"

if command -v openvt >/dev/null 2>&1; then
  exec openvt -c 1 -f -s -- env HOME="$HOME" FRAMEBUFFER="$FRAMEBUFFER" $startx_args
fi

echo "openvt not found (install kbd); trying startx without VT helper" >&2
exec env HOME="$HOME" FRAMEBUFFER="$FRAMEBUFFER" $startx_args
