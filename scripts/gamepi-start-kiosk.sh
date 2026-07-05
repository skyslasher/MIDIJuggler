#!/bin/sh
set -eu

export FRAMEBUFFER="${FRAMEBUFFER:-/dev/fb0}"
export HOME="${HOME:-/home/dietpi}"
xsession="/opt/midijuggler/app/configs/gamepi/kiosk.xsession"

cd "$HOME"
exec /usr/bin/startx "$xsession" -- :0 -nolisten tcp -nocursor -novtswitch
