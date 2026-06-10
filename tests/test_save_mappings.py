from pathlib import Path

from midijuggler.config import load_config, save_mappings
from midijuggler.mapping import MappingRule


def test_save_mappings_replaces_existing_sections(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[web]
host = "127.0.0.1"
port = 8080

[[mappings]]
id = "old"
source = "gpio:pin17"
target = "midi:cc:1:64"
input_min = 0.0
input_max = 1.0
output_min = 0.0
output_max = 127.0
invert = false
""".strip()
        + "\n",
        encoding="utf-8",
    )

    save_mappings(
        config_path,
        [
            MappingRule(
                id="learned",
                source="xtouch_mini:layer_a_fader",
                target="x32_foh:/ch/01/mix/01/level",
                input_min=0.0,
                input_max=127.0,
                output_min=0.0,
                output_max=1.0,
            )
        ],
    )

    config = load_config(config_path)
    assert len(config.mappings) == 1
    assert config.mappings[0].id == "learned"
    assert "old" not in config_path.read_text(encoding="utf-8")
