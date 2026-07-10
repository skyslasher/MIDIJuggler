# GamePi — Deploy nach git pull

Kurzanleitung für **dietpi@LunaticMaster** und jedes GamePi13 mit MIDIJuggler unter
`/opt/midijuggler/app`.

> **Warum ändert sich nach `git pull` nichts?**  
> Ein einfaches `git pull` reicht nicht: der venv muss neu installiert werden
> (`pip install -e`), systemd-Units und Skripte müssen deployed werden, und
> `midijuggler.service` sowie ggf. der Kiosk müssen neu starten. Dafür gibt es
> ein Skript.

## Voraussetzungen

| Was | Pfad / Paket |
|-----|----------------|
| App-Checkout | `/opt/midijuggler/app` |
| Python-venv | `/opt/midijuggler/venv` |
| Konfiguration | `/etc/midijuggler/config.toml` |
| Service-User | `midijuggler` |
| Kiosk-User | `dietpi` (Gruppe `video,tty,input`) |

Einmalig (neues Image): siehe [`gamepi13.md`](gamepi13.md) — GPIO-Keys, Xorg,
Helligkeit, `consoleblank=0`.

Systempakete (falls noch nicht installiert):

```bash
sudo apt update
sudo apt install -y git python3 python3-venv build-essential pkg-config \
  libasound2-dev alsa-utils avahi-daemon avahi-utils \
  xserver-xorg xserver-xorg-legacy xinit xserver-xorg-video-fbdev \
  x11-xserver-utils chromium unclutter fbi fbset kbd gpiod curl
```

## Deploy in einem Schritt (empfohlen)

Auf dem Pi, **nach** `git pull` im Repo (oder das Skript holt selbst Updates):

```bash
cd /opt/midijuggler/app
sudo git pull                    # optional — deploy-gamepi.sh macht pull-midijuggler-app.sh
sudo ./scripts/deploy-gamepi.sh
```

Das Skript ist **idempotent** — bei Problemen einfach erneut ausführen.

### Was das Skript macht

| Schritt | Aktion |
|---------|--------|
| 1 | Pfade `/opt/midijuggler/app` und venv prüfen |
| 2 | `pull-midijuggler-app.sh` — setzt `scripts/` und `configs/gamepi/` auf `origin/main` |
| 3 | `pip install -e ".[alsa,midi,hid,rotary]"` im Service-venv |
| 4 | `midijuggler.service` nach `/etc/systemd/system/` |
| 5 | sudoers (`midijuggler-sudoers.example`) |
| 6 | optional `install-gamepi13-brightness.sh` mit `GAMEPI_SETUP_BRIGHTNESS=1` |
| 7 | `install-gamepi13-services.sh` — Units, Skripte, Xorg (`99-fbdev.conf`, `Xwrapper.config`) |
| 8 | avahi-daemon prüfen (Encoder-mDNS) |
| 9 | alle GamePi-Units enablen |
| 10 | `midijuggler` + GamePi-Dienste neu starten, Kiosk-Recovery |
| 11 | `gamepi-display-health.sh` + Kiosk-Diagnose |
| 12 | Checkliste mit erwarteten Werten |

### Umgebungsvariablen

```bash
# Git-Update überspringen (Code schon aktuell):
sudo MIDIJUGGLER_SKIP_GIT_PULL=1 ./scripts/deploy-gamepi.sh

# Kiosk nicht neu starten (nur Backend):
sudo GAMEPI_RESTART_KIOSK=0 ./scripts/deploy-gamepi.sh

# Helligkeit-Einmalsetup mit apt:
sudo GAMEPI_SETUP_BRIGHTNESS=1 ./scripts/deploy-gamepi.sh

# Andere pip-Extras:
sudo GAMEPI_PIP_EXTRAS=alsa,midi,hid,rotary,rtp ./scripts/deploy-gamepi.sh
```

## Manueller Deploy (Referenz)

Falls das Skript nicht verfügbar ist:

```bash
sudo /opt/midijuggler/app/scripts/pull-midijuggler-app.sh
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e \
  "/opt/midijuggler/app[alsa,midi,hid,rotary]"
sudo cp /opt/midijuggler/app/systemd/midijuggler.service /etc/systemd/system/
sudo cp /opt/midijuggler/app/systemd/midijuggler-sudoers.example /etc/sudoers.d/midijuggler
sudo chmod 0440 /etc/sudoers.d/midijuggler
sudo /opt/midijuggler/app/scripts/install-gamepi13-services.sh
sudo systemctl daemon-reload
sudo systemctl enable midijuggler.service gamepi-splash.service \
  gamepi-kiosk-ready.service gamepi-kiosk.service \
  gamepi-blanking-watch.service gamepi-brightness-keys.service
sudo systemctl restart midijuggler.service
sudo /opt/midijuggler/app/scripts/wait-for-midijuggler-web.sh
sudo systemctl restart gamepi-kiosk.service
sudo /opt/midijuggler/app/scripts/gamepi-recover-display.sh
```

## Verifikation

```bash
# Commit aktuell?
git -C /opt/midijuggler/app rev-parse --short HEAD

# Service läuft?
systemctl is-active midijuggler.service
# → active

# Web-UI?
curl -fsS http://127.0.0.1:8080/static/clock-gamepi.html -o /dev/null && echo ok
# → ok

# Display gesund?
/opt/midijuggler/app/scripts/gamepi-display-health.sh && echo display ok
# → display ok

# Framebuffer nicht blanked?
cat /sys/class/graphics/fb0/blank
# → 0

# Kiosk aktiv?
systemctl is-active gamepi-kiosk.service
# → active

# X + Chromium?
ls -l /tmp/.X11-unix/X0
pgrep -x chromium && echo chromium ok
```

Logs:

```bash
journalctl -u midijuggler.service -n 40 --no-pager
journalctl -u gamepi-kiosk.service -u gamepi-kiosk-ready.service -b --no-pager
tail -30 /home/dietpi/.local/share/xorg/Xorg.0.log
```

## Encoder / Rotary Display (OSC)

Nach **jedem** Deploy, der den Encoder betrifft:

1. `pip install -e ".[rotary]"` (im Deploy-Skript enthalten)
2. `sudo systemctl restart midijuggler.service`
3. Encoder neu starten oder warten auf periodisches `hello`

### mDNS / Zeroconf

Der Encoder meldet sich per OSC `/midijuggler/rotary/hello` mit Hostname
z. B. `rotary-a1b2c3.local`. MIDIJuggler löst `.local` auf via:

- **python-zeroconf** (`pip install midijuggler[rotary]`) — bevorzugt
- **avahi-resolve-host-name** (`avahi-utils`) — Fallback

Prüfen:

```bash
sudo systemctl is-active avahi-daemon
/opt/midijuggler/venv/bin/python -c "import zeroconf; print('zeroconf ok')"
avahi-resolve-host-name -4 rotary-DEINNAME.local
```

In `/etc/midijuggler/config.toml`:

```toml
[rotary_display]
enabled = true
transport = "osc"   # oder "both" / "serial"
```

### USB-Serial-Fallback

Bei `transport = "both"` oder `"serial"`: USB-Port in Config setzen, pyserial
installiert (`[rotary]` extra). Nach Transport-Wechsel im Web-UI sendet
MIDIJuggler `hello` über Serial, um den Encoder zu synchronisieren (Commit 37e6b74).

```bash
ls /dev/ttyACM* /dev/serial/by-id/* 2>/dev/null
journalctl -u midijuggler.service -f | grep -i rotary
# Erwartet: "rotary display serial connected" oder OSC hello/sync
```

Ohne mDNS: feste IP in Config oder Serial-only.

## Fehlerbehebung

### Schwarzer Bildschirm nach X-Start

Ursache oft: veraltete Units, fehlendes Xorg-Setup, oder Console/X blanking.

```bash
sudo /opt/midijuggler/app/scripts/deploy-gamepi.sh
# oder nur Recovery:
sudo /opt/midijuggler/app/scripts/gamepi-recover-display.sh
sudo reboot
```

Einzelchecks:

```bash
sudo /opt/midijuggler/app/scripts/install-gamepi13-xorg.sh
cat /etc/X11/Xwrapper.config
systemctl status gamepi-kiosk.service
cat /sys/class/graphics/fb0/blank   # muss 0 sein
```

Persistentes Console-Blanking (einmalig + Reboot):

```bash
sudo /opt/midijuggler/app/scripts/install-gamepi13-consoleblank.sh
sudo reboot
```

### Tote Tasten (D-Pad, Start, L/R)

Overlays und UART — siehe [`gamepi13.md`](gamepi13.md) §1 und §4:

```bash
sudo /opt/midijuggler/app/scripts/gamepi-verify-keys.sh
sudo evtest
```

### Encoder synchronisiert nicht

```bash
sudo /opt/midijuggler/app/scripts/deploy-gamepi.sh
# oder minimal:
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e \
  "/opt/midijuggler/app[rotary]"
sudo systemctl restart midijuggler.service
```

Encoder-Strom aus/ein, dann Logs prüfen.

### Deploy-Skript schlägt fehl

```bash
# Rechte:
ls -l /opt/midijuggler/app/scripts/deploy-gamepi.sh
sudo chmod +x /opt/midijuggler/app/scripts/deploy-gamepi.sh

# venv fehlt:
sudo -u midijuggler python3 -m venv /opt/midijuggler/venv
```

## Unterschied zu gamepi-reload-after-pull.sh

| Skript | Wann |
|--------|------|
| `deploy-gamepi.sh` | **Vollständiges** Deploy nach Pull (pip, Units, Xorg, sudoers, Kiosk) |
| `gamepi-reload-after-pull.sh` | Leichtes Reload: Pull + midijuggler restart, Kiosk optional |

Für „keine Änderung nach Deploy“ immer **`deploy-gamepi.sh`** verwenden.

## Siehe auch

- [`gamepi13.md`](gamepi13.md) — Hardware, Tasten, Helligkeit, Splash
- [`dietpi_setup.md`](dietpi_setup.md) — Pi-Grundinstallation, pip-Extras
- [`rotary_display.md`](rotary_display.md) — Encoder-Protokoll
