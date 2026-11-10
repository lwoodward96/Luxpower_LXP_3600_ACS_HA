"""Config flow for the LuxPower LXP 3600 ACS."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import callback

from .client import LuxClient, LuxConnectionError, LuxError
from .const import (
    CONF_DONGLE_SERIAL,
    CONF_INVERTER_SERIAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_DONGLE_SERIAL): str,
        vol.Required(CONF_INVERTER_SERIAL): str,
    }
)


class LuxConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"seen_dongle": "-", "seen_inverter": "-"}
        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip()
            for key in (CONF_DONGLE_SERIAL, CONF_INVERTER_SERIAL):
                user_input[key] = user_input[key].strip()
                if len(user_input[key]) != 10 or not user_input[key].isascii():
                    errors[key] = "invalid_serial"

            if not errors:
                await self.async_set_unique_id(user_input[CONF_INVERTER_SERIAL])
                self._abort_if_unique_id_configured()
                client = LuxClient(
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                    user_input[CONF_DONGLE_SERIAL],
                    user_input[CONF_INVERTER_SERIAL],
                )
                try:
                    await client.read_input(0, 40)
                except LuxConnectionError:
                    errors["base"] = "cannot_connect"
                except LuxError:
                    seen_d, seen_i = client.seen_dongle_serial, client.seen_inverter_serial
                    placeholders = {
                        "seen_dongle": seen_d or "-",
                        "seen_inverter": seen_i or "-",
                    }
                    if (seen_d and seen_d != user_input[CONF_DONGLE_SERIAL]) or (
                        seen_i and seen_i != user_input[CONF_INVERTER_SERIAL]
                    ):
                        errors["base"] = "serial_mismatch"
                    else:
                        errors["base"] = "no_reply"
                finally:
                    await client.close()

            if not errors:
                return self.async_create_entry(
                    title=f"LXP 3600 ACS {user_input[CONF_INVERTER_SERIAL]}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
            description_placeholders=placeholders,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return LuxOptionsFlow()


class LuxOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        int, vol.Range(min=MIN_SCAN_INTERVAL, max=3600)
                    )
                }
            ),
        )
