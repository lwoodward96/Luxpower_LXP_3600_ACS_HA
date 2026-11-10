"""Base entity for the LuxPower integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_INVERTER_SERIAL, DOMAIN
from .coordinator import LuxCoordinator


class LuxEntity(CoordinatorEntity[LuxCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: LuxCoordinator, description: EntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        serial = coordinator.config_entry.data[CONF_INVERTER_SERIAL]
        self._attr_unique_id = f"{serial}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer="LuxPower",
            model="LXP 3600 ACS",
            name="LuxPower LXP 3600 ACS",
            serial_number=serial,
        )
