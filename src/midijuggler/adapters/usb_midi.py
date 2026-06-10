"""USB MIDI adapter stub."""

from midijuggler.adapters.base import Adapter


class UsbMidiAdapter(Adapter):
    protocol = "USB MIDI"
