#!/bin/sh
set -eu

scripts_dir="${MIDIJUGGLER_SCRIPTS_DIR:-/opt/midijuggler/app/scripts}"

if [ -x "${scripts_dir}/gamepi-splash-stop.sh" ]; then
  GAMEPI_FB_HANDOFF_DELAY="${GAMEPI_FB_HANDOFF_DELAY:-0.3}" \
    "${scripts_dir}/gamepi-splash-stop.sh"
fi

exec "${scripts_dir}/gamepi-start-kiosk.sh"
