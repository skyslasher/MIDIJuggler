#!/bin/sh
# Return 0 when the Start button is pressed.
# Prefer gpio-keys evdev (GPIO is owned by the kernel overlay); gpioget is fallback only.

gpio="${GAMEPI_START_GPIO:-26}"
chip="${GAMEPI_START_GPIO_CHIP:-gpiochip0}"
python_bin="${GAMEPI_PYTHON:-/opt/midijuggler/venv/bin/python}"
pressed_py="${GAMEPI_START_PRESSED_PY:-/opt/midijuggler/app/scripts/gamepi-is-start-pressed.py}"

if [ -x "$python_bin" ] && [ -f "$pressed_py" ]; then
  if "$python_bin" "$pressed_py"; then
    exit 0
  fi
fi

if ! command -v gpioget >/dev/null 2>&1; then
  exit 1
fi

# libgpiod v2: "26"=active/inactive; v1: 0/1
value="$(gpioget -c "$chip" "$gpio" 2>/dev/null)" \
  || value="$(gpioget "$chip" "$gpio" 2>/dev/null)" \
  || exit 1

case "$value" in
  0 | *'=active'*) exit 0 ;;
esac
exit 1
