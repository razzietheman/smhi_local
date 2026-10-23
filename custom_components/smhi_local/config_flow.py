"""Config flow for SMHI Local."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_UPDATE_INTERVAL,
    CONF_WARNING_AREA,
    DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    WARNING_AREA_ALL,
    guess_county,
)


class SmhiLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manual lat/lon or use home zone defaults."""
        errors: dict[str, str] = {}

        hass_lat = self.hass.config.latitude
        hass_lon = self.hass.config.longitude

        if user_input is not None:
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]
            name = user_input.get(CONF_NAME) or DEFAULT_NAME

            await self.async_set_unique_id(f"smhi_{round(lat, 3)}_{round(lon, 3)}")
            self._abort_if_unique_id_configured()

            auto_area = guess_county(float(lat), float(lon)) or ""
            return self.async_create_entry(
                title=name,
                data={
                    CONF_NAME: name,
                    CONF_LATITUDE: lat,
                    CONF_LONGITUDE: lon,
                },
                options={
                    CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                    CONF_WARNING_AREA: auto_area,
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Required(CONF_LATITUDE, default=hass_lat): cv.latitude,
                    vol.Required(CONF_LONGITUDE, default=hass_lon): cv.longitude,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Options flow."""
        return SmhiLocalOptionsFlow()


class SmhiLocalOptionsFlow(config_entries.OptionsFlow):
    """Handle options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options
        data = self.config_entry.data
        auto = guess_county(
            float(data.get(CONF_LATITUDE, 0)),
            float(data.get(CONF_LONGITUDE, 0)),
        ) or ""
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL,
                        default=current.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=60, max=3600)),
                    vol.Optional(
                        CONF_WARNING_AREA,
                        default=current.get(CONF_WARNING_AREA, auto),
                    ): str,
                }
            ),
        )
