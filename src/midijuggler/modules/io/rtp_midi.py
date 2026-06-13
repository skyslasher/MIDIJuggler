"""RTP-MIDI I/O module."""

from __future__ import annotations

from midijuggler.adapters.rtp_midi import RtpMidiAdapter
from midijuggler.config import AppConfig
from midijuggler.datapoint.store import DataPointStore
from midijuggler.modules.io.midi import MidiIOModule


class RtpMidiIOModule(MidiIOModule):
    """Reuse MIDI data-point handling for RTP-MIDI adapters."""

    def __init__(
        self,
        adapter: RtpMidiAdapter,
        store: DataPointStore,
        config: AppConfig,
    ) -> None:
        super().__init__(adapter, store, config)
        self.adapter = adapter
