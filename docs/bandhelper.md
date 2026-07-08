# BandHelper integration

BandHelper can drive MIDIJuggler song context on the Pi:

- **Tempo:** Ableton Link (`Settings > Tempo & Pitch > Send Tempo to Ableton Link`)
- **Key:** OSC preset per song (Ableton Link does not carry key metadata)

## Enable in MIDIJuggler

```toml
[bandhelper]
enabled = true
link_enabled = true
follow_when_running = false
min_bpm_delta = 0.5
```

Install the optional dependency on the Pi:

```bash
pip install 'midijuggler[ableton_link]'
```

## BandHelper: tempo via Ableton Link

1. *Settings > Tempo & Pitch* → turn on **Send Tempo to Ableton Link**
2. *Set Up Ableton Link* → enable Ableton Link
3. Set a **tempo** for each song in the repertoire
4. *Settings > App Control* → **Song Selection** → **Tempo** action

When you change songs, BandHelper updates the Link session tempo. MIDIJuggler
joins as a Link peer and writes the BPM to the master clock (`clock.bpm`).

## BandHelper: key via OSC

Ableton Link does **not** transport musical key. BandHelper OSC presets do not
support dynamic placeholders either — use one preset per song with a fixed key
string.

1. *Repertoire > MIDI/OSC Devices* → add an OSC device pointing at the Pi IP and port **9000**
2. *Repertoire > MIDI/OSC Presets* → add an OSC message:
   - Address: `/midijuggler/song/key`
   - Type: string
   - Value: e.g. `Am`, `Bb`, `F# minor`
3. Attach the preset to the song
4. *Settings > App Control* → **Song Selection** → **Send MIDI/OSC Presets**

Optional separate messages:

| Address | Argument | Datapoint |
|---------|----------|-----------|
| `/midijuggler/song/key` | string `Am` | `song.key_root` + `song.key_minor` |
| `/midijuggler/song/key_root` | string `Bb` or int `0..11` | `song.key_root` |
| `/midijuggler/song/key_mode` | `minor` / `major` or `1` / `0` | `song.key_minor` |

## Datapoints

| ID | Type | Meaning |
|----|------|---------|
| `song.link_tempo` | float | Current Link tempo |
| `song.link_peers` | int | Number of Link peers |
| `song.key_root` | int | Pitch class `0=C` … `11=B` |
| `song.key_minor` | bool | `true` = minor |

For Wing effects later: add Connections from `song.key_root` / `song.key_minor`
to target devices.

## Notes

- iPad and Pi must be on the same Wi‑Fi; allow multicast for Link
- `follow_when_running = false` (default): local transport keeps BPM priority while running
- Beat/phase over Link is intentionally not wired yet
- `song.link_peers` counts **other** Link apps in the session (not including MIDIJuggler). A value of `2` means three Link-enabled apps total, for example BandHelper on the iPad, MIDIJuggler on the Pi, and one more app on the LAN (another iPad, DAW, metronome app, etc.)

## Troubleshooting

### Link shows several peers but only MIDIJuggler should be active

Ableton Link discovers every Link-enabled app on the LAN. Close other Link clients (DAWs, metronome apps, second BandHelper devices) or disable Link in apps you are not using. The peer count in MIDIJuggler is informational only.

### No BPM change in the master clock

Check all of the following:

1. **BandHelper song selection must trigger the Tempo action** (*Settings > App Control > Song Selection > Tempo*). Selecting a song alone does not push tempo to Link unless that action is configured.
2. **`[bandhelper] enabled = true`** in TOML and restart MIDIJuggler after enabling.
3. **`pip install 'midijuggler[ableton_link]'`** on the Pi.
4. **Master clock transport stopped** unless `follow_when_running = true`.
5. **Song tempo differs** from the current master clock BPM by at least `min_bpm_delta`.

After a song change you should see journal lines such as `bandhelper Link session tempo …` and `bandhelper applied Link tempo …`, and monitor updates on `song.link_tempo` and `clock.bpm`.
