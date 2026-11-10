"""Numbers (percent holding registers) for the LuxPower LXP 3600 ACS."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    REG_AC_CHARGE_RATE,
    REG_AC_CHARGE_SOC_LIMIT,
    REG_CHARGE_PRIORITY_RATE,
    REG_CHARGE_PRIORITY_SOC_LIMIT,
    REG_CHARGE_RATE,
    REG_DISCHARGE_CUTOFF_SOC,
    REG_DISCHARGE_RATE,
    REG_EPS_DISCHARGE_CUTOFF_SOC,
    REG_FEED_IN_GRID_RATE,
    REG_FORCED_DISCHARGE_RATE,
    REG_FORCED_DISCHARGE_SOC_LIMIT,
)
from .coordinator import LuxConfigEntry
from .entity import LuxEntity


@dataclass(frozen=True, kw_only=True)
class LuxNumberDescription(NumberEntityDescription):
    register: int
    native_min_value: float = 0
    native_max_value: float = 100
    native_step: float = 1
    native_unit_of_measurement: str | None = PERCENTAGE
    mode: NumberMode = NumberMode.BOX
    entity_category: EntityCategory | None = EntityCategory.CONFIG


NUMBERS = (
    LuxNumberDescription(key="charge_rate", name="System charge rate", register=REG_CHARGE_RATE),
    LuxNumberDescription(key="discharge_rate", name="System discharge rate", register=REG_DISCHARGE_RATE),
    LuxNumberDescription(key="ac_charge_rate", name="AC charge rate", register=REG_AC_CHARGE_RATE),
    LuxNumberDescription(key="ac_charge_soc_limit", name="AC charge SOC limit", register=REG_AC_CHARGE_SOC_LIMIT),
    LuxNumberDescription(key="charge_priority_rate", name="Charge priority rate", register=REG_CHARGE_PRIORITY_RATE),
    LuxNumberDescription(key="charge_priority_soc_limit", name="Charge priority SOC limit", register=REG_CHARGE_PRIORITY_SOC_LIMIT),
    LuxNumberDescription(key="forced_discharge_rate", name="Forced discharge rate", register=REG_FORCED_DISCHARGE_RATE),
    LuxNumberDescription(key="forced_discharge_soc_limit", name="Forced discharge SOC limit", register=REG_FORCED_DISCHARGE_SOC_LIMIT),
    LuxNumberDescription(key="feed_in_grid_rate", name="Feed-in grid power limit", register=REG_FEED_IN_GRID_RATE),
    LuxNumberDescription(key="discharge_cutoff_soc", name="Discharge cut-off SOC (on-grid)", register=REG_DISCHARGE_CUTOFF_SOC),
    LuxNumberDescription(key="eps_discharge_cutoff_soc", name="Discharge cut-off SOC (EPS)", register=REG_EPS_DISCHARGE_CUTOFF_SOC),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(LuxNumber(coordinator, d) for d in NUMBERS)


class LuxNumber(LuxEntity, NumberEntity):
    entity_description: LuxNumberDescription

    @property
    def native_value(self) -> float | None:
        return self.coordinator.hold(self.entity_description.register)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write(self.entity_description.register, int(value))
