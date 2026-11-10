"""Polling coordinator for the LuxPower inverter."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import LuxClient, LuxError
from .const import DOMAIN, HOLD_BLOCKS, INPUT_BLOCKS, REG_TIME

_LOGGER = logging.getLogger(__name__)

type LuxConfigEntry = ConfigEntry[LuxCoordinator]


class LuxCoordinator(DataUpdateCoordinator[dict[str, dict[int, int]]]):
    """Reads input and holding registers on a fixed interval."""

    config_entry: LuxConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: LuxConfigEntry,
        client: LuxClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self._input: dict[int, int] = {}
        self._hold: dict[int, int] = {}

    async def _async_update_data(self) -> dict[str, dict[int, int]]:
        try:
            for start, count in INPUT_BLOCKS:
                self._input.update(await self.client.read_input(start, count))
        except LuxError as err:
            raise UpdateFailed(str(err)) from err

        # Settings change rarely; keep the last known values if a block fails.
        for start, count in HOLD_BLOCKS:
            try:
                self._hold.update(await self.client.read_hold(start, count))
            except LuxError as err:
                _LOGGER.debug("Holding block %s read failed: %s", start, err)

        return {"input": dict(self._input), "hold": dict(self._hold)}

    # ---- helpers for entities -------------------------------------------------
    def input(self, reg: int) -> int | None:
        return self.data["input"].get(reg) if self.data else None

    def hold(self, reg: int) -> int | None:
        return self.data["hold"].get(reg) if self.data else None

    def _store_hold(self, values: dict[int, int]) -> None:
        self._hold.update(values)
        if self.data is not None:
            self.async_set_updated_data({"input": dict(self._input), "hold": dict(self._hold)})

    async def async_write(self, register: int, value: int) -> None:
        try:
            confirmed = await self.client.write_hold(register, value)
        except LuxError as err:
            raise HomeAssistantError(f"Writing register {register} failed: {err}") from err
        self._store_hold({register: confirmed})

    async def async_set_bit(self, register: int, bit: int, on: bool) -> None:
        """Read-modify-write a single bit so other flags are never clobbered."""
        try:
            current = (await self.client.read_hold(register, 1))[register]
        except (LuxError, KeyError) as err:
            raise HomeAssistantError(f"Reading register {register} failed: {err}") from err
        new = current | (1 << bit) if on else current & ~(1 << bit)
        if new != current:
            await self.async_write(register, new)
        else:
            self._store_hold({register: current})

    async def async_sync_time(self) -> None:
        now: datetime = dt_util.now()
        values = [
            (now.year - 2000) | (now.month << 8),
            now.day | (now.hour << 8),
            now.minute | (now.second << 8),
        ]
        try:
            await self.client.write_hold_multi(REG_TIME, values)
        except LuxError as err:
            raise HomeAssistantError(f"Setting inverter time failed: {err}") from err
        self._store_hold(dict(zip(range(REG_TIME, REG_TIME + 3), values)))

