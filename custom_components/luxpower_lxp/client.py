"""Async TCP client for the LuxPower WiFi dongle (no Home Assistant imports)."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from .protocol import (
    FUNC_READ_HOLD,
    FUNC_READ_INPUT,
    FUNC_WRITE_MULTI,
    FUNC_WRITE_SINGLE,
    TCP_HEARTBEAT,
    TCP_TRANSLATED_DATA,
    Frame,
    ProtocolError,
    build_read,
    build_write_multi,
    build_write_single,
    parse_frame,
    split_frames,
)

_LOGGER = logging.getLogger(__name__)


class LuxError(Exception):
    """Communication with the dongle/inverter failed."""


class LuxClient:
    """Keeps one persistent TCP connection to the dongle.

    Requests are serialised (the dongle does not cope well with parallel
    requests) and replies are matched on (function, start register).
    """

    def __init__(
        self,
        host: str,
        port: int,
        dongle_serial: str,
        inverter_serial: str,
        timeout: float = 6.0,
        retries: int = 2,
    ) -> None:
        self.host = host
        self.port = port
        self.dongle_serial = dongle_serial
        self.inverter_serial = inverter_serial
        self.timeout = timeout
        self.retries = retries
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._pending: dict[tuple[int, int], asyncio.Future[Frame]] = {}

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        if self.connected:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout
            )
        except (OSError, asyncio.TimeoutError) as err:
            raise LuxError(f"Cannot connect to {self.host}:{self.port}: {err}") from err
        self._reader_task = asyncio.get_running_loop().create_task(self._read_loop())
        _LOGGER.debug("Connected to dongle %s:%s", self.host, self.port)

    async def close(self) -> None:
        task, self._reader_task = self._reader_task, None
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await self._drop_connection()

    async def _drop_connection(self) -> None:
        writer, self._writer, self._reader = self._writer, None, None
        if writer:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(LuxError("Connection closed"))
        self._pending.clear()

    async def _read_loop(self) -> None:
        buffer = bytearray()
        reader = self._reader
        try:
            while reader is not None:
                chunk = await reader.read(4096)
                if not chunk:
                    raise LuxError("Dongle closed the connection")
                buffer.extend(chunk)
                for raw in split_frames(buffer):
                    await self._handle(raw)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Reader stopped: %s", err)
        if self._reader is reader:
            self._reader_task = None
            await self._drop_connection()

    async def _handle(self, raw: bytes) -> None:
        try:
            frame = parse_frame(raw)
        except ProtocolError as err:
            _LOGGER.debug("Ignoring bad frame (%s): %s", err, raw.hex())
            return
        if frame.tcp_function == TCP_HEARTBEAT:
            # Echo heartbeats so the dongle keeps the session alive
            if self._writer:
                self._writer.write(raw)
            return
        if frame.tcp_function != TCP_TRANSLATED_DATA or frame.function is None:
            return
        fut = self._pending.get((frame.function, frame.register))
        if fut and not fut.done():
            fut.set_result(frame)

    async def _request(self, packet: bytes, function: int, register: int) -> Frame:
        last_err: Exception | None = None
        async with self._lock:
            for attempt in range(self.retries + 1):
                try:
                    await self.connect()
                    fut: asyncio.Future[Frame] = asyncio.get_running_loop().create_future()
                    self._pending[(function, register)] = fut
                    assert self._writer is not None
                    self._writer.write(packet)
                    await self._writer.drain()
                    frame = await asyncio.wait_for(fut, self.timeout)
                except (OSError, asyncio.TimeoutError, LuxError) as err:
                    last_err = err
                    _LOGGER.debug(
                        "Request fn=%s reg=%s failed (attempt %s): %r",
                        function, register, attempt + 1, err,
                    )
                    if not isinstance(err, asyncio.TimeoutError):
                        await self._drop_connection()
                    continue
                finally:
                    self._pending.pop((function, register), None)
                if frame.exception:
                    raise LuxError(
                        f"Inverter rejected request fn={function} register={register}"
                    )
                return frame
        raise LuxError(f"No reply from inverter: {last_err!r}")

    async def read_input(self, register: int, count: int) -> dict[int, int]:
        packet = build_read(
            self.dongle_serial, self.inverter_serial, FUNC_READ_INPUT, register, count
        )
        return (await self._request(packet, FUNC_READ_INPUT, register)).values

    async def read_hold(self, register: int, count: int) -> dict[int, int]:
        packet = build_read(
            self.dongle_serial, self.inverter_serial, FUNC_READ_HOLD, register, count
        )
        return (await self._request(packet, FUNC_READ_HOLD, register)).values

    async def write_hold(self, register: int, value: int) -> int:
        packet = build_write_single(
            self.dongle_serial, self.inverter_serial, register, value
        )
        frame = await self._request(packet, FUNC_WRITE_SINGLE, register)
        return frame.values.get(register, value)

    async def write_hold_multi(self, register: int, values: list[int]) -> None:
        packet = build_write_multi(
            self.dongle_serial, self.inverter_serial, register, values
        )
        await self._request(packet, FUNC_WRITE_MULTI, register)
