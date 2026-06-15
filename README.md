# MIDIJuggler

MIDIJuggler is an asyncio-based Python service skeleton for Raspberry Pi Zero
and DietPi. It is intended to route and map OSC, MIDI, RTP-MIDI, GPIO and HID
footswitch or controller input through a small web interface.

This initial scaffold includes:

- `aiohttp` web server with monitor, BPM display and learn-mode controls
- web-based GPIO input and MIDI master-clock configuration
- async event bus with in-memory event history
- MIDI clock BPM tracker and MIDI master clock
- mapping engine with linear scaling and inversion
- OSC mapping libraries for Behringer X32 and Behringer Wing
- MIDI mapping libraries for Behringer X-Touch Mini and PreSonus FaderPort 8/16
- GPIO footswitch input adapter plus stubs for OSC and MIDI
- Linux HID (evdev) input adapter for gamepads and USB controllers
- RTP-MIDI mDNS session hosting and discovery via Avahi on Linux
- TOML configuration loader and example configuration
- DietPi setup notes and a systemd service template
- PC817 optocoupler circuit for protected 5 V footswitch polling
- focused tests for mapping, config loading and MIDI clock tracking

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test]"
pytest
midijuggler --config configs/example.toml
```

Optional hardware extras are installed into the **same venv**, not globally.
Examples:

```bash
python -m pip install -e ".[midi]"      # USB MIDI (mido, python-rtmidi)
python -m pip install -e ".[alsa]"      # low-latency click audio
python -m pip install -e ".[rtp]"       # zeroconf fallback for RTP-MIDI
python -m pip install -e ".[hid]"       # Linux evdev HID input
python -m pip install -e ".[midi,hid]"  # combine extras as needed
```

On a Raspberry Pi with systemd, use the service venv instead — see
[`docs/dietpi_setup.md`](docs/dietpi_setup.md) and
[`docs/hid_input.md`](docs/hid_input.md).

Open <http://127.0.0.1:8080> to view the web interface.

The hardware-facing adapters are intentionally stubs in this baseline, except
for GPIO footswitch input, Linux HID (evdev) input and RTP-MIDI mDNS
session hosting/discovery. They define the lifecycle and routing boundaries
that concrete OSC and MIDI implementations can fill in later. GPIO footswitch
input is implemented via polling configured BCM GPIO numbers. HID input reads
configured evdev codes from `/dev/input/event*` and exposes them as input data
points.

On a Raspberry Pi with `avahi-utils`, RTP-MIDI sessions are announced and
discovered through `avahi-publish-service` and `avahi-browse`. The optional
`rtp` pip extra (`zeroconf`) is only a fallback backend.

OSC, MIDI and RTP-MIDI can have multiple named instances. The adapter table
name is the routing prefix used in mappings:

```toml
[adapters.osc]
enabled = true
listen_port = 9000

[adapters.osc_pedalboard]
type = "osc"
enabled = true
listen_port = 9001

[adapters.usb_stage]
type = "midi"
enabled = true
output_port = "Stage MIDI Out"

[[mappings]]
id = "pedalboard-expression"
source = "osc_pedalboard:/pedal/expression"
target = "usb_stage:cc:1:11"
```

GPIO inputs are configured with a pin list. The number of entries controls the
number of inputs:

```toml
[adapters.gpio]
enabled = true
pins = [17, 27, 22]
active_low = true
bounce_ms = 25
poll_interval_ms = 5
```

HID inputs read Linux evdev devices. Install the optional `hid` extra into your
venv (`pip install -e ".[hid]"`), then configure by device path or USB IDs:

```toml
[adapters.gamepad]
type = "hid"
enabled = true
device = "/dev/input/event5"
codes = ["BTN_A", "BTN_B", "ABS_X", "ABS_Y"]
```

See [`docs/hid_input.md`](docs/hid_input.md) for permissions, code discovery
and explicit input tables.

Hardware notes:

- [DietPi setup](docs/dietpi_setup.md)
- [GPIO footswitch input with PC817 optocoupler](docs/gpio_optocoupler_footswitch.md)
- [HID input (Linux evdev)](docs/hid_input.md)
- [MIDI master clock](docs/master_clock.md)
- [MIDI mapping libraries](docs/midi_mapping_libraries.md)
- [OSC mapping libraries](docs/osc_mapping_libraries.md)
- [Web configuration](docs/web_configuration.md)
