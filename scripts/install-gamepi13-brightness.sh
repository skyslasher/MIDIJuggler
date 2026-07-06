#!/bin/sh
# One-time setup for GamePi brightness (sysfs, GPIO PWM, or xgamma fallback).
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
apply_script="${repo_root}/scripts/gamepi-apply-gamma.sh"
state_dir="/var/lib/gamepi"
sudoers_file="/etc/sudoers.d/midijuggler-gamepi-brightness"
midijuggler_user="${MIDIJUGGLER_USER:-midijuggler}"
brightness_python="/usr/bin/python3"

if [ ! -x "$apply_script" ]; then
  chmod +x "$apply_script"
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "apt-get not found; install python3-rpi-lgpio and python3-evdev manually" >&2
  exit 1
fi

apt-get update
apt-get install -y x11-xserver-utils python3-libgpiod python3-evdev

if apt-cache show python3-rpi-lgpio >/dev/null 2>&1; then
  apt-get install -y python3-rpi-lgpio
else
  echo "python3-rpi-lgpio not in apt; installing build deps for pip fallback" >&2
  apt-get install -y swig python3-dev
  if [ -x /opt/midijuggler/venv/bin/pip ]; then
    /opt/midijuggler/venv/bin/pip install rpi-lgpio || true
  fi
  brightness_python="/opt/midijuggler/venv/bin/python"
fi

if ! (cd "$state_dir" && "$brightness_python" -c "import lgpio") 2>/dev/null; then
  echo "error: lgpio not available in ${brightness_python}" >&2
  echo "try: sudo apt-get install -y python3-rpi-lgpio" >&2
  exit 1
fi

mkdir -p "$state_dir"
chmod 1777 "$state_dir"
if id "$midijuggler_user" >/dev/null 2>&1; then
  chown root:"$midijuggler_user" "$state_dir" 2>/dev/null || true
fi

install -m 440 /dev/stdin "$sudoers_file" <<EOF
# Allow midijuggler web UI to adjust GamePi gamma fallback brightness.
${midijuggler_user} ALL=(root) NOPASSWD: ${apply_script}
EOF

brightness_env="/etc/midijuggler/brightness.env"
mkdir -p /etc/midijuggler
install -m 644 /dev/stdin "$brightness_env" <<EOF
GAMEPI_BRIGHTNESS_PYTHON=${brightness_python}
EOF

echo "installed ${sudoers_file}"
echo "installed ${brightness_env} (GAMEPI_BRIGHTNESS_PYTHON=${brightness_python})"
echo "state dir: ${state_dir}"
if [ -d /sys/class/backlight ] && [ -n "$(ls -A /sys/class/backlight 2>/dev/null || true)" ]; then
  echo "hardware backlight detected under /sys/class/backlight"
else
  echo "no sysfs backlight — GPIO PWM on GAMEPI_BACKLIGHT_GPIO (default 18) will be used"
fi

PYTHONPATH="${repo_root}/scripts" "$brightness_python" - <<'PY'
from gamepi_lgpio_env import prepare_lgpio_runtime
prepare_lgpio_runtime()
import lgpio
print("lgpio ok")
PY
