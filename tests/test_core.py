"""Unit tests for pure SMHI Local helper functions."""
from __future__ import annotations

import datetime as dt
import importlib

import pytest

from custom_components.smhi_local import coordinator as coord_module
from custom_components.smhi_local.const import (
    CACHE_MAX_AGE_MINUTES,
    CLOUD_LOOKAHEAD_MINUTES,
)

UTC = dt.timezone.utc


def iso(offset_minutes: float) -> str:
    return (dt.datetime.now(UTC) + dt.timedelta(minutes=offset_minutes)).isoformat()


def test_normalize_snow1g_entry():
    raw = {
        "time": iso(0),
        "data": {
            "air_temperature": "3.4",
            "Wsymb2": 7,
            "cloud_base_altitude": 9999,
            "unknown": "x",
        },
    }
    result = coord_module._normalize_entry(raw)
    assert result is not None
    assert result["data"]["air_temperature"] == 3.4
    assert result["data"]["symbol_code"] == 7
    assert "cloud_base_altitude" not in result["data"]  # 9999 = missing
    assert result["data"]["unknown"] == "x"


def test_normalize_legacy_entry():
    raw = {
        "validTime": iso(0),
        "parameters": [
            {"name": "t", "values": [1.5]},
            {"name": "Wsymb2", "values": [3]},
            {"name": "pmean", "values": [9999]},
        ],
    }
    result = coord_module._normalize_entry(raw)
    assert result["data"]["air_temperature"] == 1.5
    assert result["data"]["symbol_code"] == 3
    assert "precipitation_amount_mean" not in result["data"]


@pytest.mark.parametrize(
    ("symbol", "night", "expected"),
    [
        (1, False, "sunny"),
        (1, True, "clear-night"),
        (7, False, "fog"),
        (11, False, "lightning-rainy"),
        (12, False, "snowy-rainy"),
        (25, False, "snowy"),
        (99, False, "cloudy"),
    ],
)
def test_symbol_to_condition(symbol, night, expected):
    assert coord_module._symbol_to_condition(symbol, night) == expected


@pytest.mark.parametrize(
    ("degrees", "expected"),
    [
        (0, "Nord"),
        (359, "Nord"),
        (90, "Ost"),
        (180, "Syd"),
        (270, "Väst"),
        (None, "Okänt"),
    ],
)
def test_wind_direction(degrees, expected):
    assert coord_module._wind_direction_sv(degrees) == expected


def test_cloud_altitude_respects_time_window():
    series = [
        {"time": iso(10), "data": {"cloud_base_altitude": 1000}},
        {"time": iso(CLOUD_LOOKAHEAD_MINUTES + 60), "data": {"cloud_base_altitude": 9000}},
    ]
    now_ts = dt.datetime.now(UTC).timestamp()
    assert coord_module._cloud_altitude_from_series(series, "cloud_base_altitude", now_ts) == 1000

    only_far = series[1:]
    assert (
        coord_module._cloud_altitude_from_series(
            only_far, "cloud_base_altitude", now_ts
        )
        is None
    )


def test_point_in_geometry_polygon_with_hole_and_multipolygon():
    square = {
        "type": "Polygon",
        "coordinates": [
            [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
            [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
        ],
    }
    assert coord_module._point_in_geometry(1, 1, square) is True
    assert coord_module._point_in_geometry(5, 5, square) is False  # hole
    assert coord_module._point_in_geometry(20, 20, square) is False

    multi = {
        "type": "MultiPolygon",
        "coordinates": [[[[20, 20], [30, 20], [30, 30], [20, 30], [20, 20]]]],
    }
    assert coord_module._point_in_geometry(25, 25, multi) is True


def test_is_night_uses_forecast_timestamp_not_current_sun_state(monkeypatch):
    """Regression: sun state must be evaluated for the forecast point."""
    sun = importlib.import_module("homeassistant.helpers.sun")
    monkeypatch.setattr(
        sun, "is_up", lambda hass, when: 6 <= when.hour < 21, raising=False
    )
    night = dt.datetime(2026, 11, 23, 23, tzinfo=UTC)
    day = dt.datetime(2026, 11, 23, 12, tzinfo=UTC)
    assert coord_module._is_night(night, object()) is True
    assert coord_module._is_night(day, object()) is False


def test_data_is_stale_uses_last_success_and_ttl():
    fresh = {
        "timeSeries": [{"time": iso(0), "data": {}}],
        "last_success_at": iso(-5),
        "fetched_at": iso(0),
    }
    stale = {
        "timeSeries": [{"time": iso(0), "data": {}}],
        "last_success_at": iso(-(CACHE_MAX_AGE_MINUTES + 10)),
        "fetched_at": iso(0),  # recent poll must not mask old forecast
    }
    assert coord_module._data_is_stale(fresh) is False
    assert coord_module._data_is_stale(stale) is True
    assert coord_module._data_is_stale({"fetched_at": iso(0)}) is True

    age = coord_module._cache_age_minutes(stale)
    assert age is not None and age >= CACHE_MAX_AGE_MINUTES


def local_iso(days_ahead: int, hour: int) -> str:
    """ISO timestamp for a local date/hour (used by day-part tests)."""
    base = dt.datetime.now().astimezone() + dt.timedelta(days=days_ahead)
    return base.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def test_relative_when_sv_uses_morgon_not_formiddag_at_six():
    assert "bitti" in coord_module._relative_when_sv(local_iso(1, 6))
    assert "förmiddag" not in coord_module._relative_when_sv(local_iso(1, 6))
    assert "morgonen" in coord_module._relative_when_sv(local_iso(0, 7))
    assert "förmiddag" in coord_module._relative_when_sv(local_iso(1, 10))
    assert "eftermiddag" in coord_module._relative_when_sv(local_iso(1, 14))
    assert "kväll" in coord_module._relative_when_sv(local_iso(1, 20))
    assert "natt" in coord_module._relative_when_sv(local_iso(1, 3))


def test_precip_event_value_requires_real_rain_not_only_ensemble_mean():
    low_probability = {
        "precipitation_amount_mean": 0.8,
        "precipitation_amount_mean_deterministic": 0.0,
        "precipitation_amount_median": 0.0,
        "probability_of_precipitation": 6,
    }
    assert coord_module._precip_event_value(low_probability) is None

    high_probability = {**low_probability, "probability_of_precipitation": 60}
    assert coord_module._precip_event_value(high_probability) == 0.8

    deterministic = {**low_probability, "precipitation_amount_mean_deterministic": 0.3}
    assert coord_module._precip_event_value(deterministic) == 0.3


def test_precip_period_text_ignores_low_probability_drizzle():
    now_ts = dt.datetime.now(UTC).timestamp()
    low_probability = {
        "precipitation_amount_mean": 0.8,
        "precipitation_amount_mean_deterministic": 0.0,
        "precipitation_amount_median": 0.0,
        "probability_of_precipitation": 6,
    }
    series = [
        {"time": iso(60), "data": low_probability},
        {"time": iso(120), "data": low_probability},
        {"time": iso(180), "data": low_probability},
    ]
    assert coord_module._precip_period_text(series, now_ts) == "Ingen nederbörd"


def test_precip_period_text_stops_at_first_dry_point():
    now_ts = dt.datetime.now(UTC).timestamp()
    wet = {"precipitation_amount_mean_deterministic": 0.3}
    series = [
        {"time": iso(60), "data": wet},
        {"time": iso(120), "data": wet},
        {"time": iso(180), "data": {}},  # dry → event ends
        {"time": iso(240), "data": wet},  # must not extend the previous event
    ]
    text = coord_module._precip_period_text(series, now_ts)
    times = [
        coord_module.dt_util.as_local(
            coord_module.dt_util.parse_datetime(e["time"])
        ).strftime("%H:%M")
        for e in series
    ]
    assert times[0] in text
    assert times[1] in text
    assert times[3] not in text
