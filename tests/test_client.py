"""Exercise LuxClient against a fake dongle on localhost."""

import asyncio
import struct

import pytest

from luxpower_lxp.client import LuxClient, LuxError
from luxpower_lxp.protocol import (
    FUNC_READ_HOLD,
    FUNC_READ_INPUT,
    FUNC_WRITE_MULTI,
    FUNC_WRITE_SINGLE,
    TCP_HEARTBEAT,
    crc16_modbus,
    split_frames,
)

DONGLE = "BA12345678"
INVERTER = "3456789012"


def reply(function: int, register: int, body: bytes) -> bytes:
    inner = bytes([1, function]) + INVERTER.encode() + struct.pack("<H", register) + body
    payload = struct.pack("<H", len(inner) + 2) + inner + struct.pack("<H", crc16_modbus(inner))
    frame_body = bytes([1, 0xC2]) + DONGLE.encode() + payload
    return b"\xa1\x1a" + struct.pack("<HH", 2, len(frame_body)) + frame_body


class FakeDongle:
    def __init__(self) -> None:
        self.input = {i: i * 10 for i in range(80)}
        self.hold = {i: 0 for i in range(160)}
        self.heartbeat_echoes = 0
        self.ignore_next = 0
        self.writes: list[tuple[int, int]] = []

    async def handle(self, reader, writer):
        # Send a heartbeat and an unrelated broadcast first, like a real dongle
        hb = bytes([1, TCP_HEARTBEAT]) + DONGLE.encode() + b"\x00"
        writer.write(b"\xa1\x1a" + struct.pack("<HH", 1, len(hb)) + hb)
        buf = bytearray()
        while data := await reader.read(4096):
            buf.extend(data)
            for raw in split_frames(buf):
                if raw[7] == TCP_HEARTBEAT:
                    self.heartbeat_echoes += 1
                    continue
                if self.ignore_next:
                    self.ignore_next -= 1
                    continue
                fn = raw[21]
                (reg,) = struct.unpack_from("<H", raw, 32)
                if fn in (FUNC_READ_INPUT, FUNC_READ_HOLD):
                    (count,) = struct.unpack_from("<H", raw, 34)
                    src = self.input if fn == FUNC_READ_INPUT else self.hold
                    data = b"".join(struct.pack("<H", src[r]) for r in range(reg, reg + count))
                    # Noise: a reply for some other register arrives first
                    writer.write(reply(FUNC_READ_INPUT, 999, bytes([2, 0, 0])))
                    writer.write(reply(fn, reg, bytes([len(data)]) + data))
                elif fn == FUNC_WRITE_SINGLE:
                    (val,) = struct.unpack_from("<H", raw, 34)
                    if reg == 9999:
                        writer.write(reply(fn | 0x80, reg, b"\x02"))
                    else:
                        self.hold[reg] = val
                        self.writes.append((reg, val))
                        writer.write(reply(fn, reg, struct.pack("<H", val)))
                elif fn == FUNC_WRITE_MULTI:
                    (count,) = struct.unpack_from("<H", raw, 34)
                    for i in range(count):
                        self.hold[reg + i] = struct.unpack_from("<H", raw, 37 + i * 2)[0]
                    writer.write(reply(fn, reg, struct.pack("<H", count)))
                await writer.drain()
        writer.close()


@pytest.fixture
async def dongle():
    fake = FakeDongle()
    server = await asyncio.start_server(fake.handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client = LuxClient("127.0.0.1", port, DONGLE, INVERTER, timeout=1, retries=1)
    yield fake, client
    await client.close()
    server.close()
    await server.wait_closed()


async def test_read_and_write(dongle):
    fake, client = dongle
    values = await client.read_input(0, 40)
    assert values[5] == 50 and len(values) == 40
    assert fake.heartbeat_echoes == 1

    assert await client.write_hold(64, 75) == 75
    assert (await client.read_hold(64, 1)) == {64: 75}

    await client.write_hold_multi(12, [1, 2, 3])
    assert [fake.hold[r] for r in (12, 13, 14)] == [1, 2, 3]


async def test_rejected_write(dongle):
    _, client = dongle
    with pytest.raises(LuxError):
        await client.write_hold(9999, 1)


async def test_retry_after_lost_reply(dongle):
    fake, client = dongle
    fake.ignore_next = 1
    assert (await client.read_input(40, 2)) == {40: 400, 41: 410}


async def test_unreachable():
    client = LuxClient("127.0.0.1", 1, DONGLE, INVERTER, timeout=0.5, retries=0)
    with pytest.raises(LuxError):
        await client.read_input(0, 1)
