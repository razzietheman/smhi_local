"""Coordinator behaviour: caches, bundles, filtering and station handling."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging

from custom_components.smhi_local.const import (
    CACHE_MAX_AGE_MINUTES,
    DATA_STATUS_CURRENT,
    DATA_STATUS_NONE,
    DATA_STATUS_STALE,
)
from custom_components.smhi_local.coordinator import (
    SmhiLocalCoordinator,
    _obs_nearest_station,
)

UTC = dt.timezone.utc


def iso(offset_minutes: float = 0) -> str:
    return (dt.datetime.now(UTC) + dt.timedelta(minutes=offset_minutes)).isoformat()


class FakeEntry:
    def __init__(self, options=None, data=None):
        self.entry_id = "test-entry"
        self.options = options or {}
        self.data = data or {"latitude": 58.39, "longitude": 13.84}


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def json(self):
        return self.payload

    async def text(self):
        return ""


class FakeSession:
    def __init__(self, snow=None, fire=None, warnings=None):
        self.snow = snow or FakeResponse(SNOW_PAYLOAD)
        self.fire = fire or FakeResponse(FIRE_PAYLOAD)
        self.warnings = warnings or FakeResponse(WARNINGS_PAYLOAD)
        self.urls = []

    def get(self, url, timeout=None):
        self.urls.append(url)
        if "fwif1g" in url:
            return self.fire
        if "warnings" in url:
            return self.warnings
        return self.snow


SNOW_PAYLOAD = {
    "createdTime": iso(-120),
    "referenceTime": iso(-120),
    "geometry": {"type": "Point", "coordinates": [13.84, 58.39]},
    "timeSeries": [
        {
            "time": iso(-60),
            "data": {
                "air_temperature": 2.0,
                "symbol_code": 4,
                "wind_from_direction": 90,
                "cloud_base_altitude": 1000,
            },
        },
        {
            "time": iso(60),
            "data": {
                "air_temperature": 5.0,
                "symbol_code": 1,
                "wind_from_direction": 180,
                "cloud_base_altitude": 1200,
            },
        },
    ],
}

FIRE_PAYLOAD = {
    "approvedTime": iso(-60),
    "timeSeries": [
        {
            "validTime": iso(0),
            "parameters": [
                {"name": "fwiindex", "values": [2]},
                {"name": "grassfire", "values": [1]},
            ],
        }
    ],
}

WARNINGS_PAYLOAD = []


def set_data(coord, data):
    """Replace coordinator data and invalidate its precomputed bundles."""
    coord.data = {key: value for key, value in data.items() if key != "_bundles"}


def make_coordinator(session=None, options=None):
    coord = object.__new__(SmhiLocalCoordinator)
    coord.hass = object()
    coord.entry = FakeEntry(options)
    coord.session = session
    coord.data = None
    coord.last_update_success = True
    coord._last_good = None
    coord._last_cloud_base = None
    coord._last_cloud_top = None

    async def no_save():
        return None

    coord.async_save_cache = no_save
    return coord


def previous_cache():
    return {
        "timeSeries": SNOW_PAYLOAD["timeSeries"],
        "fetched_at": iso(-(CACHE_MAX_AGE_MINUTES + 10)),
        "last_success_at": iso(-(CACHE_MAX_AGE_MINUTES + 10)),
        "fire": {"data": {"fwiindex": 5}},
        "warnings": [{"event": {"sv": "Gammal varning"}}],
        "last_fire_success_at": iso(-(CACHE_MAX_AGE_MINUTES + 10)),
        "last_warnings_success_at": iso(-(CACHE_MAX_AGE_MINUTES + 10)),
    }


def test_update_preserves_failed_layers_from_previous_cache():
    session = FakeSession(
        fire=FakeResponse({}, status=500),
        warnings=FakeResponse([], status=200),
    )
    prev = previous_cache()
    coord = make_coordinator(session)
    coord._last_good = prev

    result = asyncio.run(coord._async_update_data())

    assert result["fire"] == prev["fire"]
    assert result["warnings"] == []
    assert result["last_success_at"] == result["fetched_at"]
    assert result["last_fire_success_at"] == prev["last_fire_success_at"]
    # Bundles are computed exactly once per update.
    assert "_bundles" in result
    assert coord.current_bundle() is result["_bundles"]["current"]


def test_update_keeps_forecast_success_time_when_forecast_fails():
    prev = previous_cache()
    session = FakeSession(
        snow=FakeResponse({}, status=503),
        warnings=FakeResponse({}, status=500),
    )
    coord = make_coordinator(session)
    coord._last_good = prev

    result = asyncio.run(coord._async_update_data())

    assert result["last_success_at"] == prev["last_success_at"]
    assert result["fetched_at"] != prev["fetched_at"]
    assert result["fire"]["data"]["fwiindex"] == 2  # fresh fire data
    assert result["warnings"] == prev["warnings"]  # failed poll → preserved
    assert coord.status_bundle()["data_status"] == DATA_STATUS_STALE


def test_status_bundle_reports_current_stale_and_missing():
    coord = make_coordinator()
    set_data(
        coord,
        {
            "timeSeries": SNOW_PAYLOAD["timeSeries"],
            "last_success_at": iso(-5),
            "fetched_at": iso(0),
        },
    )
    assert coord.status_bundle()["data_status"] == DATA_STATUS_CURRENT
    assert coord.data_is_stale is False

    set_data(
        coord,
        {
            "timeSeries": SNOW_PAYLOAD["timeSeries"],
            "last_success_at": iso(-(CACHE_MAX_AGE_MINUTES + 5)),
            "fetched_at": iso(0),
        },
    )
    assert coord.status_bundle()["data_status"] == DATA_STATUS_STALE
    assert coord.data_is_stale is True

    set_data(coord, {"timeSeries": []})
    assert coord.status_bundle()["data_status"] == DATA_STATUS_NONE


def test_warning_name_filter_is_or_with_geometry():
    inside = {
        "type": "Polygon",
        "coordinates": [[[13, 58], [15, 58], [15, 59], [13, 59], [13, 58]]],
    }
    far = {
        "type": "Polygon",
        "coordinates": [[[20, 60], [21, 60], [21, 61], [20, 61], [20, 60]]],
    }

    def warning(name, geom):
        return {
            "event": {"sv": "Testvarning"},
            "warningAreas": [
                {
                    "areaName": {"sv": name},
                    "area": {"geometry": geom},
                    "warningLevel": {"code": "YELLOW", "sv": "Gul"},
                }
            ],
        }

    warnings = [
        warning("Stockholms län", far),  # name match only
        warning("Västra Götalands län", inside),  # geometry match only
        warning("Skåne län", far),  # no match
    ]
    coord = make_coordinator(options={"warning_area": "stockholm"})
    set_data(coord, {"warnings": warnings})
    assert coord.warnings_bundle()["warnings_count"] == 2  # name OR geometry

    coord.entry.options = {"warning_area": ""}
    set_data(coord, {"warnings": warnings})
    assert coord.warnings_bundle()["warnings_count"] == 1  # geometry only

    coord.entry.options = {"warning_area": "all"}
    set_data(coord, {"warnings": warnings})
    assert coord.warnings_bundle()["warnings_count"] == 3


def test_manual_station_id_is_not_silently_ignored(caplog):
    session = FakeSession(snow=FakeResponse({"station": []}))
    with caplog.at_level(logging.WARNING):
        station = asyncio.run(
            _obs_nearest_station(
                session, "https://example.test", 3, 58.39, 13.84, "MISSING"
            )
        )
    assert station is None
    assert "MISSING" in caplog.text
