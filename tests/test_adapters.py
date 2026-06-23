from midijuggler.adapters import build_adapters
from midijuggler.adapters.osc import OscAdapter
from midijuggler.adapters.rtp_midi import RtpMidiAdapter
from midijuggler.adapters.midi import MidiAdapter
from midijuggler.config import AdapterConfig
from midijuggler.eventbus import EventBus


def test_build_adapters_creates_multiple_named_instances_per_type() -> None:
    adapters = build_adapters(
        {
            "osc": AdapterConfig(enabled=True, options={}, kind="osc"),
            "osc_pedalboard": AdapterConfig(enabled=True, options={}, kind="osc"),
            "usb_stage": AdapterConfig(enabled=True, options={}, kind="midi"),
            "rtp_remote": AdapterConfig(enabled=True, options={}, kind="rtp_midi"),
            "usb_disabled": AdapterConfig(enabled=False, options={}, kind="midi"),
        },
        EventBus(),
    )

    assert [adapter.name for adapter in adapters] == [
        "osc",
        "osc_pedalboard",
        "usb_stage",
        "rtp_remote",
    ]
    assert isinstance(adapters[0], OscAdapter)
    assert isinstance(adapters[1], OscAdapter)
    assert isinstance(adapters[2], MidiAdapter)
    assert isinstance(adapters[3], RtpMidiAdapter)
