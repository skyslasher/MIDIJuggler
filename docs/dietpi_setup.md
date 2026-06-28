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
sudo apt install -y build-essential pkg-config libasound2-dev python3.13-dev alsa-utils avahi-daemon avahi-utils
```

`build-essential` provides `gcc`/`g++`, which is required to build `python-rtmidi` (MIDI)
and `pyalsaaudio` (optional click audio) when piwheels has no ready-made wheel for your
Python version. `pkg-config` and `libasound2-dev` are required so the `python-rtmidi`
build can find ALSA. `python3.13-dev` provides `Python.h` and the pkg-config entry for
your Python version (`Python dependency not found` during the `python-rtmidi` build
otherwise). If your system uses another Python 3.x release, install the matching
`python3-dev` / `python3.X-dev` package instead.

`avahi-utils` provides `avahi-publish-service` and `avahi-browse`, which MIDIJuggler
prefers on the Pi for RTP-MIDI mDNS instead of opening a second mDNS stack through
`python-zeroconf`.

`alsa-utils` provides `aplay`, which MIDIJuggler can use as a fallback click
backend. For lower-latency persistent playback, install the Python ALSA extra
(`pyalsaaudio`).

RTP-MIDI on the Pi uses `avahi-utils` by default. The Python `rtp` extra
(`zeroconf`) is optional fallback software and mainly useful for development on
macOS or PCs.

After `git pull` in `/opt/midijuggler/app`, install the app into the service venv.
USB MIDI needs only the `midi` extra; add `alsa` only when you use the low-latency
click player via `pyalsaaudio` (otherwise `aplay` is enough):

```bash
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e "/opt/midijuggler/app[midi]"
```

With click audio via `pyalsaaudio`:

```bash
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e "/opt/midijuggler/app[alsa,midi]"
```

USB MIDI adapters use `mido` with `python-rtmidi` (the `midi` extra).

HID input (gamepads, USB controllers) needs the `hid` extra (`evdev`). It is
Linux-only and reads `/dev/input/event*`. See [`hid_input.md`](hid_input.md).

Add the `rtp` extra only if you want the `python-zeroconf` fallback:

```bash
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e "/opt/midijuggler/app[alsa,midi,rtp]"
```

With HID input enabled:

```bash
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e "/opt/midijuggler/app[alsa,midi,hid]"
```

All common hardware extras together:

```bash
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e "/opt/midijuggler/app[alsa,midi,rtp,hid]"
```

Equivalent when run from the app directory:

```bash
cd /opt/midijuggler/app
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e ".[alsa,midi,rtp,hid]"
```

Local development on a Mac or PC uses the same extras from the repository root
(HID only applies on Linux; `evdev` is not available on macOS):

```bash
pip install -e ".[alsa,midi,rtp,hid]"
```

### Troubleshooting `python-rtmidi` on Python 3.13

If `pip install ...[midi]` fails with `Python dependency not found`, install the
Python headers and verify pkg-config can see them:

```bash
sudo apt install -y python3.13-dev
pkg-config --cflags python-3.13
```

The second command should print an include path containing `Python.h`.

If the sdist build from PyPI still fails, install `python-rtmidi` from the
upstream git repository (better Python 3.13 support), then install the app:

```bash
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install "git+https://github.com/SpotlightKid/python-rtmidi.git"
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install mido
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e "/opt/midijuggler/app"
sudo systemctl restart midijuggler.service
```

## Install

```bash
sudo useradd --system --home /opt/midijuggler --shell /usr/sbin/nologin midijuggler
sudo mkdir -p /opt/midijuggler /etc/midijuggler
sudo chown midijuggler:midijuggler /opt/midijuggler
sudo usermod -aG gpio,audio,input midijuggler

sudo -u midijuggler git clone https://github.com/skyslasher/midijuggler.git /opt/midijuggler/app
sudo -u midijuggler python3 -m venv /opt/midijuggler/venv
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -U pip
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e "/opt/midijuggler/app[alsa]"
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
The systemd template also sets `SupplementaryGroups=gpio audio input`. After changing
group membership or the unit file, run `sudo systemctl daemon-reload` and
restart the service so systemd picks up the new permissions.

For protected GPIO footswitch wiring with 5 V polling voltage, see
[`gpio_optocoupler_footswitch.md`](gpio_optocoupler_footswitch.md).

For Linux HID / evdev input (gamepads, USB controllers), install the `hid` pip
extra and add the service user to the `input` group. Configuration is TOML-only
for now — see [`hid_input.md`](hid_input.md).

For MIDI master clock and click configuration, see
[`master_clock.md`](master_clock.md).

If `sudo -u midijuggler aplay /etc/midijuggler/click1.wav` reports
`audio open error: Permission denied`, verify that `midijuggler` is in the
`audio` group and restart the service.

## Behringer Wing USB routing (dshare)

When a Behringer Wing is connected over USB, route three stereo outputs to Wing
USB inputs 1–6 so multiple processes (including MIDIJuggler) can play at the
same time without exclusive hardware access.

The repo ships ALSA PCMs in
[`configs/alsa/50-wing-usb-routing.conf`](../configs/alsa/50-wing-usb-routing.conf).
Deploy them system-wide — **not** into `/etc/midijuggler/asoundrc`, because
MIDIJuggler overwrites that file when the master-clock audio device changes.

```bash
sudo cp /opt/midijuggler/app/configs/alsa/50-wing-usb-routing.conf /etc/alsa/conf.d/
sudo cp /opt/midijuggler/app/systemd/wing-gadget-loop.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wing-gadget-loop.service
```

Verify card names first (`aplay -l` should show `CARD=WING`; `arecord -l` should
show the USB gadget capture card, often `CARD=UAC2Gadget` on a Pi). Edit the
conf or service file if your system uses different names.

The conf reserves the first six Wing USB channels via three `dshare` PCMs that
share one `ipc_key` (single Wing hw open) but bind each stereo client to a
different channel pair. Multichannel `dmix` on the Wing fails with
`Slave PCM not usable`. Do **not** use `route` above `dshare` (first client
claims all six bindings) or `share` above `dshare` (also fails hw refine here).

Keep `ipc_key_add_uid false` and `ipc_perm 0666` so **all Unix users** (shell,
`midijuggler`, `shairport-sync`, systemd services) share one dshare pool. With
`ipc_key_add_uid true`, each user opens the Wing hardware separately and blocks
everyone else.

`dshare` opens the Wing once. `wing_stereo1`, `wing_stereo2` and `wing_stereo3`
work **in parallel** on USB 1–2, 3–4 and 5–6, but each PCM accepts only
**one client at a time**. MIDIJuggler keeps `wing_stereo1` open while click
audio is enabled; Shairport on `wing_stereo2` and `alsaloop` on `wing_stereo3`
can still run at the same time on the other pairs.

Replace `card WING` with `card N` (from `aplay -l`) if the symbolic name does
not resolve on your system.

After deployment:

```bash
aplay -L | grep wing_stereo
speaker-test -D wing_stereo1 -c 2   # terminal 1
speaker-test -D wing_stereo2 -c 2   # terminal 2 — parallel
```

| PCM | Wing USB | Typical use |
|-----|----------|-------------|
| `wing_stereo1` | 1–2 | MIDIJuggler master-clock clicks |
| `wing_stereo2` | 3–4 | Shairport-Sync (`output_device = "wing_stereo2"`) |
| `wing_stereo3` | 5–6 | USB gadget loop via `wing-gadget-loop.service` |

Only the shared `dshare` pool opens the Wing hardware. All clients — including
MIDIJuggler and Shairport-Sync — must use the software PCMs above. Do **not**
use `default`, `plughw:CARD=WING,DEV=0`, or any direct `hw:` device string.

```toml
[master_clock]
click_audio_device = "wing_stereo1"
```

Enter the PCM name manually in the web UI if it is not listed in the dropdown
(`aplay -L` shows the names after installing the conf.d file).

The `wing-gadget-loop` service runs
[`scripts/wing-gadget-loop.sh`](../scripts/wing-gadget-loop.sh) as root so it can
open the USB gadget capture device (often unavailable to the `midijuggler`
user). Playback still goes through `wing_stereo3` and shares the Wing dshare
pool (`ipc_perm 0666`). The script auto-detects the gadget capture card
(`UAC2Gadget`, `UAC2_Gadget`, or `g_audio`), waits up to 90 seconds, and sends
playback to `wing_dshare_56` (not `wing_stereo3`) because `aplay
--dump-hw-params` on the plug wrapper can hang even when `speaker-test -D
wing_stereo3` works.

If the loop fails, check the log:

```bash
sudo journalctl -u wing-gadget-loop.service -n 30 --no-pager
arecord -l
```

Override the capture device explicitly if auto-detection picks the wrong card:

```bash
sudo systemctl edit wing-gadget-loop.service
```

```ini
[Service]
Environment=G_AUDIO_CAPTURE=plughw:CARD=UAC2Gadget,DEV=0
Environment=WING_PLAYBACK=wing_dshare_56
```

After updating from git:

```bash
sudo cp /opt/midijuggler/app/systemd/wing-gadget-loop.service /etc/systemd/system/
sudo chmod +x /opt/midijuggler/app/scripts/wing-gadget-loop.sh
sudo systemctl daemon-reload
sudo systemctl restart wing-gadget-loop.service
```

## RTP-MIDI and Avahi

DietPi often ships with **Avahi** (`avahi-daemon`) already installed. That is
compatible with MIDIJuggler at the protocol level: Avahi, Bonjour and the Python
`zeroconf` package all speak the same mDNS/DNS-SD protocol.

On the Pi, MIDIJuggler prefers the Avahi CLI tools (`avahi-publish-service`,
`avahi-browse`) when `avahi-utils` is installed. That avoids port-5353 conflicts
with `avahi-daemon`. The Python `zeroconf` package is only used as a fallback.

### Install RTP-MIDI dependencies

Install Avahi on DietPi first:

```bash
sudo apt install -y avahi-daemon avahi-utils
sudo systemctl enable --now avahi-daemon
```

The Python `zeroconf` package is optional fallback software. Install it through
the `rtp` pip extra into the service venv if needed:

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

Confirm Avahi is running and the CLI tools are installed:

```bash
systemctl status avahi-daemon
which avahi-publish-service avahi-browse
```

Test manual announcement and discovery:

```bash
avahi-publish-service "MIDIJuggler-Test" _apple-midi._udp 5004
avahi-browse -rpt _apple-midi._udp
```

After starting MIDIJuggler, the journal should show RTP-MIDI activity when an
adapter is enabled in host mode:

```text
RTP-MIDI mDNS backend: avahi (/usr/bin/avahi-publish-service, /usr/bin/avahi-browse)
started RTP-MIDI discovery via /usr/bin/avahi-browse
RTP-MIDI status: {'backend': 'avahi', 'avahi_tools': True, ...}
announced RTP-MIDI session MIDIJuggler via /usr/bin/avahi-publish-service on UDP 5004
discovered RTP-MIDI session MyMac at MyMac.local.:5004
```

Make sure the RTP-MIDI adapter is actually enabled in the web UI or
`config.toml`; disabled adapters are not started and do not announce sessions.

```bash
journalctl -u midijuggler.service -f
```

If the journal reports `backend: none`, install `avahi-utils`, restart
`avahi-daemon`, update the systemd unit from the repository and restart
MIDIJuggler.

Optional fallback only:

```bash
/opt/midijuggler/venv/bin/python -c "import zeroconf; print('zeroconf ok')"
```

### Host and join sessions

Configure RTP-MIDI adapters in the web UI under **MIDI Devices** or in
`config.toml`. A common setup uses one host instance and one join instance:

```toml
[adapters.rtp_midi]
enabled = true
role = "host"
session_name = "MIDIJuggler"
port = 5004

[adapters.rtp_remote]
type = "rtp_midi"
enabled = true
role = "join"
join_target = "MacBook.local.:5004:Studio"
port = 5005
```

In the web UI, switch the join instance to **Join discovered session**, click
**Refresh RTP sessions**, then choose the remote Mac or iPad session. Locally
hosted sessions are hidden from the join dropdown.

See [`web_configuration.md`](web_configuration.md) for the HTTP API details.

## systemd

```bash
sudo cp /opt/midijuggler/app/systemd/midijuggler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now midijuggler.service
sudo systemctl status midijuggler.service
```

The unit must **not** set `NoNewPrivileges=true`; that blocks the passwordless
`sudo` helpers used for hostname changes and service restart from the web UI.
After updating the unit file, run `daemon-reload` and restart the service.

The web interface listens on the configured host and port, for example:

```text
http://<dietpi-hostname-or-ip>:8080
```

View logs with:

```bash
journalctl -u midijuggler.service -f
```

### Stage system controls (hostname and restart)

The web configuration page exposes **Stage system** controls for headless boxes on
stage:

- **Hostname** — shown in the header as `MIDIJuggler - <hostname>` and applied with
  `hostnamectl`. The helper script also updates `127.0.1.1` in `/etc/hosts` and
  restarts `avahi-daemon` so the new name is announced on mDNS immediately.
  Hosted RTP-MIDI sessions are re-announced by MIDIJuggler after the change.
- **Restart MIDIJuggler service** — restarts the systemd unit without power cycling
  the Pi when something is stuck.

These actions run helper scripts as root through passwordless `sudo`. Install the
sudoers snippet and make the scripts executable after `git pull`:

```bash
sudo chmod +x /opt/midijuggler/app/scripts/set-hostname.sh
sudo chmod +x /opt/midijuggler/app/scripts/restart-midijuggler.sh
sudo cp /opt/midijuggler/app/systemd/midijuggler-sudoers.example /etc/sudoers.d/midijuggler
sudo chmod 0440 /etc/sudoers.d/midijuggler
sudo visudo -c
```

Without the sudoers file the configuration page shows a hint explaining what is
missing; hostname and restart still work from the shell as root.

Verify from the Pi as the service user:

```bash
sudo -u midijuggler sudo -n -l
sudo -u midijuggler sudo -n /opt/midijuggler/app/scripts/restart-midijuggler.sh
```

The first command should list both helper scripts. The second restarts
MIDIJuggler immediately (only use for testing).
