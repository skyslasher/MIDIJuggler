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

After reboot, verify the input device:

```bash
sudo evtest
# Start = /dev/input/event2 → button@1a (GPIO 26), KEY_S (code 31) when pressed
# Older images may show one shared device named "gpio-keys" instead
```

Reference mapping: [`configs/gamepi/gamepi13-gpio-keys.conf`](../configs/gamepi/gamepi13-gpio-keys.conf)

| Button | BCM | evdev name | Key |
|--------|-----|------------|-----|
| D-pad Up/Down/Left/Right | 5/6/16/13 | button@5 … button@d | Arrow keys |
| A / B | 21 / 20 | button@15 / button@14 | `A` / `B` |
| X / Y | 15 / 12 | button@f / button@c | `X` / `Y` |
| **Start** | **26** | **button@1a** | **`S`** |
| Select | 19 | button@13 | `Q` |
| L / R | 23 / 14 | button@17 / button@e | Brightness Down / Up |

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
sudo systemctl daemon-reload
sudo systemctl enable --now gamepi-splash.service gamepi-kiosk-ready.service gamepi-kiosk.service gamepi-brightness-keys.service
```

Requires `evdev` in the MIDIJuggler venv (`pip install -e ".[hid]"`).

## 3. Clock remote keyboard shortcuts

The kiosk loads `/static/clock-remote.html`. With keyboard mapping enabled:

| Key | Action |
|-----|--------|
| Arrow Up/Down | BPM ± step |
| Arrow Left/Right | BPM ± huge step |
| `S` / Enter | Start/Stop transport |
| `B` / Esc | Toggle click |
| `X` | Tap tempo |
| `Y` | Next click interval |
| `Q` | Toggle beat flash |
| L / R | Hardware brightness (system service) |

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
gpio-keys device and writes `/sys/class/backlight/*/brightness` when present.

If the ST7789 panel exposes no backlight sysfs entry, the service logs a warning and
keeps running; adjust `GAMEPI_BRIGHTNESS_STEP` or add a PWM GPIO later if needed.

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
and X11 `xset`). The kiosk uses the repo session file
[`configs/gamepi/kiosk.xsession`](../configs/gamepi/kiosk.xsession).

Optional extra safety in `/boot/firmware/cmdline.txt`:

```text
consoleblank=0
```

After `git pull`, redeploy services:

```bash
sudo cp systemd/gamepi-splash.service systemd/gamepi-kiosk-ready.service systemd/gamepi-kiosk.service /etc/systemd/system/
sudo /opt/midijuggler/app/scripts/install-gamepi13-xorg.sh
sudo chmod +x scripts/gamepi-disable-blanking.sh scripts/wait-for-fb0.sh \
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
