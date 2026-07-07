# Rotary display controller

The Elecrow CrowPanel 1.28-inch rotary display can control the MIDIJuggler
master clock over **WiFi/OSC** or **USB serial**. Keep the UI logic on the
device and route clock commands through MIDIJuggler.

## Quick start (USB / macOS)

1. Flash firmware with `elecrow128-serial` (USB only).
2. Close PlatformIO serial monitor and any other tool using the USB port.
3. Find the port:

   ```bash
   ls /dev/cu.usbmodem*
   ```

4. Install pyserial in the same Python environment as MIDIJuggler:

   ```bash
   pip install pyserial
   # or: pip install 'midijuggler[rotary]'
   ```

5. Edit [`configs/rotary_display.toml`](../configs/rotary_display.toml) —
   set `serial_port` to your `/dev/cu.usbmodem…` device.

6. Start MIDIJuggler:

   ```bash
   midijuggler --config configs/rotary_display.toml
   ```

7. Log should show `rotary display serial connected on …` and then
   `rotary display hello on serial`. The display receives `sync …` lines and
   shows the master-clock BPM / RUN state.

## Transports

| Mode | Device connection | MIDIJuggler config |
|------|-------------------|-------------------|
| `osc` | WiFi to host running MIDIJuggler | `[rotary_display] transport = "osc"` |
| `serial` | USB-C to same host | `transport = "serial"`, set `serial_port` |
| `both` | WiFi and/or USB | `transport = "both"` |

Example config: [`configs/rotary_display.toml`](../configs/rotary_display.toml)

```toml
[rotary_display]
enabled = true
transport = "serial"
serial_port = "/dev/cu.usbmodem12201"
serial_baud = 115200
```

When `feedback_host` is empty, the device registers itself at boot via
`/midijuggler/rotary/hello` (OSC) or the `hello` serial line (USB). The device
also repeats `hello` every few seconds so MIDIJuggler can connect after boot.

## Device → MIDIJuggler commands

### OSC (UDP port 9000)

| Address | Arguments | Action |
|---------|-----------|--------|
| `/midijuggler/clock/bpm` | float | Set BPM |
| `/midijuggler/clock/click_interval` | string | Set interval (`sixteenth` … `whole`) |
| `/midijuggler/clock/start_stop` | optional | Toggle transport |
| `/midijuggler/clock/click_toggle` | optional | Toggle audio click |
| `/midijuggler/rotary/hello` | string host, int port | Register feedback target (WiFi) |

### USB serial (115200 baud, one command per line)

```
bpm 128.0
start_stop
click_toggle
interval quarter
hello
```

Comments start with `#`. Empty lines are ignored. Boot log lines from the
firmware are ignored automatically.

## MIDIJuggler → device feedback

### OSC

| Address | Arguments |
|---------|-----------|
| `/midijuggler/rotary/sync` | bpm, running, click_enabled, interval |
| `/midijuggler/rotary/beat` | 1.0 / 0.0 |

### USB serial

```
sync 120.0 1 0 quarter
beat 1.0
beat 0.0
```

The `rotary_display` module subscribes to `clock.beat`, `clock.bpm`,
`clock.running`, and `clock.click_enabled` and pushes sync/beat messages on
change.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| No serial connection | Wrong `serial_port` — use `/dev/cu.usbmodem*` on macOS, not `/dev/ttyACM0` |
| `ModuleNotFoundError: serial` | `pip install pyserial` |
| Port busy | Close PlatformIO monitor / Arduino serial tools |
| Display stuck at 120 BPM | Start MIDIJuggler **after** plugging in USB, or wait for periodic `hello` |
| ESP reboots when MIDIJuggler starts | Fixed in host: opens port with `dsrdtr=False` |

## Dependencies

USB serial mode requires `pyserial`:

```bash
pip install pyserial
```

## Related docs

- [`master_clock.md`](master_clock.md) — clock configuration and OSC addresses
- RotaryDisplay firmware: `MIDIJuggler-RotaryDisplay` project
