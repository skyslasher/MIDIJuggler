#!/bin/sh
# Return 0 when the Start button is pressed.
# Uses gpio-keys evdev only; gpioget does not work on overlay-owned GPIO lines.

python_bin="${GAMEPI_PYTHON:-/opt/midijuggler/venv/bin/python}"
pressed_py="${GAMEPI_START_PRESSED_PY:-/opt/midijuggler/app/scripts/gamepi-is-start-pressed.py}"

if [ ! -x "$python_bin" ] || [ ! -f "$pressed_py" ]; then
  echo "Start detection unavailable: missing ${python_bin} or ${pressed_py}" >&2
  exit 1
fi

exec "$python_bin" "$pressed_py"
