# MIDI mapping libraries

MIDIJuggler ships MIDI mapping libraries for controller surfaces. The libraries
are catalogs of logical control IDs and MIDI messages that concrete MIDI
adapter implementations can use for learn mode, routing and feedback.

Available libraries:

- `behringer_xtouch_mini`
- `presonus_faderport`

The web API exposes the packaged libraries:

```text
GET /api/midi-libraries
GET /api/midi-libraries/behringer_xtouch_mini
GET /api/midi-libraries/presonus_faderport
```

## Behringer X-Touch Mini

The X-Touch Mini library provides a logical Standard Mode mapping catalog:

- Layer A and Layer B each have 8 encoder-turn controls
- Layer A and Layer B each have 8 encoder-push controls
- Layer A and Layer B each have 16 buttons split into top and bottom rows
- Layer A and Layer B each expose the shared 60 mm fader as separate mapping IDs
- Feedback targets are provided for 8 LED rings and 16 button LEDs
- Mode/layer targets are provided for Standard Mode, MC Mode, Layer A and Layer B

Common logical IDs:

```text
layer_a_encoder_1_turn
layer_a_encoder_1_push
layer_a_top_button_1
layer_a_bottom_button_1
layer_a_fader
layer_b_encoder_1_turn
layer_b_top_button_1
layer_b_fader
layer_a_encoder_1_led_ring
layer_b_encoder_1_led_ring
encoder_1_led_ring
button_1_led
select_layer_a
select_layer_b
set_standard_mode
set_mc_mode
```

The X-Touch Mini is user-programmable with the Behringer X-Touch Editor. This
library uses a predictable layout that is suitable for MIDIJuggler mappings:

- Layer A encoder turns: CC 1-8
- Layer A master fader: CC 9
- Layer B master fader: CC 10
- Layer B encoder turns: CC 11-18
- Layer A encoder pushes: notes 0-7
- Layer B encoder pushes: notes 24-31
- Layer A top/bottom buttons: notes 8-15 and 16-23
- Layer B top/bottom buttons: notes 32-39 and 40-47

Feedback targets follow the documented X-Touch Mini receive behavior:

- Layer A LED rings: CC 1-8, values 0-28
- Layer B LED rings: CC 11-18, values 0-28
- Button LEDs: notes 0-15, value 0 off, 1 on, 2 blinking
- Layer selection: program change 0 for Layer A, 1 for Layer B
- Mode selection: CC 127 value 0 for Standard Mode, 1 for MC Mode

Example monitor-send mapping:

```toml
[adapters.xtouch_mini]
type = "midi"
enabled = true
input_port = "X-TOUCH MINI"
output_port = "X-TOUCH MINI"
midi_library = "behringer_xtouch_mini"

[[mappings]]
id = "xtouch-mini-layer-a-encoder-1-to-x32-send"
source = "xtouch_mini:layer_a_encoder_1_turn"
target = "x32_foh:/ch/01/mix/01/level"
input_min = 0.0
input_max = 127.0
output_min = 0.0
output_max = 1.0
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
MIDI adapter can insert encoded text at send time.

## Example mapping

Use the MIDI adapter instance name as the mapping prefix:

```toml
[adapters.faderport]
type = "midi"
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
They are included in the library now so a future concrete MIDI adapter can
drive the LCD track names directly.
