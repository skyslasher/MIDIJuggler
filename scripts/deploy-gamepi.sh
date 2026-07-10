#!/bin/sh
# Vollständiges GamePi-Deployment nach git pull (idempotent).
#
# Auf dem Pi als root ausführen:
#   sudo /opt/midijuggler/app/scripts/deploy-gamepi.sh
#
# Umgebungsvariablen:
#   MIDIJUGGLER_APP_ROOT      Standard: /opt/midijuggler/app
#   MIDIJUGGLER_VENV          Standard: /opt/midijuggler/venv
#   MIDIJUGGLER_USER          Standard: midijuggler
#   GAMEPI_USER               Standard: dietpi
#   MIDIJUGGLER_SKIP_GIT_PULL=1   Git-Update überspringen
#   GAMEPI_PIP_EXTRAS         Standard: alsa,midi,hid,rotary
#   GAMEPI_RESTART_KIOSK      Standard: 1 (Kiosk nach Deploy neu starten)
#   GAMEPI_SETUP_BRIGHTNESS=1 Einmal-Setup Helligkeit (apt, langsam)
set -eu

app_root="${MIDIJUGGLER_APP_ROOT:-/opt/midijuggler/app}"
venv="${MIDIJUGGLER_VENV:-/opt/midijuggler/venv}"
midijuggler_user="${MIDIJUGGLER_USER:-midijuggler}"
gamepi_user="${GAMEPI_USER:-dietpi}"
pip_extras="${GAMEPI_PIP_EXTRAS:-alsa,midi,hid,rotary}"
restart_kiosk="${GAMEPI_RESTART_KIOSK:-1}"
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
  if ! "$pip_bin" -c "import zeroconf" 2>/dev/null; then
    warn "python-zeroconf fehlt — Encoder mDNS braucht pip extra rotary oder avahi-utils"
  fi
  if ! "$pip_bin" -c "import serial" 2>/dev/null; then
    warn "pyserial fehlt — Encoder USB braucht pip extra rotary"
  fi
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
  for helper in set-hostname.sh restart-midijuggler.sh gamepi-reboot.sh gamepi-disable-blanking.sh; do
    script="${app_root}/scripts/${helper}"
    if [ -f "$script" ]; then
      chmod +x "$script"
    fi
  done
  if ! visudo -c >/dev/null 2>&1; then
    fail "visudo -c fehlgeschlagen — sudoers prüfen"
  fi
  if [ ! -f /etc/sudoers.d/midijuggler-gamepi-brightness ]; then
    warn "Helligkeit-sudoers fehlt — einmalig: sudo ${app_root}/scripts/install-gamepi13-brightness.sh"
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

ensure_avahi() {
  step_echo "avahi-daemon für Encoder-mDNS prüfen"
  if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-enabled avahi-daemon >/dev/null 2>&1; then
      systemctl enable avahi-daemon >/dev/null 2>&1 || true
      systemctl start avahi-daemon >/dev/null 2>&1 || true
    fi
  fi
  if command -v avahi-resolve-host-name >/dev/null 2>&1; then
    printf '  avahi-resolve-host-name: ok\n' >&2
  else
    warn "avahi-utils fehlt — sudo apt install -y avahi-daemon avahi-utils"
  fi
}

enable_gamepi_units() {
  step_echo "GamePi-Units aktivieren"
  systemctl daemon-reload
  systemctl enable \
    midijuggler.service \
    gamepi-splash.service \
    gamepi-kiosk-ready.service \
    gamepi-kiosk.service \
    gamepi-blanking-watch.service \
    gamepi-brightness-keys.service
}

restart_services() {
  step_echo "Dienste neu starten"
  wait_script="${app_root}/scripts/wait-for-midijuggler-web.sh"
  recover_script="${app_root}/scripts/gamepi-recover-display.sh"

  printf '  midijuggler.service …\n' >&2
  systemctl restart midijuggler.service
  if [ -x "$wait_script" ]; then
    "$wait_script" || warn "Web-UI nicht rechtzeitig erreichbar"
  fi

  for unit in gamepi-blanking-watch.service gamepi-brightness-keys.service; do
    if systemctl is-enabled "$unit" >/dev/null 2>&1; then
      printf '  %s …\n' "$unit" >&2
      systemctl restart "$unit" 2>/dev/null || true
    fi
  done

  if [ "$restart_kiosk" = "1" ]; then
    printf '  gamepi-kiosk-ready.service + gamepi-kiosk.service …\n' >&2
    systemctl restart gamepi-kiosk-ready.service 2>/dev/null || true
    if systemctl is-active --quiet gamepi-kiosk.service; then
      systemctl restart gamepi-kiosk.service
    elif systemctl is-enabled gamepi-kiosk.service >/dev/null 2>&1; then
      systemctl start gamepi-kiosk.service
    fi
    if [ -x "$recover_script" ]; then
      recover_deadline=$(($(date +%s) + 30))
      while [ "$(date +%s)" -lt "$recover_deadline" ]; do
        if systemctl is-active --quiet gamepi-kiosk.service && \
           systemctl is-active --quiet midijuggler.service; then
          break
        fi
        sleep 1
      done
      sleep 3
      GAMEPI_RECOVER_FORCE=1 "$recover_script" || warn "Display-Recovery meldet Probleme"
    fi
  else
    printf '  Kiosk-Neustart übersprungen (GAMEPI_RESTART_KIOSK=0)\n' >&2
    if [ -x "$recover_script" ]; then
      GAMEPI_RECOVER_FORCE=0 GAMEPI_RECOVER_X_SETTLE=8 "$recover_script" || true
    fi
  fi
}

run_diagnostics() {
  step_echo "Diagnose ausführen"
  health_script="${app_root}/scripts/gamepi-display-health.sh"
  diag_script="${app_root}/scripts/gamepi-kiosk-diagnostics.sh"

  if [ -x "$health_script" ]; then
    if GAMEPI_DIAGNOSE=1 "$health_script"; then
      printf '  gamepi-display-health: OK\n' >&2
    else
      warn "gamepi-display-health meldet Probleme (siehe oben)"
    fi
  fi

  if [ -x "$diag_script" ]; then
    "$diag_script" || true
  fi

  printf '  midijuggler: %s\n' "$(systemctl is-active midijuggler.service 2>/dev/null || echo '?')" >&2
  printf '  gamepi-kiosk: %s\n' "$(systemctl is-active gamepi-kiosk.service 2>/dev/null || echo '?')" >&2
  printf '  fb0 blank: %s (0=an)\n' "$(cat /sys/class/graphics/fb0/blank 2>/dev/null || echo '?')" >&2
}

print_checklist() {
  step_echo "Verifikations-Checkliste"
  cat <<EOF >&2

Deploy abgeschlossen. Erwartete Werte:

  git -C ${app_root} rev-parse --short HEAD
    → aktueller Commit (nicht der alte Stand vor dem Pull)

  systemctl is-active midijuggler.service
    → active

  curl -fsS http://127.0.0.1:8080/static/clock-gamepi.html -o /dev/null && echo ok
    → ok

  ${app_root}/scripts/gamepi-display-health.sh && echo display ok
    → display ok (Exit 0)

  cat /sys/class/graphics/fb0/blank
    → 0

  systemctl is-active gamepi-kiosk.service
    → active

Encoder OSC (nach Deploy immer nötig):
  ${venv}/bin/python -c "import zeroconf, serial; print('rotary deps ok')"
    → rotary deps ok
  journalctl -u midijuggler.service -n 30 --no-pager | grep -i rotary
    → hello/sync Meldungen nach Encoder-Neustart

Bei schwarzem Bildschirm:
  sudo ${app_root}/scripts/gamepi-recover-display.sh
  sudo reboot

Vollständige Anleitung: ${app_root}/docs/gamepi-deploy.md

EOF
}

main() {
  require_root
  printf 'GamePi-Deploy starten (commit vor Deploy: %s)\n' \
    "$(git -C "$app_root" rev-parse --short HEAD 2>/dev/null || echo '?')" >&2
  verify_paths
  git_update
  pip_install
  install_midijuggler_unit
  install_sudoers
  install_brightness_optional
  install_gamepi_services
  ensure_avahi
  enable_gamepi_units
  restart_services
  run_diagnostics
  print_checklist
  printf '\nFertig.\n' >&2
}

main "$@"
