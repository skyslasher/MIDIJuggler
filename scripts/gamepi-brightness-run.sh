#!/bin/sh
# Run brightness adjust/status as root (lgpio notify pipes need root-owned /var/lib/gamepi).
set -eu

repo_root="${MIDIJUGGLER_APP_ROOT:-/opt/midijuggler/app}"
state_dir="${GAMEPI_LGPIO_DIR:-/var/lib/gamepi}"
python="${GAMEPI_BRIGHTNESS_PYTHON:-/usr/bin/python3}"
adjust="${repo_root}/scripts/gamepi-brightness-adjust.py"

mkdir -p "$state_dir"
cd "$state_dir"
exec "$python" "$adjust" "$@"
