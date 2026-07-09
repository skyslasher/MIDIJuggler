import socket

import pytest

from midijuggler.modules.interface.rotary_display.module import _udp_send
from midijuggler.rotary_mdns import (
    invalidate_mdns_cache,
    is_mdns_hostname,
    is_ipv4_address,
    mdns_fqdn,
    resolve_mdns_ipv4,
    resolve_udp_host,
)


def test_is_mdns_hostname() -> None:
    assert is_mdns_hostname("rotary-267248.local")
    assert not is_mdns_hostname("192.168.1.10")
    assert not is_mdns_hostname("midijuggler")


def test_is_ipv4_address() -> None:
    assert is_ipv4_address("10.0.0.5")
    assert not is_ipv4_address("rotary-267248.local")


def test_mdns_fqdn_adds_trailing_dot() -> None:
    assert mdns_fqdn("rotary-267248.local") == "rotary-267248.local."


def test_resolve_udp_host_returns_ipv4_literal() -> None:
    assert resolve_udp_host("192.168.1.60") == "192.168.1.60"


def test_resolve_udp_host_uses_getaddrinfo_for_regular_hostnames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, family=0, type=0: [
            (socket.AF_INET, socket.SOCK_DGRAM, 0, "", ("10.1.2.3", 0))
        ],
    )
    assert resolve_udp_host("midijuggler") == "10.1.2.3"


def test_resolve_udp_host_uses_mdns_for_local_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "midijuggler.rotary_mdns.resolve_mdns_ipv4",
        lambda host, force=False: "192.168.0.42",
    )
    assert resolve_udp_host("rotary-267248.local") == "192.168.0.42"


def test_resolve_udp_host_falls_back_to_cached_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "midijuggler.rotary_mdns.resolve_mdns_ipv4",
        lambda host, force=False: None,
    )
    assert (
        resolve_udp_host("rotary-267248.local", fallback_ip="192.168.0.99")
        == "192.168.0.99"
    )


def test_resolve_udp_host_mdns_failure_raises_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "midijuggler.rotary_mdns.resolve_mdns_ipv4",
        lambda host, force=False: None,
    )
    with pytest.raises(OSError, match="mDNS resolution failed"):
        resolve_udp_host("rotary-267248.local")


def test_resolve_mdns_ipv4_uses_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalidate_mdns_cache("rotary-cache.local")
    request_calls: list[str] = []

    monkeypatch.setattr(
        "midijuggler.rotary_mdns.zeroconf_available",
        lambda: True,
    )

    class FakeResolver:
        def __init__(self, server: str) -> None:
            self.server = server

        def request(self, zc: object, timeout: float, **kwargs: object) -> bool:
            request_calls.append(self.server)
            return True

        def parsed_addresses(self) -> list[str]:
            return ["192.168.1.10"]

    monkeypatch.setattr(
        "zeroconf.AddressResolverIPv4",
        FakeResolver,
    )
    monkeypatch.setattr(
        "midijuggler.rotary_mdns._get_zeroconf",
        lambda: object(),
    )

    assert resolve_mdns_ipv4("rotary-cache.local") == "192.168.1.10"
    assert resolve_mdns_ipv4("rotary-cache.local") == "192.168.1.10"
    assert len(request_calls) == 1

    invalidate_mdns_cache("rotary-cache.local")
    assert resolve_mdns_ipv4("rotary-cache.local", force=True) == "192.168.1.10"
    assert len(request_calls) == 2


def test_udp_send_resolves_local_host_before_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[bytes, tuple[str, int]]] = []

    class FakeSocket:
        def __enter__(self) -> "FakeSocket":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def sendto(self, payload: bytes, address: tuple[str, int]) -> None:
            sent.append((payload, address))

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: FakeSocket())
    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.resolve_udp_host",
        lambda host, fallback_ip=None, force=False: "192.168.0.42",
    )

    payload = b"sync"
    _udp_send(payload, "rotary-267248.local", 9001)

    assert sent == [(payload, ("192.168.0.42", 9001))]


def test_udp_send_re_resolves_local_host_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[tuple[bool, str | None]] = []
    sent: list[tuple[bytes, tuple[str, int]]] = []

    class FakeSocket:
        def __enter__(self) -> "FakeSocket":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def sendto(self, payload: bytes, address: tuple[str, int]) -> None:
            sent.append((payload, address))
            if address[0] == "192.168.0.1":
                raise OSError("send failed")

    def fake_resolve(
        host: str,
        *,
        fallback_ip: str | None = None,
        force: bool = False,
    ) -> str:
        attempts.append((force, fallback_ip))
        return "192.168.0.2" if force else "192.168.0.1"

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: FakeSocket())
    monkeypatch.setattr(
        "midijuggler.modules.interface.rotary_display.module.resolve_udp_host",
        fake_resolve,
    )

    payload = b"sync"
    _udp_send(payload, "rotary-267248.local", 9001, fallback_ip="192.168.0.9")

    assert attempts == [(False, "192.168.0.9"), (True, "192.168.0.9")]
    assert sent == [
        (payload, ("192.168.0.1", 9001)),
        (payload, ("192.168.0.2", 9001)),
    ]


def test_resolve_mdns_ipv4_without_zeroconf_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("midijuggler.rotary_mdns.zeroconf_available", lambda: False)
    assert resolve_mdns_ipv4("rotary-267248.local") is None
