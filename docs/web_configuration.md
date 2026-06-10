# Web configuration

MIDIJuggler exposes configuration endpoints in the web interface for GPIO
inputs, MIDI devices and the MIDI master clock.

## GPIO inputs

Open the web interface and use **GPIO Inputs** to select active Raspberry Pi BCM
GPIO pins. The UI shows the common 40-pin Raspberry Pi header GPIOs:

```text
GPIO 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13,
GPIO 14, 15, 16, 17, 18, 19, 20, 21, 22, 23,
GPIO 24, 25, 26, 27
```

The form also exposes:

- `active_low`
- `bounce_ms`
- `poll_interval_ms`

Saving updates the running GPIO adapter and persists the `[adapters.gpio]`
section in the active TOML configuration file.

For persistence, the service user needs write access to the configuration
directory, because MIDIJuggler writes a temporary file next to the active config
before replacing it:

```bash
sudo chown -R midijuggler:midijuggler /etc/midijuggler
sudo systemctl restart midijuggler.service
```

If the service cannot write the config file, the GPIO change is still applied at
runtime and the web UI reports that it was not persisted.

The HTTP API is:

```text
GET /api/gpio
POST /api/gpio
```

Example POST body:

```json
{
  "pins": [17, 22, 27],
  "active_low": true,
  "bounce_ms": 25,
  "poll_interval_ms": 5
}
```

At least one GPIO pin must be enabled. Pin numbers are BCM numbers, matching the
hardware and DietPi documentation.

## MIDI devices

The **MIDI Devices** card exposes all configured `usb_midi` and `rtp_midi`
adapter instances. For each instance you can edit:

- enabled flag
- USB MIDI `input_port` and `output_port`
- optional `midi_library`
- RTP-MIDI mode: `host` (announce a local session via mDNS) or `join` (connect
  to a discovered session)
- RTP-MIDI `session_name` and UDP `port` in host mode
- RTP-MIDI `join_target` in join mode, chosen from sessions discovered via mDNS

RTP-MIDI discovery uses the `_apple-midi._udp` mDNS service type. Install the
optional `zeroconf` dependency (`pip install midijuggler[rtp]`) to enable
network discovery and local session announcements.

Available ALSA sequencer ports are discovered with `aconnect -l`. Saving
updates the in-memory adapter configuration and persists the corresponding
`[adapters.<name>]` sections in the active TOML configuration file.

The HTTP API is:

```text
GET /api/midi-adapters
POST /api/midi-adapters
```

Example POST body:

```json
{
  "instances": [
    {
      "name": "usb_midi",
      "enabled": true,
      "input_port": "MIDIJuggler In",
      "output_port": "MIDIJuggler Out",
      "midi_library": ""
    },
    {
      "name": "rtp_midi",
      "enabled": true,
      "role": "host",
      "session_name": "MIDIJuggler",
      "port": 5004
    }
  ]
}
```

As with GPIO and master clock, runtime changes are applied immediately. A full
restart is still recommended after changing enabled MIDI adapters so the service
can rebuild the active adapter set.

## MIDI master clock

The **Master Clock** card exposes the editable MIDI master-clock settings:

- enabled / auto-start / send-transport flags
- BPM, BPM minimum and BPM maximum
- MIDI clock output targets
- OSC addresses for BPM and click-interval remote control
- MIDI CC numbers for BPM MSB, BPM LSB and click interval
- MIDI channel for remote control
- audio click enablement, WAV path, interval and ALSA device
- audio click enablement, WAV path, interval and ALSA device

Saving updates the running master clock immediately and persists the
`[master_clock]` section in the active TOML configuration file.

The HTTP API is:

```text
GET /api/master-clock
POST /api/master-clock
```

Example POST body:

```json
{
  "enabled": true,
  "bpm": 120.0,
  "bpm_min": 40.0,
  "bpm_max": 240.0,
  "auto_start": false,
  "output_targets": ["usb_midi", "rtp_midi"],
  "midi_input_targets": ["usb_midi"],
  "osc_input_targets": ["osc"],
  "send_transport": true,
  "bpm_osc_address": "/midijuggler/clock/bpm",
  "click_interval_osc_address": "/midijuggler/clock/click_interval",
  "bpm_msb_cc": 20,
  "bpm_lsb_cc": 21,
  "click_interval_cc": 22,
  "midi_channel": 1,
  "click_enabled": false,
  "click_wav": "/etc/midijuggler/click.wav",
  "click_interval": "quarter",
  "click_audio_device": "plughw:1,0"
}
```

As with GPIO, if the service cannot write the config file, the master-clock
change is still applied at runtime and the web UI reports that it was not
persisted.

Click playback prefers `pyalsaaudio` when installed and falls back to `aplay`.
The web UI lists available ALSA devices discovered through `aplay -l`, and WAV
files found in
`/etc/midijuggler/*.wav`.
The selected ALSA device is used as the slave for a generated dmix PCM named
`master_clock` when it is a hardware PCM. If the selected target is already a
software PCM, `master_clock` is generated as a plug alias instead. The click
player always uses the generated `master_clock` PCM.

## Configuration import/export

The **Configuration import/export** card can export the active TOML file and
import another TOML configuration. Imports are validated before writing the file.
After importing, restart the service to apply all settings:

```bash
sudo systemctl restart midijuggler.service
```
