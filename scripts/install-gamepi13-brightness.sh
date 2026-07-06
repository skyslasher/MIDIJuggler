#!/bin/sh
# One-time setup for GamePi brightness (sysfs, GPIO PWM, or xgamma fallback).
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
apply_script="${repo_root}/scripts/gamepi-apply-gamma.sh"
venv_python="${MIDIJUGGLER_VENV:-/opt/midijuggler/venv}/bin/python"
state_dir="/var/lib/gamepi"
sudoers_file="/etc/sudoers.d/midijuggler-gamepi-brightness"
midijuggler_user="${MIDIJUGGLER_USER:-midijuggler}"

if [ ! -x "$apply_script" ]; then
  chmod +x "$apply_script"
fi

if command -v apt-get >/dev/null 2>&1; then
  apt-get install -y x11-xserver-utils python3-libgpiod >/dev/null 2>&1 \
    || apt-get install -y x11-xserver-utils python3-libgpiod
fi

if [ -x "$venv_python" ]; then
  "$venv_python" -m pip install -q rpi-lgpio
else
  echo "warning: ${venv_python} not found; install rpi-lgpio in the MIDIJuggler venv manually" >&2
fi

mkdir -p "$state_dir"
if id "$midijuggler_user" >/dev/null 2>&1; then
  chown root:"$midijuggler_user" "$state_dir"
  chmod 775 "$state_dir"
else
  chmod 755 "$state_dir"
fi

install -m 440 /dev/stdin "$sudoers_file" <<EOF
# Allow midijuggler web UI to adjust GamePi gamma fallback brightness.
${midijuggler_user} ALL=(root) NOPASSWD: ${apply_script}
EOF

echo "installed ${sudoers_file}"
echo "state dir: ${state_dir}"
echo "apply script: ${apply_script}"
if [ -d /sys/class/backlight ] && [ -n "$(ls -A /sys/class/backlight 2>/dev/null || true)" ]; then
  echo "hardware backlight detected under /sys/class/backlight"
else
  echo "no sysfs backlight — GPIO PWM on GAMEPI_BACKLIGHT_GPIO (default 18) will be used"
fi
