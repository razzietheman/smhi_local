"""Test bootstrap.

The project declares pytest-homeassistant-custom-component, but the pure unit
tests here also run without Home Assistant installed: minimal stubs are added
to sys.modules only when HA is unavailable. Nothing is stubbed in a real HA
test environment.
"""
from __future__ import annotations

import datetime as dt
import sys
import types
from typing import Generic, TypeVar
from zoneinfo import ZoneInfo

_T = TypeVar("_T")

UTC = dt.timezone.utc


def _module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules.setdefault(name, mod)
    return mod


try:
    import homeassistant.util.dt  # noqa: F401

    HAS_HA = True
except Exception:  # pragma: no cover - only used outside a HA environment
    HAS_HA = False

    # --- homeassistant.util.dt ---
    def parse_datetime(value):
        if not value:
            return None
        if isinstance(value, dt.datetime):
            return value
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            return None

    def as_utc(value):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def as_local(value):
        return value.astimezone()

    dt_util = _module(
        "homeassistant.util.dt",
        parse_datetime=parse_datetime,
        as_utc=as_utc,
        as_local=as_local,
        utcnow=lambda: dt.datetime.now(UTC),
        now=lambda: dt.datetime.now(),
        utc_from_timestamp=lambda ts: dt.datetime.fromtimestamp(ts, UTC),
    )
    util = _module("homeassistant.util")
    util.dt = dt_util

    # --- core modules ---
    _module("homeassistant")
    _module(
        "homeassistant.core",
        HomeAssistant=object,
        callback=lambda func: func,
    )
    class ConfigFlow:
        def __init_subclass__(cls, domain=None, **kwargs):
            super().__init_subclass__(**kwargs)
            cls.domain = domain

        async def async_set_unique_id(self, unique_id):
            self.unique_id = unique_id

        def _abort_if_unique_id_configured(self):
            return None

        def async_show_form(self, **kwargs):
            return kwargs

        def async_create_entry(self, **kwargs):
            return kwargs

    class OptionsFlow:
        def async_show_form(self, **kwargs):
            return kwargs

        def async_create_entry(self, **kwargs):
            return kwargs

    _module(
        "homeassistant.config_entries",
        ConfigEntry=object,
        ConfigFlow=ConfigFlow,
        OptionsFlow=OptionsFlow,
    )
    _module("homeassistant.data_entry_flow", FlowResult=dict)

    class _CV:
        latitude = float
        longitude = float

    _module("homeassistant.helpers.config_validation", cv=_CV())
    _module("homeassistant.exceptions", ConfigEntryNotReady=Exception)

    class Platform:
        SENSOR = "sensor"
        WEATHER = "weather"

    class UnitOfTemperature:
        CELSIUS = "°C"

    class UnitOfPressure:
        HPA = "hPa"

    class UnitOfSpeed:
        METERS_PER_SECOND = "m/s"

    class UnitOfLength:
        KILOMETERS = "km"

    _module(
        "homeassistant.const",
        Platform=Platform,
        UnitOfTemperature=UnitOfTemperature,
        UnitOfPressure=UnitOfPressure,
        UnitOfSpeed=UnitOfSpeed,
        UnitOfLength=UnitOfLength,
        CONF_LATITUDE="latitude",
        CONF_LONGITUDE="longitude",
        CONF_NAME="name",
    )

    _module(
        "homeassistant.helpers",
        config_validation=sys.modules["homeassistant.helpers.config_validation"],
    )

    class Store:
        def __init__(self, hass, version, key):
            self.data = None

        async def async_load(self):
            return self.data

        async def async_save(self, data):
            self.data = data

    _module("homeassistant.helpers.storage", Store=Store)

    class UpdateFailed(Exception):
        pass

    class DataUpdateCoordinator(Generic[_T]):
        def __init__(self, hass, logger, *, name, update_interval, config_entry):
            self.hass = hass
            self.data = None
            self.last_update_success = True

    class CoordinatorEntity(Generic[_T]):
        def __init__(self, coordinator):
            self.coordinator = coordinator

        @property
        def available(self) -> bool:
            return bool(getattr(self.coordinator, "last_update_success", True))

    _module(
        "homeassistant.helpers.update_coordinator",
        DataUpdateCoordinator=DataUpdateCoordinator,
        UpdateFailed=UpdateFailed,
        CoordinatorEntity=CoordinatorEntity,
    )
    _module(
        "homeassistant.helpers.aiohttp_client",
        async_get_clientsession=lambda hass: None,
    )

    def is_up(hass, point_in_time=None):
        when = point_in_time or dt.datetime.now(UTC)
        return 6 <= when.hour < 21

    _module("homeassistant.helpers.sun", is_up=is_up)

    class DeviceEntryType:
        SERVICE = "service"

    _module(
        "homeassistant.helpers.device_registry",
        DeviceEntryType=DeviceEntryType,
        DeviceInfo=dict,
    )
    _module("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)

    # --- platforms ---
    components = _module("homeassistant.components")

    class SensorDeviceClass:
        TEMPERATURE = "temperature"
        HUMIDITY = "humidity"
        ATMOSPHERIC_PRESSURE = "pressure"
        WIND_SPEED = "wind_speed"
        DISTANCE = "distance"
        PRECIPITATION_INTENSITY = "precipitation_intensity"
        PRECIPITATION = "precipitation"
        TIMESTAMP = "timestamp"

    class SensorStateClass:
        MEASUREMENT = "measurement"

    _module(
        "homeassistant.components.sensor",
        SensorDeviceClass=SensorDeviceClass,
        SensorStateClass=SensorStateClass,
        SensorEntity=type("SensorEntity", (), {}),
    )

    class Forecast(dict):
        def __init__(self, **kwargs):
            super().__init__(kwargs)

    class WeatherEntityFeature:
        FORECAST_HOURLY = 1
        FORECAST_DAILY = 2

    _module(
        "homeassistant.components.weather",
        Forecast=Forecast,
        WeatherEntity=type("WeatherEntity", (), {}),
        WeatherEntityFeature=WeatherEntityFeature,
    )
    components.sensor = sys.modules["homeassistant.components.sensor"]
    components.weather = sys.modules["homeassistant.components.weather"]
