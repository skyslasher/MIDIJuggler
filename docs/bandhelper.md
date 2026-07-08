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
