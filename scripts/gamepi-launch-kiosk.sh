#!/bin/sh
set -eu

scripts_dir="${MIDIJUGGLER_SCRIPTS_DIR:-/opt/midijuggler/app/scripts}"
splash_stop="${scripts_dir}/gamepi-splash-stop.sh"

if [ -x "$splash_stop" ]; then
  GAMEPI_FB_HANDOFF_DELAY="${GAMEPI_FB_HANDOFF_DELAY:-0.3}" "$splash_stop"
fi

export FRAMEBUFFER="${FRAMEBUFFER:-/dev/fb0}"
export HOME="${HOME:-/home/dietpi}"

cd "$HOME"
exec runuser -u dietpi -- env HOME="$HOME" FRAMEBUFFER="$FRAMEBUFFER" \
  /usr/bin/startx /opt/midijuggler/app/configs/gamepi/kiosk.xsession \
  -- :0 vt1 -nolisten tcp -nocursor
