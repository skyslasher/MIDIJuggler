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

Install X for the kiosk (once):

```bash
sudo apt install -y \
  xserver-xorg xserver-xorg-legacy xinit xserver-xorg-video-fbdev \
  x11-xserver-utils chromium unclutter fbi fbset kbd
sudo usermod -aG video,tty,input dietpi
sudo /opt/midijuggler/app/scripts/install-gamepi13-xorg.sh
```

`xserver-xorg-legacy` + `/etc/X11/Xwrapper.config` may still be required on some setups. The
GamePi SPI kiosk uses **fbdev on `/dev/fb0` only** — `startx` passes **`-novtswitch`**
(no `vt1`) so X does not need to open `/dev/tty1` after the splash (`fbi -T 1`) releases
the framebuffer. Re-run `install-gamepi13-xorg.sh` after updating `99-fbdev.conf`.

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
sudo cp systemd/gamepi-splash.service systemd/gamepi-kiosk.service /etc/systemd/system/
sudo chmod +x scripts/gamepi-disable-blanking.sh scripts/wait-for-fb0.sh \
  scripts/wait-for-boot-settled.sh scripts/wait-for-gamepi-network.sh \
  scripts/gamepi-launch-kiosk.sh scripts/gamepi-fb-handoff.sh scripts/gamepi-fbcon.sh \
  scripts/gamepi-start-kiosk.sh configs/gamepi/kiosk.xsession
sudo systemctl daemon-reload
sudo systemctl restart gamepi-splash.service gamepi-kiosk.service
```

## 7. Splash → kiosk handoff

The splash (`fbi`, runs as **root**) stays on screen until the kiosk clears
`/run/gamepi-splash-hold`. Start **one** background `fbi` only — with `-T 1` it
daemonizes, so a tight restart loop spawns hundreds of processes and blocks X on
`/dev/fb0`.

`gamepi-fbcon.sh off` hides kernel console text on the SPI panel during splash (otherwise
`console=tty1` boot messages look like an early splash stop).

The kiosk waits for boot jobs, **Ethernet/DHCP**, and the MIDIJuggler web UI (while `fbi`
keeps showing). **`gamepi-splash-stop.sh` runs after the web wait** so the splash stays visible during
boot. Do not set `TTYPath=/dev/tty1` on the unit while `fbi -T 1` holds that VT —
systemd would hang at `Starting…` with no further logs.

`ExecStartPre` order: web wait → splash stop → `startx`.

Do **not** add `After=ifup@eth0.service` on the unit — that blocks the kiosk until
DHCP finishes while the splash script keeps running, so X never appears to start.

Override the interface name if not `eth0`:

```bash
# /etc/systemd/system/gamepi-kiosk.service.d/network.conf
[Service]
Environment=GAMEPI_NETWORK_IF=end0
```

The kiosk runs `gamepi-splash-stop.sh` as **root** (`ExecStartPre=+…`) so it can stop the
splash service and kill `fbi` without Polkit (`pkttyagent` / `Failed to execute /usr/bin/pkt…`).

`fbi` needs `-T 1` on the GamePi SPI panel (without it nothing is drawn). Before
`startx`, `gamepi-fb-handoff.sh` resets vt1 and unbinds framebuffer vtconsoles so X
can open `/dev/fb0` without conflicting with the splash.

If X dies right after the splash with `trying fbdev: /dev/fb0` and `Return to log in`:

```bash
sudo journalctl -u gamepi-kiosk.service -b --no-pager
cat /home/dietpi/.local/share/xorg/Xorg.0.log | tail -40
```

Check: `xserver-xorg-video-fbdev` installed, `/etc/X11/xorg.conf.d/99-fbdev.conf` present,
`dietpi` in groups `video tty input`, package `fbset` installed if you need `con2fbmap` for debugging.

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
