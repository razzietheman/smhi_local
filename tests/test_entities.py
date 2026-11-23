"""Entity-level regression tests (forecast window, freshness availability)."""
from __future__ import annotations

import asyncio
import datetime as dt

from custom_components.smhi_local.const import SENSOR_TYPES, DATA_STATUS_SENSOR_TYPES
from custom_components.smhi_local.sensor import SmhiFieldSensor, SmhiStatusSensor
from custom_components.smhi_local.weather import SmhiWeatherEntity

UTC = dt.timezone.utc


def point(minutes_from_now: float, temp: float) -> dict:
    stamp = dt.datetime.now(UTC) + dt.timedelta(minutes=minutes_from_now)
    return {
        "time": stamp.isoformat(),
        "data": {
            "air_temperature": temp,
            "symbol_code": 2,
            "precipitation_amount_mean": 0.0,
        },
    }


class Coord:
    def __init__(self, series):
        self.data = {"timeSeries": series}
        self.last_update_success = True
        self.stale = False

    @property
    def source_data(self):
        return self.data

    @property
    def data_is_stale(self):
        return self.stale

    def current_bundle(self):
        return {}

    def status_bundle(self):
        return {"data_status": "Aktuell"}


def test_daily_and_hourly_forecasts_skip_past_points():
    series = [
        point(-24 * 60, 1.0),  # yesterday – must be excluded
        point(-120, 2.0),  # two hours ago – must be excluded
        point(60, 12.0),  # today
        point(24 * 60, 14.0),  # tomorrow
    ]
    entity = object.__new__(SmhiWeatherEntity)
    entity.coordinator = Coord(series)
    entity.hass = object()

    hourly = asyncio.run(entity.async_forecast_hourly())
    daily = asyncio.run(entity.async_forecast_daily())

    assert len(hourly) == 2
    assert len(daily) == 2
    assert all(entry["datetime"] != series[0]["time"] for entry in daily)


def test_stale_data_hides_regular_entities_but_not_status_sensor():
    coord = Coord([point(0, 5.0)])
    sensor = object.__new__(SmhiFieldSensor)
    sensor.coordinator = coord
    status = object.__new__(SmhiStatusSensor)
    status.coordinator = coord

    assert sensor.available is True
    assert status.available is True

    coord.stale = True
    assert sensor.available is False
    assert status.available is True


def test_status_sensor_has_unique_id_and_name():
    coord = Coord([])
    entry = type("Entry", (), {"entry_id": "abc"})()
    desc = DATA_STATUS_SENSOR_TYPES[0]
    sensor = SmhiStatusSensor(coord, entry, "SMHI", desc)
    assert sensor._attr_unique_id == "abc_data_status"
    assert sensor._attr_name == "Datastatus"
    assert SENSOR_TYPES  # sanity: existing sensors still defined
