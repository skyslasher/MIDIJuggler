# MIDIJuggler

MIDIJuggler is an asyncio-based Python service skeleton for Raspberry Pi Zero
and DietPi. It is intended to route and map OSC, USB MIDI, RTP-MIDI and GPIO
footswitch input through a small web interface.

This initial scaffold includes:

- `aiohttp` web server with monitor, BPM display and learn-mode controls
- async event bus with in-memory event history
- MIDI clock BPM tracker
- mapping engine with linear scaling and inversion
- adapter stubs for OSC, USB MIDI, RTP-MIDI and GPIO
- TOML configuration loader and example configuration
- DietPi setup notes and a systemd service template
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

The hardware-facing adapters are intentionally stubs in this baseline. They
define the lifecycle and routing boundaries that concrete OSC, MIDI, RTP-MIDI
and GPIO implementations can fill in later.
