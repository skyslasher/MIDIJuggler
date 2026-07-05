#!/bin/sh
# Reset the dedicated GamePi kiosk Chromium profile (fresh static assets after deploy).

set -eu

if [ "${GAMEPI_CHROMIUM_CLEAR_CACHE:-1}" = "0" ]; then
  exit 0
fi

home="${HOME:-/home/dietpi}"
profile="${GAMEPI_CHROMIUM_USER_DATA_DIR:-${home}/.cache/midijuggler-kiosk}"

if [ -d "$profile" ]; then
  rm -rf "$profile"
fi
mkdir -p "$profile"
