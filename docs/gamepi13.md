# GamePi13 on DietPi

Map the GamePi13 buttons to **Linux keyboard events** so Chromium can handle them in
`clock-remote.html`, while separate system services can use the same keys (for
example display brightness on L/R).

## 1. Install keyboard overlays

Append `gpio-key` device-tree lines to `/boot/firmware/config.txt`:

```bash
sudo /opt/midijuggler/app/scripts/install-gamepi13-keys.sh
sudo reboot
```

With a **Geekworm/SupTronics X1207 UPS** on the same Pi, use the remapped overlay
profile (Down → GPIO 17, Left → GPIO 22) — see [§8 X1207 UPS](#8-x1207-ups-geekworm--suptronics):

```bash
sudo GAMEPI_KEYS_PROFILE=x1207 /opt/midijuggler/app/scripts/install-gamepi13-keys.sh
sudo reboot
```

Reference mapping (standard): [`configs/gamepi/gamepi13-gpio-keys.conf`](../configs/gamepi/gamepi13-gpio-keys.conf)

X1207 variant: [`configs/gamepi/gamepi13-gpio-keys-x1207.conf`](../configs/gamepi/gamepi13-gpio-keys-x1207.conf)

| Button | BCM | evdev name | Key | X1207 notes |
|--------|-----|------------|-----|-------------|
| D-pad Up | 5 | button@5 | Arrow Up | |
| D-pad Down | 6 (17) | button@6 (button@11) | Arrow Down | **17** with X1207 |
| D-pad Left | 16 (22) | button@10 (button@16) | Arrow Left | **22** with X1207 |
| D-pad Right | 13 | button@d | Arrow Right | |
| A / B | 21 / 20 | button@15 / button@14 | `A` / `B` | |
| X / Y | 15 / 12 | button@f / button@c | `X` / `Y` | |
| **Start** | **26** | **button@1a** | **`S`** | |
| Select | 19 | button@13 | `Q` | |
| L / R | 23 / 14 | button@17 / button@e | Brightness Down / Up | |

After reboot, verify the input device:

```bash
sudo evtest
# Start = button@1a (GPIO 26), KEY_S (code 31) when pressed
# Down/Left with X1207: button@11 / button@16 (GPIO 17 / 22)
# Older images may show one shared device named "gpio-keys" instead
```

## 2. Enable system services

Install X for the kiosk (once):

```bash
sudo apt install -y \
  xserver-xorg xserver-xorg-legacy xinit xserver-xorg-video-fbdev \
  x11-xserver-utils chromium unclutter fbi fbset kbd gpiod
sudo usermod -aG video,tty,input dietpi
sudo /opt/midijuggler/app/scripts/install-gamepi13-xorg.sh
```

`xserver-xorg-legacy` + [`configs/gamepi/Xwrapper.config`](../configs/gamepi/Xwrapper.config)
(`allowed_users=anybody`, `needs_root_rights=yes`) let `startx` open `/dev/tty0`.
Run `install-gamepi13-xorg.sh` after each pull that touches X config.

Kiosk startup is **two units** so the splash can keep `/dev/tty1` until the web UI is
ready:

| Unit | Role |
|------|------|
| `gamepi-kiosk-ready.service` | wait for web → stop splash (`fbi`) |
| `gamepi-kiosk.service` | `TTYPath=/dev/tty1` → `startx` |

```bash
sudo cp /opt/midijuggler/app/systemd/gamepi-splash.service /etc/systemd/system/
sudo cp /opt/midijuggler/app/systemd/gamepi-kiosk-ready.service /etc/systemd/system/
sudo cp /opt/midijuggler/app/systemd/gamepi-kiosk.service /etc/systemd/system/
sudo cp /opt/midijuggler/app/systemd/gamepi-brightness-keys.service /etc/systemd/system/
sudo cp /opt/midijuggler/app/systemd/gamepi-blanking-watch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gamepi-splash.service gamepi-kiosk-ready.service gamepi-kiosk.service gamepi-brightness-keys.service gamepi-blanking-watch.service
```

Requires `evdev` in the MIDIJuggler venv (`pip install -e ".[hid]"`).

## 3. GamePi clock UI (`clock-gamepi.html`)

The kiosk loads [`/static/clock-gamepi.html`](../src/midijuggler/web/static/clock-gamepi.html)
(240×240, same colour scheme as the main web UI). The full-size remote remains at
`/static/clock-remote.html`.

### Layout

| Area | Content |
|------|---------|
| Top | Large BPM, run/stop pill, beat pulse bar |
| Middle | Klick / Puls / click-interval toggles |
| Bottom | Brightness − / meter / + (and **X** / **Y** keys) |

### Controls

| Input | Action |
|-------|--------|
| **Y / X** | BPM ± huge step |
| **A / B** | BPM ± step |
| **D-pad ↓** (BPM zone, default) | Enter control selection |
| **D-pad ←/→** (control zone) | Move focus across Klick / Puls / Intervall / Helligkeit |
| **D-pad ↑** (control zone) | Back to BPM zone |
| **Start** | Tap tempo (BPM zone) · activate focused control (control zone) |
| **Select** | MIDI clock start/stop |
| **Start + Select** | Reboot confirm dialog (**Abbrechen** pre-selected) |
| **L / R** (shoulder) | Brightness down / up (`gamepi-brightness-keys.service`) |

Hold **Start (`S`)** during **early boot** (from power-on through the framebuffer
wait, up to ~45s) to skip splash and kiosk and land on a **text login on tty1**
instead of the splash image.

Detection uses the Start input device (`button@1a`, GPIO 26, `KEY_S`) while
`wait-for-fb0.sh` polls for `/dev/fb0`. Newer kernels expose one evdev device per
GPIO button instead of a single `gpio-keys` device. Hold Start for at least
**500ms**. You do **not** need to keep holding after the console appears — only during
the early fb wait window, before `fbi` takes over the display.

Verify on the Pi:

```bash
sudo evtest /dev/input/event2   # button@1a — Start → KEY_S (31) value 1
/opt/midijuggler/app/scripts/gamepi-is-start-pressed.sh && echo pressed || echo released
ls -l /run/gamepi-console-boot   # present after a successful console boot
systemctl show gamepi-kiosk.service -p ConditionResult,ActiveState
```

## 4. Brightness

`gamepi-brightness-keys.service` listens for Brightness Down/Up (L/R) on the
gpio-keys device and adjusts brightness through sysfs when present.

Many GamePi13 panels (`waveshare13`) expose **no** `/sys/class/backlight` entry.
MIDIJuggler then drives the panel backlight with **GPIO PWM** (default BCM **18**,
same as Waveshare’s ST7789 wiring). Install once:

```bash
sudo /opt/midijuggler/app/scripts/install-gamepi13-brightness.sh
sudo cp /opt/midijuggler/app/systemd/gamepi-brightness-keys.service /etc/systemd/system/
sudo cp /opt/midijuggler/app/systemd/midijuggler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart midijuggler.service gamepi-brightness-keys.service
```

Verify:

```bash
sudo /opt/midijuggler/app/scripts/gamepi-brightness-run.sh --status
sudo /opt/midijuggler/app/scripts/gamepi-brightness-run.sh --delta -10
curl -fsS http://127.0.0.1:8080/api/gamepi/brightness
```

Both shoulder buttons (**GPL** / **GPR**, evdev `button@17` / `button@e`) should log
brightness changes. The web UI uses the same backend — it does **not** go through
`gamepi-brightness-keys.service`.

If brightness still fails, try another GPIO (some boards use BCM 24):

```bash
sudo systemctl edit gamepi-brightness-keys.service
# add:
# [Service]
# Environment=GAMEPI_BACKLIGHT_GPIO=24
```

## 5. Splash image

Place a 240×240 PNG at `/etc/midijuggler/splash.png`.

Enable the splash service and install `fbi`:

```bash
sudo apt install -y fbi
sudo systemctl enable --now gamepi-splash.service
```

If the splash does not appear:

```bash
sudo journalctl -u gamepi-splash.service -b --no-pager
ls -l /etc/midijuggler/splash.png
systemctl is-active gamepi-splash.service
```

Common causes: missing image, `fbi` not installed, service not enabled, or **Start**
held during boot (console mode instead of splash).

If the journal shows `skipped, unmet condition check ConditionPathExists=/dev/fb0`
(on older units) or `timed out waiting for /dev/fb0`, the ST7789 framebuffer is not
ready when the splash starts. Current units poll for up to 45s via
`scripts/wait-for-fb0.sh` instead of skipping immediately.

Do **not** use `After=dev-fb0.device` on SPI panels — systemd may wait ~90s for a
device unit that never activates even though `/dev/fb0` appears later.

```bash
systemctl show gamepi-splash.service -p ConditionResult,ActiveState,Result
sudo journalctl -u gamepi-splash.service -b --no-pager
dmesg | grep -iE 'fb|st7789'
```

## 6. Screen blanking / burn-in

The GamePi13 panel is **IPS**, not OLED — permanent burn-in is **unlikely** for a
clock UI. The black screen you see is almost always **Linux console or X11 blanking**,
not hardware protection.

MIDIJuggler disables blanking via `gamepi-disable-blanking.sh` (framebuffer, console,
and X11 `xset`) at splash/kiosk start. The kernel can still re-enable blanking after a
few minutes — use the **blanking watch** service to re-apply every 30 s:

```bash
sudo cp /opt/midijuggler/app/systemd/gamepi-blanking-watch.service /etc/systemd/system/
sudo chmod +x /opt/midijuggler/app/scripts/gamepi-blanking-watch.sh
sudo systemctl daemon-reload
sudo systemctl enable --now gamepi-blanking-watch.service
```

Also set **`consoleblank=0`** in the boot cmdline (persistent kernel console blanking
off — one-time, then reboot):

```bash
sudo /opt/midijuggler/app/scripts/install-gamepi13-consoleblank.sh
sudo reboot
```

Or manually append to `/boot/firmware/cmdline.txt`:

```text
consoleblank=0
```

The kiosk uses the repo session file [`configs/gamepi/kiosk.xsession`](../configs/gamepi/kiosk.xsession).

If the screen still goes dark, check from SSH while it is black:

```bash
systemctl is-active gamepi-blanking-watch.service
cat /sys/class/graphics/fb0/blank          # should stay 0
cat /sys/module/kernel/parameters/consoleblank
sudo journalctl -u gamepi-blanking-watch.service -b --no-pager | tail -20
```

After `git pull`, redeploy services:

```bash
sudo cp systemd/gamepi-splash.service systemd/gamepi-kiosk-ready.service systemd/gamepi-kiosk.service systemd/gamepi-blanking-watch.service /etc/systemd/system/
sudo /opt/midijuggler/app/scripts/install-gamepi13-xorg.sh
sudo chmod +x scripts/gamepi-disable-blanking.sh scripts/gamepi-blanking-watch.sh \
  scripts/wait-for-fb0.sh \
  scripts/gamepi-is-start-pressed.sh scripts/gamepi-is-start-pressed.py \
  scripts/gamepi-boot-splash.sh \
  scripts/gamepi-launch-kiosk.sh scripts/gamepi-fb-handoff.sh scripts/gamepi-fbcon.sh \
  scripts/gamepi-start-kiosk.sh configs/gamepi/kiosk.xsession
sudo systemctl daemon-reload
sudo systemctl enable gamepi-kiosk-ready.service gamepi-kiosk.service
sudo systemctl restart gamepi-splash.service gamepi-kiosk-ready.service gamepi-kiosk.service
```

## 7. Splash → kiosk handoff

Boot sequence:

1. `gamepi-splash.service` — one background `fbi -T 1` until hold flag cleared
2. `gamepi-kiosk-ready.service` — web wait, then `gamepi-splash-stop.sh` (root)
3. `gamepi-kiosk.service` — `TTYPath=/dev/tty1`, then `startx` (needs `xserver-xorg-legacy`)

Do **not** combine splash wait and `TTYPath=/dev/tty1` in one unit — systemd hangs
while `fbi` holds vt1. Do **not** use a tight `fbi` restart loop (`fbi -T 1` daemonizes).

`gamepi-fbcon.sh off` hides kernel console text during splash. `gamepi-fb-handoff.sh`
runs inside splash-stop before X starts.

If X fails with `Cannot open /dev/tty0`:

```bash
sudo /opt/midijuggler/app/scripts/install-gamepi13-xorg.sh
ls -l /usr/lib/xorg/Xorg.wrap /usr/bin/X
cat /etc/X11/Xwrapper.config
groups dietpi
```

If X fails after splash:

```bash
sudo journalctl -u gamepi-kiosk-ready.service -u gamepi-kiosk.service -b --no-pager
tail -40 /home/dietpi/.local/share/xorg/Xorg.0.log
```

Verify the deployed splash script on the Pi:

```bash
grep -E 'hold_flag|fbi ' /opt/midijuggler/app/scripts/gamepi-boot-splash.sh
systemctl is-active gamepi-splash.service
sudo journalctl -u gamepi-splash.service -b --no-pager | tail -20
```

If `systemctl restart gamepi-kiosk.service` appears to hang, check whether the unit is
still in `start-pre` (`systemctl status gamepi-kiosk.service`). Each `curl` in the web
wait has a 3s timeout; stopping Chromium/X uses `TimeoutStopSec=15`. From another SSH
session: `sudo systemctl kill -s SIGKILL gamepi-kiosk.service`.

Optional: remove `console=tty1` from `/boot/firmware/cmdline.txt` so boot logs stay on
serial only (`console=ttyAMA0`).

## 8. X1207 UPS (Geekworm / SupTronics)

The [X1207 UPS HAT](https://suptronics.com/Raspberrypi/Power_mgmt/x1207-v1.2_hardware.html)
reserves Pi GPIOs that overlap the stock GamePi13 button wiring:

| BCM | Physical pin | X1207 function |
|-----|--------------|----------------|
| 2 | 3 | I2C SDA (battery gauge) |
| 3 | 5 | I2C SCL |
| **6** | **31** | **PLD — mains OK when HIGH** |
| **16** | **36** | Battery charging control (output) |

Do **not** route GamePi **Down** or **Left** to Pi pins 31 / 36 when the X1207 is
stacked on the Pi header.

### Extension cable remapping

With a GamePi13 on an extension cable, move only these two button wires on the **Pi /
HAT side** of the cable (GamePi board pads stay unchanged):

| GamePi button | Stock Pi pin (BCM) | **X1207 Pi pin (BCM)** |
|---------------|--------------------|-------------------------|
| Down | 31 (GPIO **6**) | **11 (GPIO 17)** |
| Left | 36 (GPIO **16**) | **15 (GPIO 22)** |

All other GamePi lines can remain 1:1. Leave Pi pins 31 and 36 for the X1207 only.

Verify wiring without knowing BCM numbers in advance:

```bash
sudo apt install -y gpiod
sudo gpiomon -c gpiochip0 5 6 12 13 14 15 16 17 19 20 21 22 23 26
# Pi 5: try gpiochip4 if gpiochip0 shows no events
# Press one button — the printed line number is the active BCM GPIO
```

### Keyboard overlays (X1207 profile)

Install the remapped overlay set (GPIO **17** / **22** for Down / Left):

```bash
cd /opt/midijuggler/app
sudo GAMEPI_KEYS_PROFILE=x1207 /opt/midijuggler/app/scripts/install-gamepi13-keys.sh
sudo reboot
```

If you already installed the standard overlays, edit `/boot/firmware/config.txt` and
replace the `gpio=6` / `gpio=16` lines with the contents of
[`configs/gamepi/gamepi13-gpio-keys-x1207.conf`](../configs/gamepi/gamepi13-gpio-keys-x1207.conf)
(or remove the old block and re-run the install script on a fresh image).

After reboot:

```bash
sudo evtest
# Down → button@11 (GPIO 17)
# Left → button@16 (GPIO 22, hex name — not GPIO 16!)
# Start → button@1a (GPIO 26)
```

### Clean shutdown on mains loss

When mains power drops, the X1207 keeps the Pi running on battery. To shut down cleanly
after **5 seconds** without mains (and cancel if power returns within those 5 s),
enable the PLD monitor service:

```bash
sudo apt install -y gpiod python3-libgpiod

sudo cp /opt/midijuggler/app/systemd/gamepi-x1207-poweroff.service /etc/systemd/system/
sudo chmod +x /opt/midijuggler/app/scripts/gamepi-x1207-pld.py
sudo systemctl daemon-reload
sudo systemctl enable --now gamepi-x1207-poweroff.service
```

The script [`scripts/gamepi-x1207-pld.py`](../scripts/gamepi-x1207-pld.py) reads PLD on
GPIO **6** (HIGH = mains OK), auto-detects the correct `/dev/gpiochip*` (Pi 4 vs Pi 5),
then runs `systemctl poweroff`.

Optional environment overrides in the unit file:

| Variable | Default | Meaning |
|----------|---------|---------|
| `GAMEPI_X1207_PLD_GPIO` | `6` | BCM GPIO for X1207 PLD |
| `GAMEPI_X1207_POWEROFF_DELAY` | `5` | Seconds without mains before shutdown |
| `GAMEPI_X1207_GPIOCHIP` | `auto` | Force e.g. `/dev/gpiochip0` |

Test and monitor:

```bash
sudo journalctl -u gamepi-x1207-poweroff.service -f
# Unplug mains — after 5 s the Pi should power off cleanly on battery
# Briefly unplug mains (<5 s) — journal should show "mains power restored — shutdown cancelled"
```

Read PLD state directly (HIGH / `active` = mains OK):

```bash
gpioget -c gpiochip0 6    # try gpiochip4 on Pi 5 if this fails
sudo gpiomon -c gpiochip0 6
```
