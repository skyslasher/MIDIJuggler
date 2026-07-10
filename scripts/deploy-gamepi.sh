#!/bin/sh
# GamePi deploy after git pull (idempotent). Uses the simple splash -> kiosk flow.
#
# On the Pi as root:
#   sudo /opt/midijuggler/app/scripts/deploy-gamepi.sh
#
# Environment:
#   MIDIJUGGLER_APP_ROOT      default: /opt/midijuggler/app
#   MIDIJUGGLER_VENV          default: /opt/midijuggler/venv
#   MIDIJUGGLER_USER          default: midijuggler
#   MIDIJUGGLER_SKIP_GIT_PULL=1   skip git update
#   GAMEPI_PIP_EXTRAS         default: alsa,midi,hid,rotary
#   GAMEPI_RESTART_KIOSK      default: 0 (leave kiosk running; set 1 to restart UI)
#   GAMEPI_SETUP_BRIGHTNESS=1 one-time brightness setup (apt, slow)
set -eu

app_root="${MIDIJUGGLER_APP_ROOT:-/opt/midijuggler/app}"
venv="${MIDIJUGGLER_VENV:-/opt/midijuggler/venv}"
midijuggler_user="${MIDIJUGGLER_USER:-midijuggler}"
pip_extras="${GAMEPI_PIP_EXTRAS:-alsa,midi,hid,rotary}"
restart_kiosk="${GAMEPI_RESTART_KIOSK:-0}"
setup_brightness="${GAMEPI_SETUP_BRIGHTNESS:-0}"
skip_git="${MIDIJUGGLER_SKIP_GIT_PULL:-0}"

step=0
step_echo() {
  step=$((step + 1))
  printf '\n=== [%s] %s ===\n' "$step" "$1" >&2
}

warn() {
  printf 'WARNUNG: %s\n' "$1" >&2
}

fail() {
  printf 'FEHLER: %s\n' "$1" >&2
  exit 1
}

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    fail "Als root ausführen: sudo ${app_root}/scripts/deploy-gamepi.sh"
  fi
}

verify_paths() {
  step_echo "Pfade prüfen"
  if [ ! -d "$app_root" ]; then
    fail "App-Verzeichnis fehlt: ${app_root}"
  fi
  if [ ! -d "${app_root}/.git" ]; then
    fail "Kein Git-Checkout unter ${app_root}"
  fi
  if [ ! -x "${venv}/bin/python" ]; then
    fail "Python-venv fehlt: ${venv}/bin/python"
  fi
  if [ ! -f /etc/midijuggler/config.toml ]; then
    warn "/etc/midijuggler/config.toml fehlt — midijuggler startet ggf. nicht"
  fi
  printf '  app: %s\n' "$app_root" >&2
  printf '  venv: %s\n' "$venv" >&2
  printf '  commit: %s\n' "$(git -C "$app_root" rev-parse --short HEAD 2>/dev/null || echo '?')" >&2
}

git_update() {
  step_echo "Git-Update (pull-midijuggler-app.sh)"
  pull_script="${app_root}/scripts/pull-midijuggler-app.sh"
  if [ "$skip_git" = "1" ]; then
    printf '  übersprungen (MIDIJUGGLER_SKIP_GIT_PULL=1)\n' >&2
    return 0
  fi
  if [ ! -x "$pull_script" ]; then
    fail "Pull-Skript fehlt: ${pull_script}"
  fi
  MIDIJUGGLER_APP_ROOT="$app_root" "$pull_script"
}

pip_install() {
  step_echo "Python-Paket installieren (.[${pip_extras}])"
  pip_bin="${venv}/bin/python"
  if ! "$pip_bin" -m pip install -U pip wheel setuptools >/dev/null; then
    warn "pip/setuptools Update fehlgeschlagen — weiter mit bestehender Version"
  fi
  "$pip_bin" -m pip install -e "${app_root}[${pip_extras}]"
  printf '  extras: %s\n' "$pip_extras" >&2
}

install_midijuggler_unit() {
  step_echo "midijuggler.service installieren"
  unit_src="${app_root}/systemd/midijuggler.service"
  unit_dest="/etc/systemd/system/midijuggler.service"
  if [ ! -f "$unit_src" ]; then
    fail "Unit-Datei fehlt: ${unit_src}"
  fi
  install -m 0644 "$unit_src" "$unit_dest"
  systemctl daemon-reload
  systemctl enable midijuggler.service
}

install_sudoers() {
  step_echo "sudoers für midijuggler installieren"
  example="${app_root}/systemd/midijuggler-sudoers.example"
  dest="/etc/sudoers.d/midijuggler"
  if [ ! -f "$example" ]; then
    fail "sudoers-Vorlage fehlt: ${example}"
  fi
  install -m 0440 "$example" "$dest"
  for helper in set-hostname.sh restart-midijuggler.sh gamepi-reboot.sh; do
    script="${app_root}/scripts/${helper}"
    if [ -f "$script" ]; then
      chmod +x "$script"
    fi
  done
  if ! visudo -c >/dev/null 2>&1; then
    fail "visudo -c fehlgeschlagen — sudoers prüfen"
  fi
}

install_brightness_optional() {
  if [ "$setup_brightness" != "1" ]; then
    return 0
  fi
  step_echo "GamePi-Helligkeit einrichten (install-gamepi13-brightness.sh)"
  brightness_script="${app_root}/scripts/install-gamepi13-brightness.sh"
  if [ ! -x "$brightness_script" ]; then
    fail "Skript fehlt: ${brightness_script}"
  fi
  MIDIJUGGLER_APP_ROOT="$app_root" MIDIJUGGLER_USER="$midijuggler_user" "$brightness_script"
}

install_gamepi_services() {
  step_echo "GamePi-Units und Skripte installieren (install-gamepi13-services.sh)"
  services_script="${app_root}/scripts/install-gamepi13-services.sh"
  if [ ! -x "$services_script" ]; then
    fail "Skript fehlt: ${services_script}"
  fi
  MIDIJUGGLER_APP_ROOT="$app_root" "$services_script"
}

restart_services() {
  step_echo "Dienste neu starten"
  reload_script="${app_root}/scripts/gamepi-reload-after-pull.sh"
  if [ -x "$reload_script" ]; then
    GAMEPI_RELOAD_KIOSK="$restart_kiosk" MIDIJUGGLER_SKIP_GIT_PULL=1 "$reload_script"
    return 0
  fi

  wait_script="${app_root}/scripts/wait-for-midijuggler-web.sh"
  systemctl restart midijuggler.service
  if [ -x "$wait_script" ]; then
    "$wait_script" || warn "Web-UI nicht rechtzeitig erreichbar"
  fi
  if [ "$restart_kiosk" = "1" ]; then
    systemctl restart gamepi-kiosk.service 2>/dev/null || true
  fi
}

run_health_check() {
  step_echo "Display-Health prüfen"
  health_script="${app_root}/scripts/gamepi-display-health.sh"
  if [ -x "$health_script" ]; then
    GAMEPI_DIAGNOSE=1 "$health_script" || warn "gamepi-display-health meldet Probleme"
  fi
  printf '  midijuggler: %s\n' "$(systemctl is-active midijuggler.service 2>/dev/null || echo '?')" >&2
  printf '  gamepi-kiosk: %s\n' "$(systemctl is-active gamepi-kiosk.service 2>/dev/null || echo '?')" >&2
}

print_checklist() {
  step_echo "Verifikation"
  cat <<EOF >&2

Deploy abgeschlossen.

  git -C ${app_root} rev-parse --short HEAD
  systemctl is-active midijuggler.service
  curl -fsS http://127.0.0.1:8080/static/clock-gamepi.html -o /dev/null && echo ok
  systemctl is-active gamepi-kiosk.service

Nach Deploy ohne Kiosk-Neustart (Standard):
  sudo GAMEPI_RELOAD_KIOSK=0 ${app_root}/scripts/gamepi-reload-after-pull.sh

Kiosk neu starten:
  sudo GAMEPI_RELOAD_KIOSK=1 ${app_root}/scripts/gamepi-reload-after-pull.sh

Bei schwarzem Bildschirm:
  sudo ${app_root}/scripts/gamepi-recover-display.sh
  sudo reboot

Details: ${app_root}/docs/gamepi-deploy.md

EOF
}

main() {
  require_root
  verify_paths
  git_update
  pip_install
  install_midijuggler_unit
  install_sudoers
  install_brightness_optional
  install_gamepi_services
  restart_services
  run_health_check
  print_checklist
  printf '\nFertig.\n' >&2
}

main "$@"
