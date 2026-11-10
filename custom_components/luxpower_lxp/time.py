"""Schedule slot times for the LuxPower LXP 3600 ACS.

Each slot register packs the hour in the low byte and the minute in the high byte.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    REG_AC_CHARGE_TIMES,
    REG_CHARGE_PRIORITY_TIMES,
    REG_FORCED_DISCHARGE_TIMES,
)
from .coordinator import LuxConfigEntry
from .entity import LuxEntity


@dataclass(frozen=True, kw_only=True)
class LuxTimeDescription(TimeEntityDescription):
    register: int


def _slots(key: str, name: str, base: int) -> list[LuxTimeDescription]:
    out = []
    for slot in range(3):
        for offset, edge in ((0, "start"), (1, "end")):
            out.append(
                LuxTimeDescription(
                    key=f"{key}_{edge}_{slot + 1}",
                    name=f"{name} {edge} {slot + 1}",
                    register=base + slot * 2 + offset,
                    entity_category=EntityCategory.CONFIG,
                    # Slot 1 is enough for most people; 2 and 3 can be enabled.
                    entity_registry_enabled_default=slot == 0,
                )
            )
    return out


TIMES = (
    *_slots("ac_charge", "AC charge", REG_AC_CHARGE_TIMES),
    *_slots("charge_priority", "Charge priority", REG_CHARGE_PRIORITY_TIMES),
    *_slots("forced_discharge", "Forced discharge", REG_FORCED_DISCHARGE_TIMES),
)


def decode_time(value: int | None) -> time | None:
    if value is None:
        return None
    hour, minute = value & 0xFF, value >> 8
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def encode_time(value: time) -> int:
    return value.hour | (value.minute << 8)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(LuxTime(coordinator, d) for d in TIMES)


class LuxTime(LuxEntity, TimeEntity):
    entity_description: LuxTimeDescription

    @property
    def native_value(self) -> time | None:
        return decode_time(self.coordinator.hold(self.entity_description.register))

    async def async_set_value(self, value: time) -> None:
        await self.coordinator.async_write(self.entity_description.register, encode_time(value))
