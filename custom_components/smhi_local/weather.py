"""Weather entity for SMHI Local – current + hourly + daily forecast."""
from __future__ import annotations

from typing import Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_NAME, DEFAULT_NAME, DOMAIN
from .coordinator import SmhiLocalCoordinator, _is_night, _symbol_to_condition


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up weather entity."""
    coordinator: SmhiLocalCoordinator = entry.runtime_data
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    async_add_entities([SmhiWeatherEntity(coordinator, entry, name)])


class SmhiWeatherEntity(CoordinatorEntity[SmhiLocalCoordinator], WeatherEntity):
    """SMHI weather with hourly and daily forecasts."""

    _attr_has_entity_name = True
    _attr_name = None  # device name only → weather.smhi / weather.smhi_skovde via title
    _attr_attribution = "SMHI Open Data Powered by Rasmus"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_native_precipitation_unit = "mm"
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_HOURLY | WeatherEntityFeature.FORECAST_DAILY
    )

    def __init__(
        self,
        coordinator: SmhiLocalCoordinator,
        entry: ConfigEntry,
        device_name: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_weather"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=device_name,
            manufacturer="Rasmus",
            model="SMHI SNOW1g · lokal prognos",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://opendata.smhi.se",
        )

    def _bundle(self) -> dict[str, Any]:
        return self.coordinator.current_bundle()

    @property
    def condition(self) -> str | None:
        return self._bundle().get("condition") or "cloudy"

    @property
    def native_temperature(self) -> float | None:
        v = self._bundle().get("air_temperature")
        return float(v) if v is not None else None

    @property
    def native_pressure(self) -> float | None:
        v = self._bundle().get("air_pressure_at_mean_sea_level")
        return float(v) if v is not None else None

    @property
    def humidity(self) -> float | None:
        v = self._bundle().get("relative_humidity")
        return float(v) if v is not None else None

    @property
    def native_wind_speed(self) -> float | None:
        v = self._bundle().get("wind_speed")
        return float(v) if v is not None else None

    @property
    def wind_bearing(self) -> float | None:
        v = self._bundle().get("wind_from_direction")
        return float(v) if v is not None else None

    @property
    def native_visibility(self) -> float | None:
        v = self._bundle().get("visibility_in_air")
        return float(v) if v is not None else None

    @property
    def native_wind_gust_speed(self) -> float | None:
        v = self._bundle().get("wind_speed_of_gust")
        return float(v) if v is not None else None

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Hourly forecast from timeSeries (from ~now)."""
        data = self.coordinator.data or {}
        series = data.get("timeSeries") or []
        if not series:
            return None

        now_ts = dt_util.now().timestamp()
        out: list[Forecast] = []

        for e in series:
            if not e or "time" not in e or "data" not in e:
                continue
            dt = dt_util.parse_datetime(e["time"])
            if dt is None:
                continue
            if dt.timestamp() < now_ts - 1800:
                continue

            d = e["data"]
            symbol = int(d.get("symbol_code") or 6)
            night = _is_night(dt, self.hass)
            cond = _symbol_to_condition(symbol, night)

            out.append(
                Forecast(
                    datetime=e["time"],
                    condition=cond,
                    native_temperature=_f(d.get("air_temperature")),
                    native_precipitation=_f(d.get("precipitation_amount_mean")),
                    precipitation_probability=_i(d.get("probability_of_precipitation")),
                    native_wind_speed=_f(d.get("wind_speed")),
                    wind_bearing=_f(d.get("wind_from_direction")),
                    humidity=_f(d.get("relative_humidity")),
                    native_pressure=_f(d.get("air_pressure_at_mean_sea_level")),
                    native_wind_gust_speed=_f(d.get("wind_speed_of_gust")),
                )
            )
        return out

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Daily min/max aggregated from hourly points."""
        data = self.coordinator.data or {}
        series = data.get("timeSeries") or []
        if not series:
            return None

        days: dict[str, dict[str, Any]] = {}
        for e in series:
            if not e or "time" not in e or "data" not in e:
                continue
            dt = dt_util.parse_datetime(e["time"])
            if dt is None:
                continue
            local = dt_util.as_local(dt)
            key = local.date().isoformat()
            temp = _f(e["data"].get("air_temperature"))
            if temp is None:
                continue
            if key not in days:
                days[key] = {
                    "min": temp,
                    "max": temp,
                    "sym": e["data"].get("symbol_code") or 6,
                    "time": e["time"],
                    "precip": _f(e["data"].get("precipitation_amount_mean")) or 0.0,
                    "prob": _i(e["data"].get("probability_of_precipitation")) or 0,
                    "wind": _f(e["data"].get("wind_speed")),
                    "bearing": _f(e["data"].get("wind_from_direction")),
                }
            else:
                d = days[key]
                d["min"] = min(d["min"], temp)
                d["max"] = max(d["max"], temp)
                # accumulate precip roughly
                p = _f(e["data"].get("precipitation_amount_mean")) or 0.0
                d["precip"] = (d["precip"] or 0) + p

        out: list[Forecast] = []
        for key in sorted(days.keys()):
            d = days[key]
            symbol = int(d["sym"] or 6)
            # daily: prefer day-style condition (not night)
            cond = _symbol_to_condition(symbol, night=False)
            out.append(
                Forecast(
                    datetime=d["time"],
                    condition=cond,
                    native_temperature=d["max"],
                    native_templow=d["min"],
                    native_precipitation=round(d["precip"], 1) if d["precip"] else 0.0,
                    precipitation_probability=d["prob"],
                    native_wind_speed=d["wind"],
                    wind_bearing=d["bearing"],
                )
            )
        return out


def _f(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _i(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
