import struct

import pytest

from luxpower_lxp.protocol import (
    FUNC_READ_HOLD,
    FUNC_READ_INPUT,
    FUNC_WRITE_MULTI,
    FUNC_WRITE_SINGLE,
    TCP_HEARTBEAT,
    ProtocolError,
    build_read,
    build_write_multi,
    build_write_single,
    crc16_modbus,
    parse_frame,
    split_frames,
)

DONGLE = "2222222222"
INVERTER = "5555555555"


def make_reply(function: int, register: int, body: bytes) -> bytes:
    inner = bytes([1, function]) + INVERTER.encode() + struct.pack("<H", register) + body
    payload = struct.pack("<H", len(inner)) + inner + struct.pack("<H", crc16_modbus(inner))
    frame_body = bytes([1, 0xC2]) + DONGLE.encode() + payload
    return b"\xa1\x1a" + struct.pack("<HH", 1, len(frame_body)) + frame_body


def test_crc_known_value():
    # Standard CRC-16/MODBUS check value
    assert crc16_modbus(b"123456789") == 0x4B37


def test_build_read_hold_layout():
    pkt = build_read(DONGLE, INVERTER, FUNC_READ_HOLD, 0, 12)
    assert pkt[:2] == b"\xa1\x1a"
    assert struct.unpack_from("<HH", pkt, 2) == (1, 32)
    assert len(pkt) == 38
    assert pkt[6:8] == bytes([1, 0xC2])
    assert pkt[8:18] == DONGLE.encode()
    assert struct.unpack_from("<H", pkt, 18)[0] == 16  # data length
    assert pkt[20:22] == bytes([0, FUNC_READ_HOLD])
    assert pkt[22:32] == INVERTER.encode()
    assert pkt[32:36] == bytes([0, 0, 12, 0])
    assert struct.unpack_from("<H", pkt, 36)[0] == crc16_modbus(pkt[20:36])


def test_build_write_single_and_multi():
    pkt = build_write_single(DONGLE, INVERTER, 21, 0xABCD)
    assert pkt[21] == FUNC_WRITE_SINGLE
    assert pkt[32:36] == bytes([21, 0, 0xCD, 0xAB])

    pkt = build_write_multi(DONGLE, INVERTER, 12, [1, 2, 3])
    assert struct.unpack_from("<H", pkt, 2)[0] == 2  # protocol
    assert pkt[21] == FUNC_WRITE_MULTI
    assert pkt[32:34] == bytes([12, 0])
    assert pkt[34:37] == bytes([3, 0, 6])
    assert pkt[37:43] == bytes([1, 0, 2, 0, 3, 0])


def test_bad_serial_rejected():
    with pytest.raises(ValueError):
        build_read("short", INVERTER, FUNC_READ_INPUT, 0, 1)


def test_parse_read_reply():
    values = [1, 2, 0x1234]
    data = b"".join(struct.pack("<H", v) for v in values)
    frame = parse_frame(make_reply(FUNC_READ_INPUT, 40, bytes([len(data)]) + data))
    assert frame.function == FUNC_READ_INPUT
    assert frame.inverter_serial == INVERTER
    assert frame.values == {40: 1, 41: 2, 42: 0x1234}


def test_parse_write_single_reply():
    frame = parse_frame(make_reply(FUNC_WRITE_SINGLE, 64, struct.pack("<H", 80)))
    assert frame.values == {64: 80}


def test_parse_exception_reply():
    frame = parse_frame(make_reply(FUNC_WRITE_SINGLE | 0x80, 64, b"\x02"))
    assert frame.exception and frame.function == FUNC_WRITE_SINGLE


def test_crc_mismatch():
    raw = bytearray(make_reply(FUNC_WRITE_SINGLE, 64, struct.pack("<H", 80)))
    raw[-1] ^= 0xFF
    with pytest.raises(ProtocolError):
        parse_frame(bytes(raw))


def test_split_frames_handles_garbage_and_partial():
    a = make_reply(FUNC_WRITE_SINGLE, 1, struct.pack("<H", 1))
    b = make_reply(FUNC_WRITE_SINGLE, 2, struct.pack("<H", 2))
    buf = bytearray(b"junk" + a + b[:10])
    assert split_frames(buf) == [a]
    buf.extend(b[10:])
    assert split_frames(buf) == [b]
    assert buf == bytearray()


def test_heartbeat_parses():
    body = bytes([1, TCP_HEARTBEAT]) + DONGLE.encode() + b"\x00"
    raw = b"\xa1\x1a" + struct.pack("<HH", 1, len(body)) + body
    frame = parse_frame(raw)
    assert frame.tcp_function == TCP_HEARTBEAT
    assert frame.dongle_serial == DONGLE
