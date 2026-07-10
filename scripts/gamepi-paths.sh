#!/bin/sh
# Shared GamePi runtime paths. Source from other scripts: . "$0/../gamepi-paths.sh"

gamepi_splash_completed_flag() {
  if [ -n "${GAMEPI_SPLASH_COMPLETED_FLAG:-}" ]; then
    printf '%s\n' "$GAMEPI_SPLASH_COMPLETED_FLAG"
    return 0
  fi
  if [ -d /run/gamepi ]; then
    printf '%s\n' /run/gamepi/splash-completed
    return 0
  fi
  if [ -n "${XDG_RUNTIME_DIR:-}" ] && [ -d "$XDG_RUNTIME_DIR" ]; then
    printf '%s\n' "${XDG_RUNTIME_DIR}/gamepi-splash-completed"
    return 0
  fi
  printf '%s\n' /tmp/gamepi-splash-completed
}

gamepi_mark_splash_completed() {
  flag="$(gamepi_splash_completed_flag)"
  dir="$(dirname "$flag")"
  if [ ! -d "$dir" ]; then
    mkdir -p "$dir" 2>/dev/null || true
  fi
  if : >"$flag" 2>/dev/null; then
    gamepi_user="${GAMEPI_USER:-dietpi}"
    if [ "$(id -u)" -eq 0 ] && id "$gamepi_user" >/dev/null 2>&1; then
      chown "${gamepi_user}:${gamepi_user}" "$flag" 2>/dev/null || true
    fi
    return 0
  fi
  echo "warning: could not mark splash completed (${flag})" >&2
  return 0
}
