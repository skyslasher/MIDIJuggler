#!/bin/sh
# Shell tests for GamePi blanking script (no hardware required).
set -eu

repo_root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0
fail=0

assert() {
  desc="$1"
  shift
  if "$@"; then
    pass=$((pass + 1))
    printf 'ok: %s\n' "$desc"
  else
    fail=$((fail + 1))
    printf 'FAIL: %s\n' "$desc" >&2
  fi
}

mock_bin="$tmp/bin"
mkdir -p "$mock_bin" "$tmp/home/dietpi"
xset_log="$tmp/xset.log"
: >"$xset_log"

cat >"$mock_bin/xset" <<EOF
#!/bin/sh
echo "xset \$*" >>"$xset_log"
exit 0
EOF
chmod +x "$mock_bin/xset"

cat >"$mock_bin/runuser" <<'EOF'
#!/bin/sh
shift
shift
exec "$@"
EOF
chmod +x "$mock_bin/runuser"

cat >"$mock_bin/id" <<'EOF'
#!/bin/sh
case "$1" in
  -u) echo 0 ;;
  -un) echo root ;;
  dietpi) exit 0 ;;
  *) exit 1 ;;
esac
EOF
chmod +x "$mock_bin/id"

touch "$tmp/home/dietpi/.Xauthority"
mkdir -p /tmp/.X11-unix
x_socket="/tmp/.X11-unix/X0"
if [ -e "$x_socket" ] && [ ! -S "$x_socket" ]; then
  rm -f "$x_socket"
fi
if [ ! -S "$x_socket" ]; then
  python3 - <<PY
import os
import socket

path = "/tmp/.X11-unix/X0"
if os.path.exists(path):
    os.unlink(path)
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.bind(path)
sock.close()
PY
fi

PATH="$mock_bin:$PATH" \
  GAMEPI_X_USER=dietpi \
  GAMEPI_X_HOME="$tmp/home/dietpi" \
  GAMEPI_XAUTHORITY="$tmp/home/dietpi/.Xauthority" \
  GAMEPI_X_DISPLAY=:0 \
  sh "$repo_root/scripts/gamepi-disable-blanking.sh"

assert "blanking script runs xset as kiosk user" grep -q 'xset s off' "$xset_log"
assert "blanking script forces dpms on" grep -q 'xset dpms force on' "$xset_log"

setterm_log="$tmp/setterm.log"
: >"$setterm_log"
cat >"$mock_bin/setterm" <<EOF
#!/bin/sh
echo "setterm \$*" >>"$setterm_log"
exit 0
EOF
chmod +x "$mock_bin/setterm"

PATH="$mock_bin:$PATH" \
  GAMEPI_X_USER=dietpi \
  GAMEPI_X_HOME="$tmp/home/dietpi" \
  GAMEPI_XAUTHORITY="$tmp/home/dietpi/.Xauthority" \
  GAMEPI_X_DISPLAY=:0 \
  GAMEPI_ALLOW_SETTERM=1 \
  sh "$repo_root/scripts/gamepi-disable-blanking.sh"

if grep -q setterm "$setterm_log"; then
  fail=$((fail + 1))
  printf 'FAIL: blanking script skips setterm when X is running\n' >&2
else
  pass=$((pass + 1))
  printf 'ok: blanking script skips setterm when X is running\n'
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
