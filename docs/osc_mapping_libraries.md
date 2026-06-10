# OSC mapping libraries

MIDIJuggler ships OSC mapping libraries for common mixer targets. The libraries
are data files, not hard-coded routing rules. Use them as address catalogs when
creating mappings for an OSC adapter instance.

Available libraries:

- `behringer_x32`
- `behringer_wing`

The web API exposes the packaged libraries:

```text
GET /api/osc-libraries
GET /api/osc-libraries/behringer_x32
GET /api/osc-libraries/behringer_wing
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
id = "footswitch-to-x32-channel-01-mute"
source = "gpio:pin17"
target = "x32_foh:/ch/01/mix/on"
input_min = 0.0
input_max = 1.0
output_min = 0.0
output_max = 1.0
invert = false
```

The `x32_foh` prefix selects the adapter instance. The remaining part,
`/ch/01/mix/on`, is the OSC address from the `behringer_x32` library.

## Behringer X32

The X32 library contains common targets for:

- 32 input channel faders: `/ch/01/mix/fader` ... `/ch/32/mix/fader`
- 32 input channel on switches: `/ch/01/mix/on` ... `/ch/32/mix/on`
- 32 input channel pan parameters
- channel-to-bus-01 send levels
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
- 16 bus faders and mutes
- 8 matrix faders and mutes
- 16 DCA faders and mutes
- main 1/main 2 faders and mutes

Wing mute values use integer `0` or `1`, where `1` means muted and `0` means
unmuted. Wing fader parameters can expose both normalized and engineering values
depending on the response format; these presets use the normalized control range
for MIDIJuggler mappings.

## Extending libraries

The packaged files live in `src/midijuggler/osc_libraries/*.toml`.

Use `[[parameters]]` for one fixed address and `[[templates]]` for repeated
ranges such as channels or buses. Template fields support Python's string format
syntax, for example `{channel:02d}` for X32 two-digit channel paths.
