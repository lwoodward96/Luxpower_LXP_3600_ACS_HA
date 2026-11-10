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
    payload = struct.pack("<H", len(inner) + 2) + inner + struct.pack("<H", crc16_modbus(inner))
    frame_body = bytes([1, 0xC2]) + DONGLE.encode() + payload
    return b"\xa1\x1a" + struct.pack("<HH", 2, len(frame_body)) + frame_body


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
    assert struct.unpack_from("<H", pkt, 18)[0] == 18  # data length incl. CRC
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


# ---- Real frames taken from lxp-bridge's test suite (captured from hardware) --

LXPB_DONGLE = "2222222222"
LXPB_INVERTER = "5555555555"


def test_lxp_bridge_build_read_hold():
    assert build_read(LXPB_DONGLE, LXPB_INVERTER, FUNC_READ_HOLD, 12, 3) == bytes(
        [161, 26, 1, 0, 32, 0, 1, 194, *[50] * 10, 18, 0, 0, 3, *[53] * 10, 12, 0, 3, 0, 112, 38]
    )


def test_lxp_bridge_build_read_inputs():
    assert build_read(LXPB_DONGLE, LXPB_INVERTER, FUNC_READ_INPUT, 0, 40) == bytes(
        [161, 26, 1, 0, 32, 0, 1, 194, *[50] * 10, 18, 0, 0, 4, *[53] * 10, 0, 0, 40, 0, 42, 132]
    )


def test_lxp_bridge_parse_read_hold_reply():
    raw = bytes(
        [161, 26, 2, 0, 37, 0, 1, 194, *[50] * 10, 23, 0, 1, 3, *[53] * 10, 12, 0, 6,
         22, 6, 20, 5, 16, 57, 93, 135]
    )
    frame = parse_frame(raw)
    assert frame.function == FUNC_READ_HOLD
    assert frame.inverter_serial == LXPB_INVERTER
    # time registers: 2022-06-20 05:16:57
    assert frame.values == {12: 22 | (6 << 8), 13: 20 | (5 << 8), 14: 16 | (57 << 8)}


def test_lxp_bridge_parse_read_inputs_reply():
    raw = bytes([
        161, 26, 2, 0, 111, 0, 1, 194, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 97, 0, 1, 4, 53, 53,
        53, 53, 53, 53, 53, 53, 53, 53, 0, 0, 80, 32, 0, 0, 0, 0, 0, 0, 0, 250, 1, 77, 0, 0, 53, 0,
        0, 0, 0, 0, 0, 128, 13, 0, 0, 114, 9, 0, 16, 132, 0, 142, 19, 0, 0, 198, 13, 202, 5, 232,
        3, 114, 9, 0, 10, 80, 112, 142, 19, 0, 0, 0, 0, 0, 0, 36, 15, 0, 0, 0, 0, 0, 0, 91, 0, 83,
        0, 87, 0, 114, 0, 0, 0, 1, 0, 102, 0, 174, 14, 183, 12, 71, 187,
    ])
    frame = parse_frame(raw)
    assert frame.function == FUNC_READ_INPUT
    assert len(frame.values) == 40
    assert frame.values[0] == 32  # status
    assert frame.values[4] == 506  # battery 50.6 V
    assert frame.values[5] & 0xFF == 77  # SOC


def test_protocol1_read_reply_without_length_byte():
    inner = bytes([1, FUNC_READ_HOLD]) + LXPB_INVERTER.encode() + struct.pack("<HH", 64, 80)
    payload = struct.pack("<H", len(inner) + 2) + inner + struct.pack("<H", crc16_modbus(inner))
    body = bytes([1, 0xC2]) + LXPB_DONGLE.encode() + payload
    raw = b"\xa1\x1a" + struct.pack("<HH", 1, len(body)) + body
    assert parse_frame(raw).values == {64: 80}
