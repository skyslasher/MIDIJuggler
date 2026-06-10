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
    adapters: list[Adapter] = []
    for instance_name, config in configs.items():
        if not config.enabled:
            continue

        kind = config.kind or instance_name
        adapter_class = ADAPTER_CLASSES[kind]
        adapters.append(adapter_class(name=instance_name, config=config, bus=bus))

    return adapters
