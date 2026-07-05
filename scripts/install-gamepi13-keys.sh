#!/bin/sh
set -eu

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
profile="${GAMEPI_KEYS_PROFILE:-standard}"
boot_config="${GAMEPI_BOOT_CONFIG:-/boot/firmware/config.txt}"

case "$profile" in
  x1207)
    keys_conf="${repo_root}/configs/gamepi/gamepi13-gpio-keys-x1207.conf"
    profile_label="GamePi13 + X1207"
    ;;
  standard | "")
    keys_conf="${repo_root}/configs/gamepi/gamepi13-gpio-keys.conf"
    profile_label="GamePi13"
    ;;
  *)
    echo "unknown GAMEPI_KEYS_PROFILE=${profile} (use standard or x1207)" >&2
    exit 1
    ;;
esac

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
  echo "${profile_label} gpio-key lines already present in ${boot_config}"
  echo "To switch profiles, edit ${boot_config} manually and replace the GamePi13 overlay block."
  exit 0
fi

{
  echo
  echo "# ${profile_label} keyboard mapping (MIDIJuggler)"
  grep -v '^#' "$keys_conf" | sed '/^[[:space:]]*$/d'
} >>"$boot_config"

echo "Appended ${profile_label} gpio-key overlays to ${boot_config}"
echo "Reboot to activate keyboard mapping."
