# DietPi setup for MIDIJuggler

These notes target a Raspberry Pi Zero running DietPi with Python 3.11 or newer.
The current codebase contains protocol and GPIO stubs; install the service now
and add hardware-specific Python packages when concrete adapters are implemented.

## Base packages

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

Optional packages that are commonly useful for later adapter work:

```bash
sudo apt install -y libasound2-dev alsa-utils
```

## Install

```bash
sudo useradd --system --home /opt/midijuggler --shell /usr/sbin/nologin midijuggler
sudo mkdir -p /opt/midijuggler /etc/midijuggler
sudo chown midijuggler:midijuggler /opt/midijuggler

sudo -u midijuggler git clone https://github.com/your-org/midijuggler.git /opt/midijuggler/app
sudo -u midijuggler python3 -m venv /opt/midijuggler/venv
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -U pip
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e /opt/midijuggler/app
sudo cp /opt/midijuggler/app/configs/example.toml /etc/midijuggler/config.toml
```

Adjust `/etc/midijuggler/config.toml` for local ports, MIDI devices and GPIO
pins. On a production Pi, restrict the web host or firewall access if the device
is on an untrusted network.

## systemd

```bash
sudo cp /opt/midijuggler/app/systemd/midijuggler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now midijuggler.service
sudo systemctl status midijuggler.service
```

The web interface listens on the configured host and port, for example:

```text
http://<dietpi-hostname-or-ip>:8080
```

View logs with:

```bash
journalctl -u midijuggler.service -f
```
