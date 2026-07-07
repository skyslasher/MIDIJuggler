from midijuggler.config import RotaryDisplayDeviceConfig, parse_config, save_rotary_display_config
from midijuggler.modules.interface.rotary_display.device_config import (
    build_device_config_commands,
    device_config_fingerprint,
    push_device_config_sync,
    read_config_response_lines,
)


def test_parse_rotary_display_device_section() -> None:
    config = parse_config(
        {
            "rotary_display": {
                "enabled": True,
                "device": {
                    "transport": "both",
                    "wifi_enabled": True,
                    "wifi_ssid": "testnet",
                    "wifi_pass": "secret",
                    "host": "192.168.1.10",
                    "port": 9000,
                    "listen_port": 9001,
                    "pulse_enabled": False,
                    "bpm_step": 2.0,
                },
            }
        }
    )
    device = config.rotary_display.device
    assert device.transport == "both"
    assert device.wifi_ssid == "testnet"
    assert device.wifi_pass == "secret"
    assert device.host == "192.168.1.10"
    assert device.pulse_enabled is False
    assert device.bpm_step == 2.0


def test_build_device_config_commands() -> None:
    device = RotaryDisplayDeviceConfig(
        transport="both",
        wifi_enabled=True,
        wifi_ssid="home",
        wifi_pass="pass123",
        host="midijuggler.local",
        port=9000,
        listen_port=9001,
    )
    assert build_device_config_commands(device) == [
        "transport both",
        "wifi_enabled on",
        "wifi ssid home",
        "wifi pass pass123",
        "host midijuggler.local",
        "port 9000",
        "listen_port 9001",
    ]


def test_build_device_config_commands_wifi_clear() -> None:
    device = RotaryDisplayDeviceConfig()
    assert "wifi clear" in build_device_config_commands(device)


def test_device_config_fingerprint_changes_with_password() -> None:
    base = RotaryDisplayDeviceConfig()
    changed = RotaryDisplayDeviceConfig(wifi_pass="new")
    assert device_config_fingerprint(base) != device_config_fingerprint(changed)


def test_save_rotary_display_config_writes_device_section(tmp_path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
        [rotary_display]
        enabled = false
        transport = "osc"
        """,
        encoding="utf-8",
    )
    config = parse_config(
        {
            "rotary_display": {
                "enabled": True,
                "transport": "both",
                "serial_port": "/dev/ttyACM0",
                "device": {
                    "transport": "both",
                    "host": "pi.local",
                    "wifi_pass": "secret",
                },
            }
        }
    )
    save_rotary_display_config(config_file, config.rotary_display)
    saved = config_file.read_text(encoding="utf-8")
    assert "[rotary_display.device]" in saved
    assert 'wifi_pass = "secret"' in saved
    assert 'serial_port = "/dev/ttyACM0"' in saved


class FakePort:
    def __init__(self, responses: list[list[str]]) -> None:
        self._responses = responses
        self.written: list[bytes] = []

    def write(self, payload: bytes) -> None:
        self.written.append(payload)

    def flush(self) -> None:
        return None

    def readline(self) -> bytes:
        if not self._responses:
            return b""
        line = self._responses[0].pop(0)
        if not self._responses[0]:
            self._responses.pop(0)
        return (line + "\n").encode("utf-8")


def test_push_device_config_sync() -> None:
    port = FakePort([["ok"], ["ok"], ["ok"]])
    result = push_device_config_sync(
        port,
        ["transport both", "host midijuggler.local"],
    )
    assert result["ok"] is True
    assert b"config apply\n" in port.written


def test_read_config_response_lines_stops_on_ok() -> None:
    port = FakePort([["cfg transport=both", "ok"]])
    lines = read_config_response_lines(port, timeout_s=0.1)
    assert lines == ["cfg transport=both", "ok"]


def test_read_config_response_lines_ignores_device_noise() -> None:
    port = FakePort([["hello", "renderHome: dynamic parts=14", "ok"]])
    lines = read_config_response_lines(port, timeout_s=0.1)
    assert lines == ["ok"]


def test_push_device_config_sync_fails_with_timeout_reason() -> None:
    port = FakePort([["hello"]])
    result = push_device_config_sync(port, ["transport both"], timeout_s=0.05)
    assert result["ok"] is False
    assert result["reason"] == "timeout waiting for ok"
    assert result["failed_command"] == "transport both"
