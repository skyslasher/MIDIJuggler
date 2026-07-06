# Rotary display controller

The Elecrow CrowPanel 1.28-inch rotary display can control the MIDIJuggler
master clock over **WiFi/OSC** or **USB serial**. Keep the UI logic on the
device and route clock commands through MIDIJuggler.

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
transport = "both"
feedback_host = ""
feedback_port = 9001
serial_port = "/dev/ttyACM0"
serial_baud = 115200

[adapters.osc]
enabled = true
listen_port = 9000
```

When `feedback_host` is empty, the device registers itself at boot via
`/midijuggler/rotary/hello` (OSC) or the `hello` serial line (USB).

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

Comments start with `#`. Empty lines are ignored.

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

## Dependencies

USB serial mode requires `pyserial`:

```bash
pip install pyserial
```

## Related docs

- [`master_clock.md`](master_clock.md) — clock configuration and OSC addresses
- RotaryDisplay firmware: sibling project `RotaryDisplay`
