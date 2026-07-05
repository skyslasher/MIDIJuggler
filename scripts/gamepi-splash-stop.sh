#!/bin/sh
set -eu

systemctl stop gamepi-splash.service 2>/dev/null || true
killall fbi 2>/dev/null || true
rm -f /run/gamepi-splash.pid
