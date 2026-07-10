#!/bin/sh
# Install GamePi13 systemd units and helper scripts from the app checkout.
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
app_root="${MIDIJUGGLER_APP_ROOT:-$repo_root}"
unit_src_dir="${repo_root}/systemd"
unit_dir="${GAMEPI_SYSTEMD_DIR:-/etc/systemd/system}"

units="
  gamepi-splash.service
  gamepi-kiosk-ready.service
  gamepi-kiosk.service
  gamepi-blanking-watch.service
  gamepi-brightness-keys.service
"

tmpfiles_src="${repo_root}/systemd/gamepi-tmpfiles.conf"
tmpfiles_dest="/etc/tmpfiles.d/gamepi.conf"

scripts="
  scripts/gamepi-paths.sh
  scripts/gamepi-disable-blanking.sh
  scripts/gamepi-blanking-watch.sh
  scripts/gamepi-kiosk-diagnostics.sh
  scripts/gamepi-display-health.sh
  scripts/gamepi-recover-display.sh
  scripts/wait-for-midijuggler-web.sh
  scripts/wait-for-fb0.sh
  scripts/gamepi-boot-splash.sh
  scripts/gamepi-splash-stop.sh
  scripts/gamepi-fb-handoff.sh
  scripts/gamepi-fbcon.sh
  scripts/gamepi-start-kiosk.sh
  scripts/gamepi-launch-kiosk.sh
  configs/gamepi/kiosk.xsession
"

echo "Installing GamePi13 units to ${unit_dir}" >&2
for unit in $units; do
  src="${unit_src_dir}/${unit}"
  if [ ! -f "$src" ]; then
    echo "missing unit: ${src}" >&2
    exit 1
  fi
  install -m 0644 "$src" "${unit_dir}/${unit}"
done

if [ -f "$tmpfiles_src" ]; then
  echo "Installing tmpfiles.d for /run/gamepi" >&2
  install -m 0644 "$tmpfiles_src" "$tmpfiles_dest"
  if command -v systemd-tmpfiles >/dev/null 2>&1; then
    systemd-tmpfiles --create "$tmpfiles_dest"
  fi
fi

echo "Installing executable GamePi13 scripts" >&2
for script in $scripts; do
  src="${app_root}/${script}"
  if [ ! -f "$src" ]; then
    echo "missing script: ${src}" >&2
    exit 1
  fi
  dest="${app_root}/${script}"
  chmod +x "$dest"
done

if [ -x "${app_root}/scripts/install-gamepi13-xorg.sh" ]; then
  "${app_root}/scripts/install-gamepi13-xorg.sh"
fi

systemctl daemon-reload
systemctl enable gamepi-splash.service gamepi-kiosk-ready.service gamepi-kiosk.service \
  gamepi-blanking-watch.service gamepi-brightness-keys.service

echo "Installed. Restart with:" >&2
echo "  sudo systemctl restart gamepi-splash.service gamepi-kiosk-ready.service gamepi-kiosk.service gamepi-blanking-watch.service" >&2
echo "Or reboot for a clean splash -> kiosk handoff." >&2
