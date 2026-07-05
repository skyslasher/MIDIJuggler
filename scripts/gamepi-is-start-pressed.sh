#!/bin/sh
# Return 0 when the Start button (GPIO 26, active low) is pressed.

gpio="${GAMEPI_START_GPIO:-26}"
chip="${GAMEPI_START_GPIO_CHIP:-gpiochip0}"

if ! command -v gpioget >/dev/null 2>&1; then
  exit 1
fi

# libgpiod v2: gpioget -c chip line; v1: gpioget chip line
value="$(gpioget -c "$chip" "$gpio" 2>/dev/null)" \
  || value="$(gpioget "$chip" "$gpio" 2>/dev/null)" \
  || exit 1
[ "$value" = "0" ]
