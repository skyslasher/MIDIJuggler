from __future__ import annotations

from midijuggler.config import load_config, save_devices
from midijuggler.device.identity import generate_device_uid, parse_device_identity
from midijuggler.device.types import DeviceConfig


def test_parse_device_identity_migrates_legacy_id_field() -> None:
    uid, name = parse_device_identity({"id": "wing_foh", "label": "Wing FOH"})
    assert uid == "wing_foh"
    assert name == "Wing FOH"


def test_generate_device_uid_uses_adapter_slug() -> None:
    uid = generate_device_uid("wing_foh")
    assert uid.startswith("wing_foh_")


def test_renaming_device_name_preserves_connection_endpoints(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[adapters.wing_foh]
type = "osc"
enabled = true
osc_library = "behringer_wing"

[[devices]]
id = "wing_foh"
adapter = "wing_foh"
library = "behringer_wing"
library_kind = "osc"

[[connections]]
id = "to-wing-fader"
source = "wing_foh./ch/1/fdr"
target = "wing_foh./ch/1/fdr"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    from midijuggler.config import load_config

    config = load_config(config_path)
    device = config.devices["wing_foh"]
    assert device.uid == "wing_foh"
    assert device.name == "wing_foh"

    save_devices(
        config_path,
        {
            device.uid: DeviceConfig(
                uid=device.uid,
                name="Wing FOH",
                adapter=device.adapter,
                library=device.library,
                library_kind=device.library_kind,
            )
        },
    )

    reloaded = load_config(config_path)
    assert reloaded.devices["wing_foh"].name == "Wing FOH"
    assert reloaded.connections[0].source == "wing_foh./ch/1/fdr"
    assert "uid = " in config_path.read_text(encoding="utf-8")
