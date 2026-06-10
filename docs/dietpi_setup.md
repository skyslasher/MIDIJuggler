# DietPi setup for MIDIJuggler

These notes target a Raspberry Pi Zero running DietPi with Python 3.11 or newer.
The current codebase contains protocol and GPIO stubs; install the service now
and add hardware-specific Python packages when concrete adapters are implemented.

## Base packages

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

Packages for master-clock click output through a USB sound card:

```bash
sudo apt install -y libasound2-dev alsa-utils
```

`alsa-utils` provides `aplay`, which MIDIJuggler can use as a fallback click
backend. For lower-latency persistent playback, install the Python ALSA extra
(`pyalsaaudio`). For RTP-MIDI mDNS discovery and session hosting, install the
`rtp` extra (`zeroconf`). Both are optional pip extras defined in
`pyproject.toml`.

On the Pi, install the app into the service venv with both extras (recommended
path — works from any directory):

```bash
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e "/opt/midijuggler/app[alsa,rtp]"
```

Equivalent when run from the app directory:

```bash
cd /opt/midijuggler/app
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e ".[alsa,rtp]"
```

Local development on a Mac or PC uses the same extras from the repository root:

```bash
pip install -e ".[alsa,rtp]"
```

## Install

```bash
sudo useradd --system --home /opt/midijuggler --shell /usr/sbin/nologin midijuggler
sudo mkdir -p /opt/midijuggler /etc/midijuggler
sudo chown midijuggler:midijuggler /opt/midijuggler
sudo usermod -aG gpio,audio midijuggler

sudo -u midijuggler git clone https://github.com/skyslasher/midijuggler.git /opt/midijuggler/app
sudo -u midijuggler python3 -m venv /opt/midijuggler/venv
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -U pip
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e "/opt/midijuggler/app[alsa,rtp]"
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
The systemd template also sets `SupplementaryGroups=gpio audio`. After changing
group membership or the unit file, run `sudo systemctl daemon-reload` and
restart the service so systemd picks up the new permissions.

For protected GPIO footswitch wiring with 5 V polling voltage, see
[`gpio_optocoupler_footswitch.md`](gpio_optocoupler_footswitch.md).

For MIDI master clock and click configuration, see
[`master_clock.md`](master_clock.md). Use `aplay -l` on the Pi to find the ALSA
device name for `master_clock.click_audio_device`, for example `plughw:1,0`.
If `sudo -u midijuggler aplay /etc/midijuggler/click1.wav` reports
`audio open error: Permission denied`, verify that `midijuggler` is in the
`audio` group and restart the service.

## RTP-MIDI and Avahi

DietPi often ships with **Avahi** (`avahi-daemon`) already installed. That is
compatible with MIDIJuggler at the protocol level: Avahi, Bonjour and the Python
`zeroconf` package all speak the same mDNS/DNS-SD protocol.

MIDIJuggler does **not** use Avahi's D-Bus API. RTP-MIDI discovery and local
session announcements go through the optional `rtp` extra (`zeroconf`), which
opens its own UDP sockets on port **5353**. Avahi and `zeroconf` can run on the
same Pi, but both must be allowed to share that port.

### Install zeroconf (`rtp` extra)

RTP-MIDI requires the `zeroconf` Python package. Install it through the `rtp`
pip extra into the service venv:

```bash
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e "/opt/midijuggler/app[rtp]"
```

To install ALSA click playback and RTP-MIDI together:

```bash
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e "/opt/midijuggler/app[alsa,rtp]"
```

From the app directory, the same commands use a relative path:

```bash
cd /opt/midijuggler/app
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e ".[rtp]"
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e ".[alsa,rtp]"
```

After installation, restart MIDIJuggler so discovery starts with the service:

```bash
sudo systemctl restart midijuggler.service
```

### Avahi configuration

Check `/etc/avahi/avahi-daemon.conf` and make sure Avahi does not block other
mDNS stacks:

```ini
[server]
disallow-other-stacks=no
```

The Avahi default is usually `no`, but some distributions ship `yes`. After a
change, restart Avahi:

```bash
sudo systemctl restart avahi-daemon
```

### Verify RTP-MIDI on the Pi

Confirm the Python dependency is installed in the service venv:

```bash
/opt/midijuggler/venv/bin/python -c "import zeroconf; print('zeroconf ok')"
```

Check who is using port 5353:

```bash
sudo ss -ulnp | grep 5353
```

After starting MIDIJuggler, the journal should show RTP-MIDI activity when an
adapter is enabled in host mode:

```text
started RTP-MIDI mDNS discovery
announced RTP-MIDI session MIDIJuggler as MIDIJuggler._apple-midi._udp.local. on MIDIJuggler.local. UDP 5004
discovered RTP-MIDI session MyMac at MyMac.local.:5004
```

Make sure the RTP-MIDI adapter is actually enabled in the web UI or
`config.toml`; disabled adapters are not started and do not announce sessions.

```bash
journalctl -u midijuggler.service -f
```

If discovery or hosting fails with `Address already in use`, adjust the Avahi
setting above. On some systems, port sharing only works when both processes run
as the same user; Avahi runs as `avahi` while MIDIJuggler runs as `midijuggler`.
In that case, discovery of remote sessions in the LAN still works, but hosting
a local RTP-MIDI session on the Pi may require stopping `avahi-daemon` or moving
to an Avahi-based publisher in a future release.

Configure RTP-MIDI adapters in the web UI under **MIDI Devices** or in
`config.toml`:

```toml
[adapters.rtp_midi]
enabled = true
role = "host"
session_name = "MIDIJuggler"
port = 5004
```

Use `role = "join"` and `join_target` to connect to a session discovered on the
network. See [`web_configuration.md`](web_configuration.md) for the HTTP API
details.

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
