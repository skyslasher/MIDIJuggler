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

`alsa-utils` provides `aplay`, which MIDIJuggler can use for the optional
master-clock click output through a USB sound card.

## Install

```bash
sudo useradd --system --home /opt/midijuggler --shell /usr/sbin/nologin midijuggler
sudo mkdir -p /opt/midijuggler /etc/midijuggler
sudo chown midijuggler:midijuggler /opt/midijuggler
sudo usermod -aG gpio midijuggler

sudo -u midijuggler git clone https://github.com/skyslasher/midijuggler.git /opt/midijuggler/app
sudo -u midijuggler python3 -m venv /opt/midijuggler/venv
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -U pip
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e /opt/midijuggler/app
sudo cp /opt/midijuggler/app/configs/example.toml /etc/midijuggler/config.toml
sudo chown -R midijuggler:midijuggler /etc/midijuggler
```

Adjust `/etc/midijuggler/config.toml` for local ports, MIDI devices and GPIO
pins. On a production Pi, restrict the web host or firewall access if the device
is on an untrusted network.

The service user must own `/etc/midijuggler` if configuration changes should be
persisted from the web interface. If not, runtime changes still apply but are
lost on restart.

GPIO inputs use BCM numbering. The number of configured inputs is the number of
entries in `pins`:

```toml
[adapters.gpio]
enabled = true
pins = [17, 27, 22]
active_low = true
bounce_ms = 25
poll_interval_ms = 5
```

MIDIJuggler accepts BCM numbers here. On newer Raspberry Pi kernels, the
deprecated sysfs GPIO interface may internally use global GPIO numbers with a
`gpiochip` base offset; MIDIJuggler resolves that offset at startup.
The systemd template also sets `SupplementaryGroups=gpio`. After changing group
membership or the unit file, run `sudo systemctl daemon-reload` and restart the
service so systemd picks up the new permissions.

For protected GPIO footswitch wiring with 5 V polling voltage, see
[`gpio_optocoupler_footswitch.md`](gpio_optocoupler_footswitch.md).

For MIDI master clock and click configuration, see
[`master_clock.md`](master_clock.md). Use `aplay -l` on the Pi to find the ALSA
device name for `master_clock.click_audio_device`, for example `plughw:1,0`.

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
