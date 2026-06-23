# HID input (Linux evdev)

MIDIJuggler can read Linux HID devices (gamepads, USB controllers, custom
input nodes) through the `hid` adapter. Each configured evdev code becomes an
input data point that can be mapped like GPIO or MIDI sources.

HID support is **Linux-only**. It uses the `evdev` Python package to read
`/dev/input/event*`.

## Install the `hid` pip extra

Install optional dependencies **into the same Python environment that runs
MIDIJuggler** — not with a global `pip install` on the system Python.

### Local development

From the repository root, use the project virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[test,hid]"
```

To combine HID with other hardware extras:

```bash
python -m pip install -e ".[test,midi,hid]"
```

Run the service with that venv active:

```bash
midijuggler --config configs/example.toml
```

### Raspberry Pi / DietPi (systemd service)

On a Pi, MIDIJuggler runs from the dedicated service venv at
`/opt/midijuggler/venv`. Install the extra there as the `midijuggler` user:

```bash
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e "/opt/midijuggler/app[hid]"
```

Typical production install with MIDI and HID together:

```bash
sudo -u midijuggler /opt/midijuggler/venv/bin/python -m pip install -e "/opt/midijuggler/app[alsa,midi,hid]"
```

After `git pull`, re-run the pip command if dependencies changed, then restart:

```bash
sudo systemctl restart midijuggler.service
```

Verify the module is available:

```bash
/opt/midijuggler/venv/bin/python -c "import evdev; print('evdev ok')"
```

## Device permissions

The service user must be allowed to read the input device node. Add the
`input` group on DietPi:

```bash
sudo usermod -aG input midijuggler
sudo systemctl restart midijuggler.service
```

List devices and codes on the Pi:

```bash
ls -l /dev/input/event*
sudo evtest
```

`evtest` (package `evtest` on Debian/DietPi) helps find evdev code names such
as `BTN_A` or `ABS_X`.

## Configuration

HID adapters are configured in TOML. There is no web form yet; edit
`config.toml` and restart the service, or use a config file that already
contains the section.

### By device path

```toml
[adapters.gamepad]
type = "hid"
enabled = true
device = "/dev/input/event5"
codes = ["BTN_A", "BTN_B", "ABS_X", "ABS_Y"]
```

### By USB vendor/product ID

```toml
[adapters.gamepad]
type = "hid"
enabled = true
vendor_id = "0x046d"
product_id = "0xc21f"
codes = ["BTN_A", "BTN_B"]
```

### Explicit control names and value ranges

```toml
[adapters.gamepad]
type = "hid"
enabled = true
device = "/dev/input/event5"

[[adapters.gamepad.inputs]]
code = "BTN_A"
control = "button_a"

[[adapters.gamepad.inputs]]
code = "ABS_X"
control = "stick_x"
value_min = -1.0
value_max = 1.0
```

Compact `codes` uses lowercase evdev names as control IDs (`BTN_A` →
`btn_a`, `KEY_A` → `key_a`). Buttons and keys normalize to `0.0` / `1.0`.
Axes are scaled using the device absinfo range into `value_min` /
`value_max`.

### Keyboard keystrokes

Point the adapter at a keyboard evdev node (for example
`/dev/input/event0` or a path under `/dev/input/by-id/`). Enable
`keystrokes = true` to publish every `KEY_*` press and release without
listing each key first:

```toml
[adapters.keyboard]
type = "hid"
enabled = true
device = "/dev/input/by-id/usb-...-event-kbd"
keystrokes = true
grab = true
```

With `keystrokes = true`, each key becomes a control such as `key_a` or
`key_space` (`keyboard.key_a` as a data point). `grab = true` (the
default when keystrokes are enabled) keeps key events from also reaching
other programs on the same device.

You can still map individual keys explicitly with `codes = ["A",
"KEY_ENTER"]` or learn them in the web UI. Single letters and common
names such as `ENTER` or `SPACE` are accepted as aliases for `KEY_*`
codes.

## Data points and mappings

Each control is exposed as an input data point:

```text
gamepad.btn_a
gamepad.stick_x
```

Legacy mapping syntax:

```toml
[[mappings]]
id = "gamepad-a-to-midi"
source = "gamepad:btn_a"
target = "midi:note:60:0"
```

Incoming HID events also appear in the web monitor and can be used in learn
mode (`HidEvent`).

## Multiple instances

Like OSC and MIDI, you can define several HID instances with different
`type = "hid"` tables:

```toml
[adapters.pedal]
type = "hid"
enabled = true
device = "/dev/input/event3"
codes = ["BTN_0", "BTN_1"]
```

The adapter table name (`pedal`) is the routing prefix in mappings and data
point IDs (`pedal.btn_0`).
