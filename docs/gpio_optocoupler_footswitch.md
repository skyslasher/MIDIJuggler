# GPIO footswitch input with PC817 optocoupler

This circuit protects Raspberry Pi GPIO inputs while allowing a 5 V polling
voltage on the footswitch side. The 5 V side can therefore drive LEDs inside
the footswitch enclosure, while the Pi only ever sees a 3.3 V GPIO signal.

Repeat the circuit once per footswitch input.

## Recommended input channel

```text
5 V footswitch side                         Raspberry Pi side
-------------------                         -----------------

 +5V_SW
   |
   |     R1 820 ohm
   +----/\/\/\/----+---->|----+
                   |   PC817  |
                   | input LED|
                   |          |
          optional |          |
          status   |          |
          LED path |          |
                   |          |
 Footswitch contact          |
   o/ o----------------------+
   |
  GND_SW


                       PC817 output transistor

 Pi 3V3 ---- R2 10 kOhm ----+---- GPIO input
                             |
                             C
                          PC817
                             E
                             |
                           Pi GND
```

Behavior:

- footswitch open: PC817 LED is off, transistor is off, GPIO reads high
- footswitch closed: PC817 LED is on, transistor pulls GPIO low
- configure the GPIO input as active-low in software

`GND_SW` and `Pi GND` may be kept separate if the 5 V switch supply is isolated.
If the switch-side 5 V comes from the Raspberry Pi 5 V pin, both grounds are
already related through the Pi supply; the PC817 still provides level protection
and input-current limiting, but not full galvanic isolation.

## Values

| Part | Suggested value | Notes |
| --- | --- | --- |
| U1 | PC817, one channel per switch | Common, inexpensive optocoupler |
| R1 | 820 ohm, 0.25 W | About 4.5 mA through the PC817 LED at 5 V |
| R2 | 10 kOhm | External pull-up to 3.3 V; Pi internal pull-up also works |
| C1 | 10 nF to 100 nF, optional | From GPIO to Pi GND for extra hardware debounce |

R1 calculation for the PC817 input LED:

```text
R1 = (5.0 V - 1.2 V) / 0.0045 A = 844 ohm
```

Use the nearest standard value, 820 ohm. Values from 680 ohm to 1 kOhm are
reasonable for typical PC817 parts and Raspberry Pi GPIO pull-ups. If the
footswitch LED is wired in series with the PC817 input LED, recalculate R1 with
both LED forward voltages:

```text
R1 = (5.0 V - Vf_PC817 - Vf_switch_LED) / I_LED
```

For many visible LEDs this leaves little voltage headroom at 5 V. Prefer a
separate LED branch when the footswitch provides separate LED pins.

## Footswitch LED wiring

### Preferred: separate LED pins in the footswitch

If the footswitch has separate switch contacts and LED pins, keep the switch
sense current and LED current in separate branches:

```text
Sense branch:
+5V_SW -> R1 820 ohm -> PC817 input LED -> switch contact -> GND_SW

LED branch:
+5V_SW -> R_LED -> footswitch LED -> switch contact or LED control -> GND_SW
```

Choose `R_LED` for the LED current and color:

```text
R_LED = (5.0 V - Vf_LED) / I_LED
```

Examples:

- red LED, 2.0 V forward voltage, 5 mA: 560 ohm to 680 ohm
- blue/white LED, 3.0 V forward voltage, 3 mA: 680 ohm

### Two-wire illuminated footswitches

Two-wire illuminated switches often contain an LED and resistor internally.
They can usually be placed on the 5 V switch side, but their internal circuit
can leak current while the contact is open. If this causes false triggering,
add a pulldown resistor of 10 kOhm to 47 kOhm across the PC817 input LED or use
a switch with separate LED terminals.

## Raspberry Pi connection

Use only the PC817 transistor side on the Raspberry Pi GPIO header:

```text
PC817 collector -> GPIO pin, plus R2 to Pi 3V3
PC817 emitter   -> Pi GND
```

Do not connect the 5 V footswitch line directly to any Raspberry Pi GPIO pin.
The Pi input should be configured as a digital input with pull-up and active-low
logic. The example configuration already uses GPIO pins 17, 27 and 22; duplicate
the circuit for each of those inputs.

## Debounce

Mechanical footswitches bounce. Keep software debounce enabled in the GPIO
adapter once the stub is replaced by a concrete implementation. The example
configuration uses:

```toml
[adapters.gpio]
enabled = true
# The number of inputs is controlled by the number of configured BCM GPIO pins.
pins = [17, 27, 22]
active_low = true
bounce_ms = 25
poll_interval_ms = 5
```

If long cables are used, add optional hardware filtering:

```text
GPIO input -> C1 10 nF to 100 nF -> Pi GND
```

Place C1 close to the Raspberry Pi side of the optocoupler output.

## Bill of materials per input

- 1x PC817 optocoupler
- 1x 820 ohm resistor for PC817 input current
- 1x 10 kOhm resistor for the GPIO pull-up
- optional 1x 10 nF to 100 nF capacitor for hardware debounce/noise filtering
- optional LED resistor for footswitch LED wiring, if not built into the switch
