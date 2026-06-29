from pathlib import Path

import pytest

from midijuggler.config import load_config, save_connections
from midijuggler.datapoint.types import ConnectionSpec


def test_save_connections_replaces_existing_sections(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[web]
host = "127.0.0.1"
port = 8080

[adapters.xtouch_mini]
type = "midi"
enabled = true
midi_library = "behringer_xtouch_mini"

[adapters.x32_foh]
type = "osc"
enabled = true
osc_library = "behringer_x32"

[[devices]]
id = "xtouch_mini"
adapter = "xtouch_mini"
library = "behringer_xtouch_mini"
library_kind = "midi"

[[devices]]
id = "x32_foh"
adapter = "x32_foh"
library = "behringer_x32"
library_kind = "osc"

[[connections]]
id = "old"
source = "gpio.pin17"
target = "midi.cc_1_64"
modifier = "range_map"
input_min = 0.0
input_max = 1.0
output_min = 0.0
output_max = 127.0
invert = false
""".strip()
        + "\n",
        encoding="utf-8",
    )

    save_connections(
        config_path,
        [
            ConnectionSpec(
                id="learned",
                source="xtouch_mini.layer_a_fader",
                target="x32_foh./ch/01/mix/01/level",
                input_min=0.0,
                input_max=127.0,
                output_min=0.0,
                output_max=1.0,
            )
        ],
    )

    config = load_config(config_path)
    assert len(config.connections) == 1
    assert config.connections[0].id == "learned"
    assert "old" not in config_path.read_text(encoding="utf-8")


def test_save_connections_removes_inline_connections_array(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[web]
host = "127.0.0.1"
port = 8080

connections = [
  { id = "legacy", source = "gpio.pin17", target = "midi.cc_1_64" },
]

[[devices]]
id = "midi"
adapter = "midi"
library_kind = "midi"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    save_connections(
        config_path,
        [
            ConnectionSpec(
                id="learned",
                source="gpio.pin17",
                target="midi.cc_1_64",
            )
        ],
    )

    saved_text = config_path.read_text(encoding="utf-8")
    assert "connections = [" not in saved_text
    assert "[[connections]]" in saved_text
    import tomllib

    with config_path.open("rb") as handle:
        payload = tomllib.load(handle)
    assert len(payload["connections"]) == 1
    assert payload["connections"][0]["id"] == "learned"


def test_load_config_reports_helpful_toml_error_for_duplicate_connection_key(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[[connections]]
id = "first"
source = "gpio.pin17"
target = "midi.cc_1_64"
modifier = "range_map"
input_min = 0.0
input_max = 1.0
output_min = 0.0
output_max = 127.0
invert = false
id = "second"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid TOML") as exc_info:
        load_config(config_path)

    message = str(exc_info.value)
    assert "line 11" in message
    assert "[[connections]]" in message
