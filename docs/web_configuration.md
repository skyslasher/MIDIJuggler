# Web configuration

MIDIJuggler exposes first configuration endpoints in the web interface. The
initial editable area is GPIO input selection.

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
