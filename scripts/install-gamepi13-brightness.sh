#!/bin/sh
# One-time setup for GamePi brightness (sysfs, GPIO PWM, or xgamma fallback).
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
apply_script="${repo_root}/scripts/gamepi-apply-gamma.sh"
run_script="${repo_root}/scripts/gamepi-brightness-run.sh"
state_dir="/var/lib/gamepi"
sudoers_file="/etc/sudoers.d/midijuggler-gamepi-brightness"
midijuggler_user="${MIDIJUGGLER_USER:-midijuggler}"
brightness_python="/usr/bin/python3"

chmod +x "$apply_script" "$run_script"

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

mkdir -p "$state_dir"
chown root:root "$state_dir"
chmod 755 "$state_dir"
rm -f "$state_dir"/.lgd-nfy* 2>/dev/null || true

if ! (cd "$state_dir" && "$brightness_python" -c "import lgpio") 2>/dev/null; then
  if ! (cd "$state_dir" && sudo "$brightness_python" -c "import lgpio") 2>/dev/null; then
    echo "error: lgpio not available in ${brightness_python}" >&2
    echo "try: sudo apt-get install -y python3-rpi-lgpio" >&2
    exit 1
  fi
fi

install -m 440 /dev/stdin "$sudoers_file" <<EOF
# GamePi brightness: lgpio needs root in /var/lib/gamepi.
${midijuggler_user} ALL=(root) NOPASSWD: ${run_script}
${midijuggler_user} ALL=(root) NOPASSWD: ${apply_script}
EOF

brightness_env="/etc/midijuggler/brightness.env"
mkdir -p /etc/midijuggler
install -m 644 /dev/stdin "$brightness_env" <<EOF
GAMEPI_BRIGHTNESS_PYTHON=${brightness_python}
GAMEPI_LGPIO_DIR=${state_dir}
MIDIJUGGLER_APP_ROOT=${repo_root}
EOF

echo "installed ${sudoers_file}"
echo "installed ${brightness_env}"
echo "state dir: ${state_dir} (root:root 755 — brightness runs via sudo)"
if [ -d /sys/class/backlight ] && [ -n "$(ls -A /sys/class/backlight 2>/dev/null || true)" ]; then
  echo "hardware backlight detected under /sys/class/backlight"
else
  echo "no sysfs backlight — GPIO PWM on GAMEPI_BACKLIGHT_GPIO (default 18) will be used"
fi

sudo env PYTHONPATH="${repo_root}/scripts" "$run_script" --status
echo "brightness CLI ok"
