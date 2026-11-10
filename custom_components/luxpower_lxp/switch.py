"""Switches (bits of holding register 21) for the LuxPower LXP 3600 ACS."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    BIT_AC_CHARGE,
    BIT_CHARGE_PRIORITY,
    BIT_EPS,
    BIT_FEED_IN_GRID,
    BIT_FORCED_DISCHARGE,
    BIT_POWER_ON,
    REG_FUNCTION,
)
from .coordinator import LuxConfigEntry
from .entity import LuxEntity


@dataclass(frozen=True, kw_only=True)
class LuxSwitchDescription(SwitchEntityDescription):
    register: int = REG_FUNCTION
    bit: int


SWITCHES = (
    LuxSwitchDescription(key="ac_charge", name="AC charge", bit=BIT_AC_CHARGE, icon="mdi:battery-charging"),
    LuxSwitchDescription(key="forced_discharge", name="Forced discharge", bit=BIT_FORCED_DISCHARGE, icon="mdi:battery-arrow-down"),
    LuxSwitchDescription(key="charge_priority", name="Charge priority", bit=BIT_CHARGE_PRIORITY, icon="mdi:battery-arrow-up"),
    LuxSwitchDescription(key="feed_in_grid", name="Feed-in to grid", bit=BIT_FEED_IN_GRID, icon="mdi:transmission-tower-import", entity_category=EntityCategory.CONFIG),
    LuxSwitchDescription(key="eps", name="EPS (backup) output", bit=BIT_EPS, icon="mdi:power-plug-battery", entity_category=EntityCategory.CONFIG),
    LuxSwitchDescription(key="power_on", name="Inverter on (off = standby)", bit=BIT_POWER_ON, icon="mdi:power", entity_category=EntityCategory.CONFIG),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(LuxSwitch(coordinator, d) for d in SWITCHES)


class LuxSwitch(LuxEntity, SwitchEntity):
    entity_description: LuxSwitchDescription

    @property
    def is_on(self) -> bool | None:
        value = self.coordinator.hold(self.entity_description.register)
        return None if value is None else bool(value & (1 << self.entity_description.bit))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_bit(
            self.entity_description.register, self.entity_description.bit, True
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_bit(
            self.entity_description.register, self.entity_description.bit, False
        )
