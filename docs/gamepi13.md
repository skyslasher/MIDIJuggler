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
# pick the "gpio-keys" device, press buttons — you should see KEY_* events
```

Reference mapping: [`configs/gamepi/gamepi13-gpio-keys.conf`](../configs/gamepi/gamepi13-gpio-keys.conf)

| Button | Key |
|--------|-----|
| D-pad | Arrow keys |
| A / B | `A` / `B` |
| X / Y | `X` / `Y` |
| Start | `S` |
| Select | `Q` |
| L / R | Brightness Down / Up |

## 2. Enable system services

```bash
sudo cp /opt/midijuggler/app/systemd/gamepi-splash.service /etc/systemd/system/
sudo cp /opt/midijuggler/app/systemd/gamepi-kiosk.service /etc/systemd/system/
sudo cp /opt/midijuggler/app/systemd/gamepi-brightness-keys.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gamepi-splash.service gamepi-kiosk.service gamepi-brightness-keys.service
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

Hold **Start (`S`)** during early boot to show the text console instead of the splash
image.

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
sudo cp systemd/gamepi-splash.service systemd/gamepi-kiosk.service /etc/systemd/system/
sudo chmod +x scripts/gamepi-disable-blanking.sh configs/gamepi/kiosk.xsession
sudo systemctl daemon-reload
sudo systemctl restart gamepi-splash.service gamepi-kiosk.service
```
