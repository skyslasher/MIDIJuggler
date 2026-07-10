#!/bin/sh
set -eu

scripts_dir="${MIDIJUGGLER_SCRIPTS_DIR:-/opt/midijuggler/app/scripts}"
. "${scripts_dir}/gamepi-paths.sh"

completed_flag="$(gamepi_splash_completed_flag)"
splash_active=false
if [ -f /run/gamepi-splash-hold ] || pgrep -x fbi >/dev/null 2>&1; then
  splash_active=true
fi

if [ "$splash_active" = true ] || [ ! -f "$completed_flag" ]; then
  if [ -x "${scripts_dir}/gamepi-splash-stop.sh" ]; then
    GAMEPI_FB_HANDOFF_DELAY="${GAMEPI_FB_HANDOFF_DELAY:-0.3}" \
      "${scripts_dir}/gamepi-splash-stop.sh" || true
  fi
fi

exec "${scripts_dir}/gamepi-start-kiosk.sh"
