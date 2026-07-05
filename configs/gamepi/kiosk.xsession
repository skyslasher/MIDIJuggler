#!/bin/sh
export FRAMEBUFFER=/dev/fb0

/opt/midijuggler/app/scripts/gamepi-disable-blanking.sh

if command -v unclutter >/dev/null 2>&1; then
  unclutter -idle 0 &
fi

if command -v xset >/dev/null 2>&1; then
  xset s off
  xset -dpms
  xset s noblank
fi

exec chromium --kiosk --noerrdialogs --disable-infobars \
  --window-size=240,240 \
  http://127.0.0.1:8080/static/clock-remote.html
