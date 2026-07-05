#!/bin/sh
set -eu

export FRAMEBUFFER="${FRAMEBUFFER:-/dev/fb0}"
export HOME="${HOME:-/home/dietpi}"

if command -v chvt >/dev/null 2>&1; then
  chvt 1 2>/dev/null || true
fi

cd "$HOME"
exec /usr/bin/startx /opt/midijuggler/app/configs/gamepi/kiosk.xsession -- :0 vt1 -nolisten tcp -nocursor
