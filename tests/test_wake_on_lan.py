"""Offline checks for the Wake-on-LAN sender; no packets are emitted."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/wake_on_lan.py"
spec = importlib.util.spec_from_file_location("wake_on_lan", SCRIPT)
assert spec is not None
assert spec.loader is not None
wol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wol)


@pytest.mark.parametrize("text", ["AA:BB:CC:DD:EE:FF", "aa-bb-cc-dd-ee-ff", "AABBCCDDEEFF"])
def test_parse_mac_accepts_common_forms(text):
    assert wol.parse_mac(text) == bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])


@pytest.mark.parametrize("text", ["", "AA:BB:CC", "AA:BB:CC:DD:EE:FG", "AA:BB:CC:DD:EE:FF:00"])
def test_parse_mac_rejects_bad_input(text):
    with pytest.raises(ValueError, match="Invalid MAC"):
        wol.parse_mac(text)


def test_magic_packet_structure():
    packet = wol.build_magic_packet(bytes([1, 2, 3, 4, 5, 6]))
    assert len(packet) == 102
    assert packet[:6] == b"\xff" * 6
    assert packet[6:] == bytes([1, 2, 3, 4, 5, 6]) * 16
    with pytest.raises(ValueError, match="exactly 6 bytes"):
        wol.build_magic_packet(b"short")


def test_send_uses_broadcast_socket(monkeypatch):
    calls = {}

    class FakeSocket:
        def __init__(self, *args, **kwargs):
            calls["broadcast"] = False

        def setsockopt(self, level, name, value):
            import socket as std_socket

            if name == std_socket.SO_BROADCAST and value == 1:
                calls["broadcast"] = True

        def sendto(self, packet, address):
            calls.setdefault("packets", []).append((packet, address))
            return len(packet)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(wol.socket, "socket", FakeSocket)
    total = wol.send_magic_packet("AA:BB:CC:DD:EE:FF", "192.168.1.255", 7, count=2)
    assert total == 204
    assert calls["broadcast"] is True
    assert len(calls["packets"]) == 2
    assert all(address == ("192.168.1.255", 7) for _, address in calls["packets"])
