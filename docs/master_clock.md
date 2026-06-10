# MIDI master clock

MIDIJuggler can run as a MIDI clock receiver and as a MIDI master clock. The
master clock emits MIDI timing clock at 24 PPQN and can send MIDI Start, Stop
and Continue messages to configured MIDI-capable adapter instances.

## Configuration

```toml
[master_clock]
enabled = true
bpm = 120.0
bpm_min = 40.0
bpm_max = 240.0
auto_start = false
output_targets = ["usb_midi", "rtp_midi"]
send_transport = true

bpm_osc_address = "/midijuggler/clock/bpm"
click_interval_osc_address = "/midijuggler/clock/click_interval"

bpm_msb_cc = 20
bpm_lsb_cc = 21
click_interval_cc = 22
midi_channel = 1

click_enabled = false
click_wav = "/etc/midijuggler/click.wav"
click_interval = "quarter"
click_audio_device = ""
```

`output_targets` are adapter instance names. Use USB MIDI and/or RTP-MIDI
instances depending on where MIDI Clock should be sent.

## Transport

Incoming MIDI realtime messages control the master clock:

| MIDI status | Meaning |
| --- | --- |
| `0xFA` | Start from tick 0 |
| `0xFB` | Continue from current tick |
| `0xFC` | Stop |

When transport changes and `send_transport = true`, MIDIJuggler also sends the
corresponding realtime message to all configured `output_targets`.

## BPM remote control

### OSC

Send a float BPM value:

```text
/midijuggler/clock/bpm 128.5
```

The OSC address is configurable through `bpm_osc_address`.

### MIDI CC MSB/LSB

BPM can also be controlled with two MIDI CC messages:

```text
CC 20 = BPM MSB
CC 21 = BPM LSB
```

The two 7-bit values form one 14-bit value. MIDIJuggler scales it into
`bpm_min` ... `bpm_max`.

## Audio click

If `click_enabled = true`, MIDIJuggler can play a WAV file through ALSA's
`aplay`, which works well with small USB sound cards on DietPi:

```toml
click_enabled = true
click_wav = "/etc/midijuggler/click.wav"
click_audio_device = "plughw:1,0"
```

The web UI discovers ALSA devices with `aplay -l` and shows them as a dropdown.
Click WAV files are discovered from `/etc/midijuggler/*.wav`. Playback always
uses `aplay`.

MIDIJuggler writes an ALSA config next to the active TOML config, usually
`/etc/midijuggler/asoundrc`, defining a PCM named `master_clock`. The master
clock always plays clicks through `aplay -D master_clock`; changing the audio
device in the web UI rewrites that generated PCM.

MIDIJuggler uses two ALSA strategies:

- hardware PCMs such as `hw:1,0` or `plughw:1,0`: generate `pcm.master_clock`
  as a `plug` wrapper around `pcm.master_clock_dmix`. The dmix slave is a direct
  `hw:X,Y` PCM. If `plughw:X,Y` is selected in the UI, MIDIJuggler automatically
  uses `hw:X,Y` internally for the dmix slave. The plug wrapper lets ALSA convert
  mono/stereo channel counts and sample formats from the click WAV before dmix.
- software PCMs such as `default`, `dmix`, `plug`, route plugins, or custom
  channel mappings: generate `pcm.master_clock` as a `plug` alias to the
  selected PCM

This avoids ALSA's `dmix plugin can be only connected to hw plugin` error while
still allowing custom softdevices, for example routing to selected channels on
a 5.1 sound card.

Click playback is triggered in the background, so a click WAV that is longer
than the configured click interval does not block the master clock from
triggering the next click. In hardware/dmix mode, clicks may overlap. In
software/alias mode, MIDIJuggler stops any still-running click process before
starting the next one, because many software PCMs still open the underlying
device exclusively.

The click interval can be:

- `eighth`
- `quarter`
- `half`
- `whole`

It can be changed remotely through OSC:

```text
/midijuggler/clock/click_interval "half"
```

or through `click_interval_cc`. MIDI CC values are mapped like this:

| Value range | Interval |
| --- | --- |
| `0..31` | eighth |
| `32..63` | quarter |
| `64..95` | half |
| `96..127` | whole |

## Internal clock parameters

Whenever BPM changes, the master clock publishes internal `ControlEvent`s with
source `clock`. These can be used by normal mappings:

| Mapping source | Meaning |
| --- | --- |
| `clock:bpm` | Current BPM |
| `clock:ppqn_tick_ms` | One MIDI clock tick in ms |
| `clock:sixteenth_ms` | 1/16 note duration in ms |
| `clock:eighth_ms` | 1/8 note duration in ms |
| `clock:quarter_ms` | 1/4 note duration in ms |
| `clock:half_ms` | 1/2 note duration in ms |
| `clock:whole_ms` | Whole note duration in ms |
| `clock:bar_4_4_ms` | One 4/4 bar in ms |

Example:

```toml
[[mappings]]
id = "clock-eighth-ms-to-delay-time"
source = "clock:eighth_ms"
target = "osc:/fx/delay/time_ms"
input_min = 50.0
input_max = 1000.0
output_min = 50.0
output_max = 1000.0
```

This keeps tempo-derived values available for effect parameters without special
case code in the mapping engine.
