# MIDIJuggler

MIDIJuggler is an asyncio-based Python service skeleton for Raspberry Pi Zero
and DietPi. It is intended to route and map OSC, USB MIDI, RTP-MIDI and GPIO
footswitch input through a small web interface.

This initial scaffold includes:

- `aiohttp` web server with monitor, BPM display and learn-mode controls
- web-based GPIO input and MIDI master-clock configuration
- async event bus with in-memory event history
- MIDI clock BPM tracker and MIDI master clock
- mapping engine with linear scaling and inversion
- OSC mapping libraries for Behringer X32 and Behringer Wing
- MIDI mapping libraries for Behringer X-Touch Mini and PreSonus FaderPort 8/16
- GPIO footswitch input adapter plus stubs for OSC and USB MIDI
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

Open <http://127.0.0.1:8080> to view the web interface.

The hardware-facing adapters are intentionally stubs in this baseline, except
for GPIO footswitch input and RTP-MIDI mDNS session hosting/discovery. They
define the lifecycle and routing boundaries that concrete OSC and USB MIDI
implementations can fill in later. GPIO footswitch input is implemented via
polling configured BCM GPIO numbers.

On a Raspberry Pi with `avahi-utils`, RTP-MIDI sessions are announced and
discovered through `avahi-publish-service` and `avahi-browse`. The optional
`rtp` pip extra (`zeroconf`) is only a fallback backend.

OSC, USB MIDI and RTP-MIDI can have multiple named instances. The adapter table
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
type = "usb_midi"
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

Hardware notes:

- [DietPi setup](docs/dietpi_setup.md)
- [GPIO footswitch input with PC817 optocoupler](docs/gpio_optocoupler_footswitch.md)
- [MIDI master clock](docs/master_clock.md)
- [MIDI mapping libraries](docs/midi_mapping_libraries.md)
- [OSC mapping libraries](docs/osc_mapping_libraries.md)
- [Web configuration](docs/web_configuration.md)
