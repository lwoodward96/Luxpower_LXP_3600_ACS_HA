"""Buttons for the LuxPower LXP 3600 ACS."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LuxConfigEntry
from .entity import LuxEntity

SYNC_TIME = ButtonEntityDescription(
    key="sync_time",
    name="Sync inverter clock",
    icon="mdi:clock-check-outline",
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LuxSyncTimeButton(entry.runtime_data, SYNC_TIME)])


class LuxSyncTimeButton(LuxEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self.coordinator.async_sync_time()
