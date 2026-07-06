#!/bin/sh
# Show GamePi keyboard overlays in boot config and evdev button devices.
set -eu

boot_config="${GAMEPI_BOOT_CONFIG:-/boot/firmware/config.txt}"
if [ ! -f "$boot_config" ]; then
  boot_config=/boot/config.txt
fi

echo "boot config: ${boot_config}"
echo
echo "GamePi overlays:"
grep -E 'label="GP|gpio-key' "$boot_config" 2>/dev/null || echo "(none found)"
echo
echo "evdev button devices:"
if command -v python3 >/dev/null 2>&1; then
  PYTHONPATH=/opt/midijuggler/app/scripts python3 - <<'PY'
from gamepi_gpio_keys import describe_input_devices

for entry in describe_input_devices():
    name = entry["name"]
    if not str(name).startswith("button@"):
        continue
    print(f"{entry['path']}\t{name}\tkeys={entry['keys']}")
PY
else
  grep -H "" /sys/class/input/input*/name 2>/dev/null || true
fi
