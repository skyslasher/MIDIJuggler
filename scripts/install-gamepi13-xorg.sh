#!/bin/sh
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
src="${repo_root}/configs/gamepi/99-fbdev.conf"
dest_dir="/etc/X11/xorg.conf.d"
dest="${dest_dir}/99-fbdev.conf"

if [ ! -f "$src" ]; then
  echo "missing ${src}" >&2
  exit 1
fi

mkdir -p "$dest_dir"
install -m 644 "$src" "$dest"
echo "installed ${dest}"
