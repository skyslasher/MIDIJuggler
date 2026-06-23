from midijuggler.adapters.wing_native import WingNativeAdapter
from midijuggler.clock import ClockBpmTracker
from midijuggler.config import AdapterConfig, parse_config
from midijuggler.eventbus import EventBus
from midijuggler.master_clock import MasterClock
from midijuggler.web.server import WebInterface


def test_status_payload_includes_wing_native_instances() -> None:
    bus = EventBus()
    adapter = WingNativeAdapter(
        name="wing_native_foh",
        config=AdapterConfig(
            enabled=True,
            kind="wing_native",
            options={
                "remote_host": "192.168.1.48",
                "native_port": 2222,
                "wing_library": "behringer_wing",
            },
        ),
        bus=bus,
    )
    adapter._connectivity.note_connected("192.168.1.48", 2222)  # noqa: SLF001
    adapter._connectivity.paths_cached = 42  # noqa: SLF001
    adapter.running = True

    config = parse_config(
        {
            "adapters": {
                "wing_native_foh": {
                    "type": "wing_native",
                    "enabled": True,
                    "remote_host": "192.168.1.48",
                    "native_port": 2222,
                    "wing_library": "behringer_wing",
                }
            }
        }
    )
    interface = WebInterface(
        config,
        bus,
        ClockBpmTracker(),
        MasterClock(config.master_clock, bus),
        wing_native_adapters={"wing_native_foh": adapter},
    )
    interface._adapter_runtime_status["wing_native_foh"] = {
        "status": "started",
        "detail": "Wing native connected to 192.168.1.48:2222",
        "connection_phase": "connected",
    }

    payload = interface._status_payload()

    assert payload["wing_native_instances"]
    instance = payload["wing_native_instances"][0]
    assert instance["name"] == "wing_native_foh"
    assert instance["runtime_active"] is True
    assert instance["connectivity"]["connected"] is True
    assert instance["connectivity"]["paths_cached"] == 42
    assert payload["adapters"]["wing_native_foh"]["wing_connectivity"]["connected"] is True
