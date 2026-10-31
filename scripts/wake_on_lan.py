"""Send a Wake-on-LAN magic packet to a sleeping LAN machine.

Developer/owner tooling for the remote-workflow wake ladder. The packet must
originate inside the target's LAN broadcast domain (directed Internet delivery
is out of scope by design). Usage from any awake Python machine on the LAN::

    python scripts/wake_on_lan.py AA:BB:CC:DD:EE:FF
    python scripts/wake_on_lan.py AA-BB-CC-DD-EE-FF --broadcast 192.168.1.255 --port 9

No dependencies beyond the standard library.
"""

from __future__ import annotations

import argparse
import re
import socket


def parse_mac(value: str) -> bytes:
    """Parse ``AA:BB:CC:DD:EE:FF`` (also ``-``/space separated) to 6 bytes."""
    cleaned = re.sub(r"[^0-9a-fA-F]", "", value.strip())
    if len(cleaned) != 12 or not re.fullmatch(r"[0-9a-fA-F]{12}", cleaned):
        raise ValueError(f"Invalid MAC address: {value!r}")
    return bytes(int(cleaned[index : index + 2], 16) for index in range(0, 12, 2))


def build_magic_packet(mac: bytes) -> bytes:
    """Return the 102-byte magic packet: 6x 0xFF sync then 16x MAC."""
    if len(mac) != 6:
        raise ValueError("MAC must be exactly 6 bytes")
    return b"\xff" * 6 + mac * 16


def send_magic_packet(
    mac: str, broadcast: str = "255.255.255.255", port: int = 9, count: int = 3
) -> int:
    """Broadcast the magic packet ``count`` times; return bytes sent."""
    packet = build_magic_packet(parse_mac(mac))
    total = 0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for _ in range(count):
            total += sock.sendto(packet, (broadcast, port))
    return total


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mac", help="Target MAC, e.g. AA:BB:CC:DD:EE:FF")
    parser.add_argument("--broadcast", default="255.255.255.255")
    parser.add_argument("--port", type=int, default=9)
    parser.add_argument("--count", type=int, default=3)
    args = parser.parse_args(argv)
    sent = send_magic_packet(args.mac, args.broadcast, args.port, args.count)
    print(f"sent {sent} bytes to {args.mac} via {args.broadcast}:{args.port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
