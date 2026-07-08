# BandHelper integration

BandHelper can drive MIDIJuggler song context on the Pi:

- **Tempo:** Ableton Link (`Settings > Tempo & Pitch > Send Tempo to Ableton Link`)
- **Tonart:** OSC preset per song (Ableton Link carries no key metadata)

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

## BandHelper: Tempo via Ableton Link

1. *Settings > Tempo & Pitch* → **Send Tempo to Ableton Link** on
2. *Set Up Ableton Link* → Link aktivieren
3. Pro Song im Repertoire ein **Tempo** setzen
4. *Settings > App Control* → **Song Selection** → Aktion **Tempo**

Beim Songwechsel aktualisiert BandHelper die Link-Session. MIDIJuggler folgt als
Link-Peer und schreibt die BPM in den Master Clock (`clock.bpm`).

## BandHelper: Tonart via OSC

Ableton Link transportiert **keine Tonart**. BandHelper unterstützt in OSC-Presets
keine dynamischen Platzhalter — pro Song ein Preset mit festem Key-String.

1. *Repertoire > MIDI/OSC Devices* → OSC-Gerät mit Pi-IP und Port **9000**
2. *Repertoire > MIDI/OSC Presets* → OSC-Nachricht:
   - Adresse: `/midijuggler/song/key`
   - Typ: string
   - Wert: z. B. `Am`, `Bb`, `F# minor`
3. Preset dem Song zuweisen
4. *Settings > App Control* → **Song Selection** → **Send MIDI/OSC Presets**

Optional getrennte Nachrichten:

| Adresse | Argument | Datapoint |
|---------|----------|-----------|
| `/midijuggler/song/key` | string `Am` | `song.key_root` + `song.key_minor` |
| `/midijuggler/song/key_root` | string `Bb` oder int `0..11` | `song.key_root` |
| `/midijuggler/song/key_mode` | `minor` / `major` oder `1` / `0` | `song.key_minor` |

## Datapoints

| ID | Typ | Bedeutung |
|----|-----|-----------|
| `song.link_tempo` | float | Aktuelles Link-Tempo |
| `song.link_peers` | int | Anzahl Link-Peers |
| `song.key_root` | int | Grundton `0=C` … `11=B` |
| `song.key_minor` | bool | `true` = Moll |

Später für Wing-Effekte: Connections von `song.key_root` / `song.key_minor` auf
Zielgeräte legen.

## Hinweise

- iPad und Pi im gleichen WLAN; Multicast für Link erlauben
- `follow_when_running = false` (Standard): lokaler Transport behält BPM-Vorrang
- Beat/Phase über Link ist bewusst noch nicht angebunden
