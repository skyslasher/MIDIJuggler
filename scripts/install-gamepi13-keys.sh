#!/bin/sh
# Ensure all GamePi13 gpio-key overlays from the repo are present in boot config.
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

added=0
while IFS= read -r line; do
  case "$line" in
    "" | \#*) continue ;;
  esac
  label=$(printf '%s\n' "$line" | sed -n 's/.*label="\([^"]*\)".*/\1/p')
  if [ -z "$label" ]; then
    continue
  fi
  if grep -q "label=\"${label}\"" "$boot_config" 2>/dev/null; then
    continue
  fi
  if [ "$added" -eq 0 ]; then
    {
      echo
      echo "# ${profile_label} keyboard mapping (MIDIJuggler)"
    } >>"$boot_config"
    added=1
  fi
  echo "$line" >>"$boot_config"
  echo "added missing overlay: ${label}"
done <"$keys_conf"

if [ "$added" -eq 0 ]; then
  echo "${profile_label} gpio-key overlays already complete in ${boot_config}"
else
  echo "Reboot to activate new keyboard overlays."
fi

if command -v python3 >/dev/null 2>&1; then
  PYTHONPATH="${repo_root}/scripts" python3 - <<'PY' || true
from gamepi_gpio_keys import boot_config_overlay_line, boot_config_warnings

gpr = boot_config_overlay_line("GPR")
if gpr and "gpio=14" not in gpr:
    print(f"warning: GPR overlay does not use gpio=14: {gpr}", flush=True)

for warning in boot_config_warnings():
    print(f"warning: {warning}", flush=True)
PY
fi
