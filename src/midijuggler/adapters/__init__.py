"""Adapter factories for MIDIJuggler inputs and outputs."""

from midijuggler.adapters.base import Adapter
from midijuggler.adapters.gpio import GpioAdapter
from midijuggler.adapters.osc import OscAdapter
from midijuggler.adapters.rtp_midi import RtpMidiAdapter
from midijuggler.adapters.usb_midi import UsbMidiAdapter
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus

ADAPTER_CLASSES = {
    "osc": OscAdapter,
    "usb_midi": UsbMidiAdapter,
    "rtp_midi": RtpMidiAdapter,
    "gpio": GpioAdapter,
}


def build_adapters(configs: dict[str, AdapterConfig], bus: EventBus) -> list[Adapter]:
    return [
        adapter_class(name=name, config=config, bus=bus)
        for name, adapter_class in ADAPTER_CLASSES.items()
        if (config := configs.get(name)) and config.enabled
    ]
