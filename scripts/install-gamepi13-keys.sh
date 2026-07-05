#!/bin/sh
set -eu

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
keys_conf="${repo_root}/configs/gamepi/gamepi13-gpio-keys.conf"
boot_config="${GAMEPI_BOOT_CONFIG:-/boot/firmware/config.txt}"

if [ ! -f "$keys_conf" ]; then
  echo "missing ${keys_conf}" >&2
  exit 1
fi

if [ ! -f "$boot_config" ]; then
  boot_config=/boot/config.txt
fi

if [ ! -f "$boot_config" ]; then
  echo "boot config not found (set GAMEPI_BOOT_CONFIG)" >&2
  exit 1
fi

if grep -q 'label="GPSTART"' "$boot_config" 2>/dev/null; then
  echo "GamePi13 gpio-key lines already present in ${boot_config}"
  exit 0
fi

{
  echo
  echo "# GamePi13 keyboard mapping (MIDIJuggler)"
  grep -v '^#' "$keys_conf" | sed '/^[[:space:]]*$/d'
} >>"$boot_config"

echo "Appended GamePi13 gpio-key overlays to ${boot_config}"
echo "Reboot to activate keyboard mapping."
