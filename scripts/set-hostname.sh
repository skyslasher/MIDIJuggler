#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: set-hostname.sh <hostname>" >&2
  exit 2
fi

HOSTNAME="$1"
hostnamectl set-hostname "$HOSTNAME"
if grep -q '^127.0.1.1' /etc/hosts; then
  sed -i "s/^127.0.1.1.*/127.0.1.1\t${HOSTNAME}/" /etc/hosts
else
  printf '127.0.1.1\t%s\n' "$HOSTNAME" >> /etc/hosts
fi
systemctl restart avahi-daemon
