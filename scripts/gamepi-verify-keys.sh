#!/bin/sh
# Show GamePi keyboard overlays, boot conflicts, and evdev button devices.
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${repo_root}/scripts:${PYTHONPATH:-}"

boot_config="${GAMEPI_BOOT_CONFIG:-/boot/firmware/config.txt}"
if [ ! -f "$boot_config" ]; then
  boot_config=/boot/config.txt
fi

echo "boot config: ${boot_config}"
echo
echo "GamePi overlays:"
grep -E 'label="GP|gpio-key' "$boot_config" 2>/dev/null || echo "(none found)"
echo

if command -v python3 >/dev/null 2>&1; then
  python3 - <<'PY'
import json
import sys

from gamepi_gpio_keys import (
    boot_config_overlay_line,
    boot_config_uart_reserves_gpio_14,
    boot_config_warnings,
    brightness_input_warnings,
    describe_input_devices,
    dmesg_gpio_key_hints,
    gpio_button_name,
    resolve_boot_config,
    verify_keys_ok,
)

boot = resolve_boot_config()
print("boot diagnostics:")
for warning in boot_config_warnings():
    print(f"  WARNING: {warning}")
if not boot_config_warnings():
    print("  (no boot config conflicts detected)")

gpr = boot_config_overlay_line("GPR")
if gpr:
    print(f"GPR overlay line: {gpr}")
else:
    print("GPR overlay line: (missing)")

if boot_config_uart_reserves_gpio_14():
    print("UART on GPIO 14/15: likely ENABLED (blocks button@e until disabled)")

hints = dmesg_gpio_key_hints()
if hints:
    print("dmesg gpio-key hints:")
    for hint in hints:
        print(f"  {hint}")

print()
print("evdev button devices:")
for entry in describe_input_devices():
    name = entry["name"]
    if not str(name).startswith("button@"):
        continue
    print(f"{entry['path']}\t{name}\tkeys={entry['keys']}")

expected = gpio_button_name(14)
print()
print(f"expected R shoulder: {expected} (GPIO 14, key 225)")
for warning in brightness_input_warnings():
    print(f"WARNING: {warning}")

sys.exit(0 if verify_keys_ok() else 1)
PY
else
  echo "evdev button devices:"
  grep -H "" /sys/class/input/input*/name 2>/dev/null || true
  exit 1
fi
