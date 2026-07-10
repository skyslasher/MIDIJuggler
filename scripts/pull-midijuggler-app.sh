#!/bin/sh
# Update the Pi app clone from git. Discards local edits under scripts/ and configs/gamepi/.
#
# Use this instead of plain `git pull` on the GamePi — manual edits and chmod-only
# diffs there otherwise block updates.

set -eu

app_root="${MIDIJUGGLER_APP_ROOT:-/opt/midijuggler/app}"
branch="${MIDIJUGGLER_GIT_BRANCH:-main}"
run_user="${MIDIJUGGLER_GIT_USER:-midijuggler}"

run_git() {
  if [ "$(id -un)" = "$run_user" ]; then
    "$@"
  else
    sudo -u "$run_user" "$@"
  fi
}

if [ ! -d "${app_root}/.git" ]; then
  echo "not a git checkout: ${app_root}" >&2
  exit 1
fi

cd "$app_root"

echo "Fetching origin/${branch}..." >&2
run_git git fetch origin "$branch"

echo "Resetting deploy-managed paths to origin/${branch}..." >&2
run_git git checkout "origin/${branch}" -- scripts configs/gamepi

echo "Fast-forwarding to origin/${branch}..." >&2
run_git git merge --ff-only "origin/${branch}"

for script in scripts/gamepi-*.sh scripts/pull-midijuggler-app.sh scripts/wait-for-*.sh \
  scripts/deploy-gamepi.sh scripts/install-gamepi13-*.sh; do
  [ -f "$script" ] || continue
  chmod +x "$script"
done
chmod +x configs/gamepi/kiosk.xsession 2>/dev/null || true

echo "Now at $(run_git git rev-parse --short HEAD)" >&2
