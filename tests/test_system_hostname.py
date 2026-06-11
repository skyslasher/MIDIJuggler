import pytest

from midijuggler.system_hostname import get_hostname, validate_hostname


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
