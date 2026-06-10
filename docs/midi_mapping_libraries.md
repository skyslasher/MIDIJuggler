# MIDI mapping libraries

MIDIJuggler ships MIDI mapping libraries for controller surfaces. The libraries
are catalogs of logical control IDs and MIDI messages that concrete USB-MIDI
adapter implementations can use for learn mode, routing and feedback.

Available libraries:

- `presonus_faderport`

The web API exposes the packaged libraries:

```text
GET /api/midi-libraries
GET /api/midi-libraries/presonus_faderport
```

## PreSonus FaderPort 8/16

The FaderPort library targets the multichannel FaderPort 8 and FaderPort 16 in
MCU-style operation:

- FaderPort 8 uses channels 1-8 on `port_1`
- FaderPort 16 uses channels 1-8 on `port_1` and channels 9-16 on `port_2`
- Fader movements are represented as pitch-bend controls
- Pan/V-Pot encoders are represented as relative control-change controls
- Record-arm, solo, mute and select buttons are represented as note controls
- LCD track names are represented as PreSonus SysEx text targets

Common logical IDs:

```text
ch_1_fader
ch_1_pan_encoder
ch_1_record_arm
ch_1_solo
ch_1_mute
ch_1_select
ch_1_lcd_track_name
```

These repeat through `ch_16_*` for FaderPort 16.

## LCD track names

Each channel has a track-name target for its LCD scribble strip:

```text
ch_1_lcd_track_name
...
ch_16_lcd_track_name
```

The library stores the SysEx template for each channel:

```text
F0 00 01 06 02 12 <strip> 00 00 {text} F7
```

`<strip>` is generated per channel:

- channels 1-8 use strips 0-7 on `port_1`
- channels 9-16 use strips 0-7 on `port_2`

Keep track names to 7 ASCII characters for best fit on the scribble strips.
The `{text}` placeholder is intentionally left unresolved in the library so the
USB-MIDI adapter can insert encoded text at send time.

## Example mapping

Use the USB-MIDI adapter instance name as the mapping prefix:

```toml
[adapters.faderport]
type = "usb_midi"
enabled = true
input_port = "PreSonus FP16 Port 1"
output_port = "PreSonus FP16 Port 1"
midi_library = "presonus_faderport"

[[mappings]]
id = "faderport-channel-1-to-x32-monitor-send"
source = "faderport:ch_1_fader"
target = "x32_foh:/ch/01/mix/01/level"
input_min = 0.0
input_max = 16383.0
output_min = 0.0
output_max = 1.0
```

Display targets such as `faderport:ch_1_lcd_track_name` are text/SysEx targets.
They are included in the library now so a future concrete USB-MIDI adapter can
drive the LCD track names directly.
