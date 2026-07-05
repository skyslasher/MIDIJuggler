#!/bin/sh
# Append consoleblank=0 to the Pi boot cmdline if missing (requires reboot).
set -eu

cmdline="${GAMEPI_CMDLINE:-/boot/firmware/cmdline.txt}"

if [ ! -f "$cmdline" ]; then
  cmdline=/boot/cmdline.txt
fi

if [ ! -f "$cmdline" ]; then
  echo "boot cmdline not found (set GAMEPI_CMDLINE)" >&2
  exit 1
fi

if grep -qE '(^|[[:space:]])consoleblank=0([[:space:]]|$)' "$cmdline"; then
  echo "consoleblank=0 already set in ${cmdline}"
  exit 0
fi

sed -i 's/$/ consoleblank=0/' "$cmdline"
echo "Appended consoleblank=0 to ${cmdline} — reboot to apply"
