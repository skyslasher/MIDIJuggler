from pathlib import Path

import pytest

from midijuggler.config import load_config, parse_config


def test_parse_config_reads_web_adapters_and_mappings() -> None:
    config = parse_config(
        {
            "web": {"host": "127.0.0.1", "port": 9090},
            "adapters": {"gpio": {"enabled": True, "pins": [17]}},
            "mappings": [
                {
                    "id": "switch",
                    "source": "gpio:pin17",
                    "target": "usb_midi:cc:1:64",
                    "invert": True,
                }
            ],
        }
    )

    assert config.web.host == "127.0.0.1"
    assert config.web.port == 9090
    assert config.adapters["gpio"].enabled is True
    assert config.adapters["gpio"].options["pins"] == [17]
    assert config.adapters["osc"].enabled is False
    assert config.mappings[0].id == "switch"
    assert config.mappings[0].invert is True


def test_load_config_reads_toml_file(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [web]
        host = "0.0.0.0"
        port = 8081

        [[mappings]]
        id = "pedal"
        source = "osc:/pedal"
        target = "usb_midi:cc:1:11"
        input_min = 0.0
        input_max = 1.0
        output_min = 0.0
        output_max = 127.0
        """,
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.web.port == 8081
    assert config.mappings[0].target == "usb_midi:cc:1:11"


def test_parse_config_rejects_incomplete_mapping() -> None:
    with pytest.raises(ValueError, match="missing required fields"):
        parse_config({"mappings": [{"id": "broken", "source": "gpio:pin17"}]})
