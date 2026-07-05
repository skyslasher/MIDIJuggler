#!/bin/sh
set -eu

export FRAMEBUFFER="${FRAMEBUFFER:-/dev/fb0}"
export HOME="${HOME:-/home/dietpi}"

cd "$HOME"
exec /usr/bin/startx /opt/midijuggler/app/configs/gamepi/kiosk.xsession -- :0 vt1 -nolisten tcp -nocursor
