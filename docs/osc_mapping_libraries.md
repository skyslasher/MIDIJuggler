# OSC mapping libraries

MIDIJuggler ships OSC mapping libraries for common mixer targets. The libraries
are data files, not hard-coded routing rules. Use them as address catalogs when
creating mappings for an OSC adapter instance.

Available libraries:

- `behringer_x32`
- `behringer_wing`
- `rotary_display`

The web API exposes the packaged libraries:

```text
GET /api/osc-libraries
GET /api/osc-libraries/behringer_x32
GET /api/osc-libraries/behringer_wing
GET /api/osc-libraries/rotary_display
```

## Mapping syntax

Mappings still target an adapter instance. Combine the adapter instance name
with the OSC address from a library:

```toml
[adapters.x32_foh]
type = "osc"
enabled = true
listen_host = "0.0.0.0"
listen_port = 9000
remote_host = "192.168.10.32"
remote_port = 10023

[[mappings]]
id = "footswitch-to-x32-channel-01-bus-01-send"
source = "gpio:pin17"
target = "x32_foh:/ch/01/mix/01/level"
input_min = 0.0
input_max = 1.0
output_min = 0.0
output_max = 1.0
invert = false
```

The `x32_foh` prefix selects the adapter instance. The remaining part,
`/ch/01/mix/01/level`, is the OSC address from the `behringer_x32` library.

Because MIDIJuggler is primarily intended for monitor control, channel sends
are the largest and most important part of the packaged libraries.

## Behringer X32

The X32 library contains common targets for:

- 32 input channel faders: `/ch/01/mix/fader` ... `/ch/32/mix/fader`
- 32 input channel on switches: `/ch/01/mix/on` ... `/ch/32/mix/on`
- 32 input channel pan parameters
- 512 channel send levels: `/ch/01/mix/01/level` ... `/ch/32/mix/16/level`
- 16 bus master faders and on switches
- 8 DCA faders and on switches
- main stereo fader and on switch

X32 fader-style values use normalized `0.0` to `1.0` ranges. On switches use
integer `0` or `1`, where `1` means on and `0` means muted/off.

## Behringer Wing

The Wing library contains common targets for:

- 48 channel strip faders: `/ch/1/fdr` ... `/ch/48/fdr`
- 48 channel strip mutes: `/ch/1/mute` ... `/ch/48/mute`
- 48 channel strip pan parameters
- 768 channel send levels: `/ch/1/send/1/lvl` ... `/ch/48/send/16/lvl`
- 16 bus faders and mutes
- 8 matrix faders and mutes
- 16 DCA faders and mutes
- main 1/main 2 faders and mutes
- 16 FX rack mix levels: `/fx/1/fxmix` ... `/fx/16/fxmix`
- common reverb parameters per FX slot (pre-delay, decay, size, filters)
- common delay parameters per FX slot (time, feedback, BBD delay)
- channel/bus/matrix/main insert on/off switches for pre/post FX inserts

Wing mute values use integer `0` or `1`, where `1` means muted and `0` means
unmuted. Wing fader parameters can expose both normalized and engineering values
depending on the response format; these presets use the normalized control range
for MIDIJuggler mappings.

FX slot parameters depend on the effect model loaded in that slot. For example,
`/fx/1/time` applies when a delay (ST-DL, TAP-DL, …) is loaded; `/fx/2/dcy`
applies when a reverb is loaded. Use `/fx/n/?` on the desk to list parameters
for the active model. `fxmix` is always valid for every slot.

## Extending libraries

The packaged files live in `src/midijuggler/osc_libraries/*.toml`.

Use `[[parameters]]` for one fixed address and `[[templates]]` for repeated
ranges such as channels or buses. Template fields support Python's string format
syntax, for example `{channel:02d}` for X32 two-digit channel paths.

For channel-send grids, templates can use multiple ranges:

```toml
[[templates]]
id = "ch_{channel:02d}_bus_{bus:02d}_send"
address = "/ch/{channel:02d}/mix/{bus:02d}/level"
ranges = [
  { name = "channel", start = 1, end = 32 },
  { name = "bus", start = 1, end = 16 },
]
```

## Rotary display

The `rotary_display` library catalogs OSC addresses for the Elecrow rotary
encoder. Bind it to an OSC adapter device in the Connections UI:

```toml
[[devices]]
uid = "rotary_encoder"
id = "rotary_encoder"
name = "Rotary Display"
adapter = "osc"
library = "rotary_display"
library_kind = "osc"
```

Encoder commands (`direction = "source"`):

| Parameter | Address |
|-----------|---------|
| Set BPM | `/midijuggler/clock/bpm` |
| Start/stop | `/midijuggler/clock/start_stop` |
| Click toggle | `/midijuggler/clock/click_toggle` |
| Tap tempo | `/midijuggler/clock/tap_tempo` |
| Click interval | `/midijuggler/clock/click_interval` |
| Hello | `/midijuggler/rotary/hello` |

Host feedback (`direction = "target"`):

| Parameter | Address |
|-----------|---------|
| Sync state | `/midijuggler/rotary/sync` |
| Beat pulse | `/midijuggler/rotary/beat` |

Example connections:

```toml
[[connections]]
id = "rotary-bpm-to-clock"
source = "rotary_encoder./midijuggler/clock/bpm"
target = "clock.bpm_set"
modifier = "passthrough"

[[connections]]
id = "clock-beat-to-rotary"
source = "clock.beat"
target = "rotary_encoder./midijuggler/rotary/beat"
modifier = "passthrough"
```

When `[rotary_display] enabled = true`, the interface module handles transport
directly. Default connections are only auto-added when that module is disabled
and a `rotary_display` device exists. See [`rotary_display.md`](rotary_display.md).
