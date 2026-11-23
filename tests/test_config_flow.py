"""Config/options flow tests, including pre-2024.11 HA compatibility."""
from __future__ import annotations

import asyncio

from custom_components.smhi_local.config_flow import (
    SmhiLocalConfigFlow,
    SmhiLocalOptionsFlow,
)
from custom_components.smhi_local.const import (
    CONF_ENABLE_ICE,
    CONF_ENABLE_WATER,
    CONF_UPDATE_INTERVAL,
    CONF_WARNING_AREA,
    DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL,
)


class Entry:
    def __init__(self, options):
        self.options = options


class ConfigEntries:
    def __init__(self, entry):
        self.entry = entry

    def async_get_entry(self, entry_id):
        return self.entry if entry_id == "entry-1" else None


class Hass:
    def __init__(self, entry):
        self.config = type("Config", (), {"latitude": 58.39, "longitude": 13.84})()
        self.config_entries = ConfigEntries(entry)


def test_user_step_creates_entry_with_sensible_defaults():
    flow = object.__new__(SmhiLocalConfigFlow)
    flow.hass = Hass(Entry({}))

    result = asyncio.run(
        flow.async_step_user(
            {"latitude": 58.3912, "longitude": 13.8451, "name": ""}
        )
    )

    assert result["title"] == DEFAULT_NAME
    assert result["data"]["latitude"] == 58.3912
    assert result["options"][CONF_UPDATE_INTERVAL] == DEFAULT_UPDATE_INTERVAL
    assert result["options"][CONF_WARNING_AREA] == ""
    assert result["options"][CONF_ENABLE_WATER] is False
    assert result["options"][CONF_ENABLE_ICE] is False
    assert flow.unique_id == "smhi_58.391_13.845"


def test_options_flow_reads_entry_on_new_and_old_home_assistant():
    entry = Entry(
        {
            CONF_UPDATE_INTERVAL: 900,
            CONF_WARNING_AREA: "all",
            CONF_ENABLE_WATER: True,
            CONF_ENABLE_ICE: True,
        }
    )

    # HA 2024.11+: OptionsFlow exposes config_entry directly.
    new = object.__new__(SmhiLocalOptionsFlow)
    new.config_entry = entry
    assert new._current_options()[CONF_UPDATE_INTERVAL] == 900

    # HA 2024.8–2024.10: fall back to the flow handler (= config entry id).
    old = object.__new__(SmhiLocalOptionsFlow)
    old.hass = Hass(entry)
    old.handler = "entry-1"
    assert old._current_options()[CONF_WARNING_AREA] == "all"
    assert asyncio.run(old.async_step_init())["step_id"] == "init"

    old.handler = "missing"
    assert old._current_options() == {}
