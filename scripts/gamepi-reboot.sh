#!/bin/sh
# Reboot the Pi (invoked via sudo from the midijuggler web API).
set -eu
exec /usr/bin/systemctl reboot
