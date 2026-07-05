#!/bin/sh
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
src="${repo_root}/configs/gamepi/99-fbdev.conf"
dest_dir="/etc/X11/xorg.conf.d"
dest="${dest_dir}/99-fbdev.conf"
wrapper="${repo_root}/configs/gamepi/Xwrapper.config"

if [ ! -f "$src" ]; then
  echo "missing ${src}" >&2
  exit 1
fi

mkdir -p "$dest_dir" /etc/X11
install -m 644 "$src" "$dest"
echo "installed ${dest}"

if [ -f "$wrapper" ]; then
  install -m 644 "$wrapper" /etc/X11/Xwrapper.config
  echo "installed /etc/X11/Xwrapper.config"
fi

if command -v dpkg-reconfigure >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive dpkg-reconfigure -f noninteractive xserver-xorg-legacy 2>/dev/null \
    || true
fi

if [ -x /usr/lib/xorg/Xorg.wrap ]; then
  ls -l /usr/lib/xorg/Xorg.wrap /usr/bin/X 2>/dev/null || true
fi
