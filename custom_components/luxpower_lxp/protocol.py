"""LuxPower WiFi dongle local TCP protocol (port 8000).

Pure Python, no Home Assistant imports, so it can be unit tested on its own.

Outer frame (all multi-byte ints little endian):

    0  2  prefix 0xA1 0x1A
    2  2  protocol (1 = normal, 2 = write multi)
    4  2  frame length (bytes following this field)
    6  1  address (always 1)
    7  1  tcp function (0xC1 heartbeat, 0xC2 translated data)
    8 10  dongle (datalog) serial, ASCII
   18  .  payload

Translated data payload:

    0  2  data length (bytes after this field, including the 2 byte CRC)
    2  1  address (0 = request, 1 = reply)
    3  1  device function (3 read hold, 4 read input, 6 write single, 16 write multi)
    4 10  inverter serial, ASCII
   14  2  start register
   16  .  function specific body
    .  2  CRC16/MODBUS over payload[2:-2]
"""

from __future__ import annotations

from dataclasses import dataclass, field
import struct

PREFIX = b"\xa1\x1a"
HEADER_LEN = 6  # prefix + protocol + frame length

TCP_HEARTBEAT = 0xC1
TCP_TRANSLATED_DATA = 0xC2

FUNC_READ_HOLD = 0x03
FUNC_READ_INPUT = 0x04
FUNC_WRITE_SINGLE = 0x06
FUNC_WRITE_MULTI = 0x10


class ProtocolError(Exception):
    """Raised when a frame cannot be decoded."""


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def _serial(value: str) -> bytes:
    raw = value.encode("ascii")
    if len(raw) != 10:
        raise ValueError(f"Serial numbers must be 10 characters, got {value!r}")
    return raw


def _wrap(tcp_function: int, protocol: int, dongle_serial: str, payload: bytes) -> bytes:
    body = bytes([1, tcp_function]) + _serial(dongle_serial) + payload
    return PREFIX + struct.pack("<HH", protocol, len(body)) + body


def _translated(
    dongle_serial: str,
    inverter_serial: str,
    function: int,
    register: int,
    body: bytes,
) -> bytes:
    inner = bytes([0, function]) + _serial(inverter_serial) + struct.pack("<H", register) + body
    payload = (
        struct.pack("<H", len(inner) + 2) + inner + struct.pack("<H", crc16_modbus(inner))
    )
    protocol = 2 if function == FUNC_WRITE_MULTI else 1
    return _wrap(TCP_TRANSLATED_DATA, protocol, dongle_serial, payload)


def build_read(
    dongle_serial: str, inverter_serial: str, function: int, register: int, count: int
) -> bytes:
    if function not in (FUNC_READ_HOLD, FUNC_READ_INPUT):
        raise ValueError("function must be read hold or read input")
    return _translated(
        dongle_serial, inverter_serial, function, register, struct.pack("<H", count)
    )


def build_write_single(
    dongle_serial: str, inverter_serial: str, register: int, value: int
) -> bytes:
    return _translated(
        dongle_serial,
        inverter_serial,
        FUNC_WRITE_SINGLE,
        register,
        struct.pack("<H", value & 0xFFFF),
    )


def build_write_multi(
    dongle_serial: str, inverter_serial: str, register: int, values: list[int]
) -> bytes:
    data = b"".join(struct.pack("<H", v & 0xFFFF) for v in values)
    body = struct.pack("<HB", len(values), len(data)) + data
    return _translated(dongle_serial, inverter_serial, FUNC_WRITE_MULTI, register, body)


@dataclass
class Frame:
    """A decoded frame received from the dongle."""

    tcp_function: int
    dongle_serial: str
    raw: bytes
    # Only set for translated data frames
    function: int | None = None
    inverter_serial: str | None = None
    register: int | None = None
    values: dict[int, int] = field(default_factory=dict)
    exception: bool = False


def split_frames(buffer: bytearray) -> list[bytes]:
    """Remove and return all complete frames from ``buffer``.

    Garbage before a valid prefix is discarded.
    """
    frames: list[bytes] = []
    while True:
        start = buffer.find(PREFIX)
        if start < 0:
            # Keep a trailing 0xA1 in case the prefix is split across reads
            del buffer[: max(0, len(buffer) - 1)]
            return frames
        if start:
            del buffer[:start]
        if len(buffer) < HEADER_LEN:
            return frames
        (length,) = struct.unpack_from("<H", buffer, 4)
        total = HEADER_LEN + length
        if len(buffer) < total:
            return frames
        frames.append(bytes(buffer[:total]))
        del buffer[:total]


def parse_frame(raw: bytes) -> Frame:
    if len(raw) < 18 or raw[:2] != PREFIX:
        raise ProtocolError("Frame too short or bad prefix")
    tcp_function = raw[7]
    dongle = raw[8:18].decode("ascii", errors="replace")
    frame = Frame(tcp_function=tcp_function, dongle_serial=dongle, raw=raw)
    if tcp_function != TCP_TRANSLATED_DATA:
        return frame

    # Like lxp-bridge, trust the outer frame length rather than the inner data
    # length field: payload = 2 byte data length, inner data, 2 byte CRC.
    protocol = struct.unpack_from("<H", raw, 2)[0]
    inner = raw[20:-2]
    if len(inner) < 14:
        raise ProtocolError("Translated data payload too short")
    if struct.unpack("<H", raw[-2:])[0] != crc16_modbus(inner):
        raise ProtocolError("CRC mismatch")

    function = inner[1]
    frame.exception = bool(function & 0x80)
    frame.function = function & 0x7F
    frame.inverter_serial = inner[2:12].decode("ascii", errors="replace")
    (frame.register,) = struct.unpack_from("<H", inner, 12)
    body = inner[14:]

    if frame.exception:
        return frame

    if frame.function in (FUNC_READ_HOLD, FUNC_READ_INPUT):
        # Replies with protocol 2/5 carry a byte count first; protocol 1 does not.
        if protocol != 1 or (body and body[0] == len(body) - 1):
            n_bytes, data = (body[0], body[1:]) if body else (0, b"")
        else:
            n_bytes, data = len(body), body
        if not data or len(data) != n_bytes or n_bytes % 2:
            raise ProtocolError("Read reply length mismatch")
        for i in range(n_bytes // 2):
            frame.values[frame.register + i] = struct.unpack_from("<H", data, i * 2)[0]
    elif frame.function == FUNC_WRITE_SINGLE and len(body) >= 2:
        frame.values[frame.register] = struct.unpack_from("<H", body, 0)[0]
    return frame
