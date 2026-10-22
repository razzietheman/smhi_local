"""SMHI Local integration – point forecast as sensors (+ later weather)."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .coordinator import SmhiLocalCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.WEATHER]

type SmhiConfigEntry = ConfigEntry[SmhiLocalCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SmhiConfigEntry) -> bool:
    """Set up SMHI Local from a config entry."""
    session = async_get_clientsession(hass)
    coordinator = SmhiLocalCoordinator(hass, entry, session)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as ex:
        raise ConfigEntryNotReady(f"SMHI first refresh failed: {ex}") from ex

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SmhiConfigEntry) -> bool:
    """Unload entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload on options change."""
    await hass.config_entries.async_reload(entry.entry_id)
