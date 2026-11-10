"""LuxPower LXP 3600 ACS local integration (WiFi dongle, TCP port 8000)."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .client import LuxClient
from .const import (
    CONF_DONGLE_SERIAL,
    CONF_INVERTER_SERIAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import LuxConfigEntry, LuxCoordinator

PLATFORMS = [
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_WRITE_REGISTER = "write_holding_register"
WRITE_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Required("register"): vol.All(vol.Coerce(int), vol.Range(min=0, max=0xFFFF)),
        vol.Required("value"): vol.All(vol.Coerce(int), vol.Range(min=0, max=0xFFFF)),
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def write_register(call: ServiceCall) -> None:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        entry_id = call.data.get("config_entry_id")
        if entry_id:
            entries = [e for e in entries if e.entry_id == entry_id]
        if len(entries) != 1:
            raise ServiceValidationError(
                "Specify config_entry_id: zero or multiple LuxPower inverters loaded"
            )
        coordinator: LuxCoordinator = entries[0].runtime_data
        await coordinator.async_write(call.data["register"], call.data["value"])

    hass.services.async_register(
        DOMAIN, SERVICE_WRITE_REGISTER, write_register, schema=WRITE_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LuxConfigEntry) -> bool:
    client = LuxClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_DONGLE_SERIAL],
        entry.data[CONF_INVERTER_SERIAL],
    )
    coordinator = LuxCoordinator(
        hass,
        entry,
        client,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.close()
        raise
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: LuxConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: LuxConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.close()
    return unloaded
