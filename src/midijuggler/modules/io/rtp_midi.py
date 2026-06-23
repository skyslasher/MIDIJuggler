"""RTP-MIDI I/O module."""

from __future__ import annotations

from midijuggler.adapters.rtp_midi import RtpMidiAdapter
from midijuggler.config import AppConfig
from midijuggler.datapoint.store import DataPointStore
from midijuggler.device.registry import DeviceRegistry
from midijuggler.device.types import DeviceConfig
from midijuggler.modules.io.midi import MidiIOModule


class RtpMidiIOModule(MidiIOModule):
    """Reuse MIDI data-point handling for RTP-MIDI adapters."""

    def __init__(
        self,
        adapter: RtpMidiAdapter,
        device: DeviceConfig,
        store: DataPointStore,
        config: AppConfig,
        device_registry: DeviceRegistry,
    ) -> None:
        super().__init__(adapter, device, store, config, device_registry)
        self.adapter = adapter
