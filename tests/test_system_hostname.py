import pytest

from midijuggler.system_hostname import (
    get_hostname,
    scripts_dir,
    set_hostname_script,
    validate_hostname,
)


def test_validate_hostname_normalizes_to_lowercase() -> None:
    assert validate_hostname("Stage-Box-1") == "stage-box-1"


@pytest.mark.parametrize(
    "hostname",
    [
        "",
        "-bad",
        "bad-",
        "has spaces",
        "a" * 64,
        "bad_underscore",
    ],
)
def test_validate_hostname_rejects_invalid_values(hostname: str) -> None:
    with pytest.raises(ValueError):
        validate_hostname(hostname)


def test_get_hostname_strips_domain_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "midijuggler.system_hostname.socket.gethostname",
        lambda: "dietpi.local",
    )
    assert get_hostname() == "dietpi"


def test_scripts_dir_honors_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pytest.TempPathFactory,
) -> None:
    scripts = tmp_path / "custom-scripts"
    scripts.mkdir()
    monkeypatch.setenv("MIDIJUGGLER_SCRIPTS_DIR", str(scripts))
    assert scripts_dir() == scripts
    assert set_hostname_script() == scripts / "set-hostname.sh"


def test_scripts_dir_falls_back_to_packaged_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MIDIJUGGLER_SCRIPTS_DIR", raising=False)
    resolved = scripts_dir()
    assert resolved.name == "scripts"
