# protocol.py
import struct
import socket
from typing import Optional, Tuple

MAGIC_COOKIE = 0xabcddcba

TYPE_OFFER   = 0x2
TYPE_REQUEST = 0x3
TYPE_PAYLOAD = 0x4

RESULT_NOT_OVER = 0x0
RESULT_TIE      = 0x1
RESULT_LOSS     = 0x2
RESULT_WIN      = 0x3

NAME_LEN = 32
UDP_PORT = 13122

# Fixed message sizes (TCP framing by fixed-size reads)
OFFER_SIZE          = 4 + 1 + 2 + NAME_LEN          # 39
REQUEST_SIZE        = 4 + 1 + 1 + NAME_LEN          # 38
CLIENT_PAYLOAD_SIZE = 4 + 1 + 5                      # 10  ("Hittt"/"Stand")
SERVER_PAYLOAD_SIZE = 4 + 1 + 1 + 2 + 1              # 9   (result + rank(2) + suit(1))

def _pack_name(name: str) -> bytes:
    raw = name.encode("utf-8", errors="ignore")[:NAME_LEN]
    return raw.ljust(NAME_LEN, b"\x00")

def _unpack_name(b: bytes) -> str:
    return b.split(b"\x00", 1)[0].decode("utf-8", errors="ignore")

def pack_offer(tcp_port: int, server_name: str) -> bytes:
    return struct.pack("!IBH", MAGIC_COOKIE, TYPE_OFFER, tcp_port & 0xFFFF) + _pack_name(server_name)

def unpack_offer(data: bytes) -> Optional[Tuple[int, str]]:
    if len(data) < OFFER_SIZE:
        return None
    cookie, mtype, tcp_port = struct.unpack("!IBH", data[:7])
    if cookie != MAGIC_COOKIE or mtype != TYPE_OFFER:
        return None
    name = _unpack_name(data[7:7+NAME_LEN])
    return tcp_port, name

def pack_request(num_rounds: int, client_name: str) -> bytes:
    # cookie(4) + type(1) + rounds(1) + name(32)
    return struct.pack("!IBB", MAGIC_COOKIE, TYPE_REQUEST, num_rounds & 0xFF) + _pack_name(client_name)

def unpack_request(data: bytes) -> Optional[Tuple[int, str]]:
    if len(data) < REQUEST_SIZE:
        return None
    cookie, mtype, rounds = struct.unpack("!IBB", data[:6])
    if cookie != MAGIC_COOKIE or mtype != TYPE_REQUEST:
        return None
    name = _unpack_name(data[6:6+NAME_LEN])
    return rounds, name

def pack_client_payload(decision: str) -> bytes:
    # exactly 5 bytes: "Hittt" or "Stand"
    if decision not in ("Hittt", "Stand"):
        raise ValueError("decision must be exactly 'Hittt' or 'Stand'")
    return struct.pack("!IB", MAGIC_COOKIE, TYPE_PAYLOAD) + decision.encode("ascii")

def unpack_client_payload(data: bytes) -> Optional[str]:
    if len(data) != CLIENT_PAYLOAD_SIZE:
        return None
    cookie, mtype = struct.unpack("!IB", data[:5])
    if cookie != MAGIC_COOKIE or mtype != TYPE_PAYLOAD:
        return None
    decision = data[5:10].decode("ascii", errors="ignore")
    if decision not in ("Hittt", "Stand"):
        return None
    return decision

def pack_server_payload(result_code: int, rank: int, suit: int) -> bytes:
    # cookie(4) + type(1) + result(1) + rank(2) + suit(1)
    return struct.pack("!IBBHB", MAGIC_COOKIE, TYPE_PAYLOAD, result_code & 0xFF, rank & 0xFFFF, suit & 0xFF)

def unpack_server_payload(data: bytes) -> Optional[Tuple[int, int, int]]:
    if len(data) != SERVER_PAYLOAD_SIZE:
        return None
    cookie, mtype, result, rank, suit = struct.unpack("!IBBHB", data)
    if cookie != MAGIC_COOKIE or mtype != TYPE_PAYLOAD:
        return None
    return result, rank, suit

def recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
    """Read exactly n bytes from TCP. Return None if peer closed. Raises socket.timeout on timeout."""
    chunks = []
    got = 0
    while got < n:
        part = sock.recv(n - got)
        if not part:
            return None
        chunks.append(part)
        got += len(part)
    return b"".join(chunks)
