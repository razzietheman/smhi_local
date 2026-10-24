"""Sensors for SMHI Local – current fields + derived forecast helpers."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_NAME,
    DEFAULT_NAME,
    DERIVED_SENSOR_TYPES,
    DOMAIN,
    FIRE_SENSOR_TYPES,
    META_SENSOR_TYPES,
    SENSOR_TYPES,
    WARNING_SENSOR_TYPES,
    WATER_SENSOR_TYPES,
    ICE_SENSOR_TYPES,
)
from .coordinator import SmhiLocalCoordinator

_DEVICE_CLASS_MAP = {
    "temperature": SensorDeviceClass.TEMPERATURE,
    "humidity": SensorDeviceClass.HUMIDITY,
    "pressure": SensorDeviceClass.ATMOSPHERIC_PRESSURE,
    "wind_speed": SensorDeviceClass.WIND_SPEED,
    "distance": SensorDeviceClass.DISTANCE,
    "precipitation_intensity": SensorDeviceClass.PRECIPITATION_INTENSITY,
    "precipitation": SensorDeviceClass.PRECIPITATION,
    "timestamp": SensorDeviceClass.TIMESTAMP,
}

_STATE_CLASS_MAP = {
    "measurement": SensorStateClass.MEASUREMENT,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SMHI sensors from a config entry."""
    coordinator: SmhiLocalCoordinator = entry.runtime_data
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    entities: list[SensorEntity] = [
        SmhiFieldSensor(coordinator, entry, name, desc) for desc in SENSOR_TYPES
    ]
    entities.extend(
        SmhiDerivedSensor(coordinator, entry, name, desc)
        for desc in DERIVED_SENSOR_TYPES
    )
    entities.extend(
        SmhiMetaSensor(coordinator, entry, name, desc) for desc in META_SENSOR_TYPES
    )
    entities.extend(
        SmhiFireSensor(coordinator, entry, name, desc) for desc in FIRE_SENSOR_TYPES
    )
    entities.extend(
        SmhiWarningSensor(coordinator, entry, name, desc)
        for desc in WARNING_SENSOR_TYPES
    )
    entities.extend(
        SmhiWaterSensor(coordinator, entry, name, desc)
        for desc in WATER_SENSOR_TYPES
    )
    entities.extend(
        SmhiIceSensor(coordinator, entry, name, desc)
        for desc in ICE_SENSOR_TYPES
    )
    entities.append(SmhiCurrentSensor(coordinator, entry, name))
    async_add_entities(entities)


def _device_info(entry: ConfigEntry, device_name: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=device_name,
        manufacturer="Rasmus",
        model="SMHI SNOW1g · lokal prognos",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://opendata.smhi.se",
    )


class SmhiFieldSensor(CoordinatorEntity[SmhiLocalCoordinator], SensorEntity):
    """Single field from nearest SMHI timeSeries point."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmhiLocalCoordinator,
        entry: ConfigEntry,
        device_name: str,
        desc: dict[str, Any],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._key = desc["key"]
        self._attr_name = desc["name"]
        self._attr_unique_id = f"{entry.entry_id}_{self._key}"
        self._attr_native_unit_of_measurement = desc.get("unit")
        self._attr_icon = desc.get("icon")
        dc = desc.get("device_class")
        self._attr_device_class = _DEVICE_CLASS_MAP.get(dc) if dc else None
        sc = desc.get("state_class")
        self._attr_state_class = _STATE_CLASS_MAP.get(sc) if sc else None
        self._attr_device_info = _device_info(entry, device_name)

    @property
    def native_value(self) -> float | int | str | None:
        """Return field value."""
        bundle = self.coordinator.current_bundle()
        if not bundle or self._key not in bundle:
            return None
        val = bundle[self._key]
        if self._key in ("condition", "condition_sv", "cloud_type", "wind_direction_sv"):
            return val
        if self._key in ("symbol_code",):
            try:
                return int(val)
            except (TypeError, ValueError):
                return val
        try:
            return round(float(val), 1)
        except (TypeError, ValueError):
            return val

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Degrees for wind direction label."""
        if self._key != "wind_direction_sv":
            return {}
        bundle = self.coordinator.current_bundle()
        deg = bundle.get("wind_from_direction")
        try:
            return {"degrees": round(float(deg), 1)} if deg is not None else {}
        except (TypeError, ValueError):
            return {}


class SmhiDerivedSensor(CoordinatorEntity[SmhiLocalCoordinator], SensorEntity):
    """Sensor derived by scanning the full forecast series."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmhiLocalCoordinator,
        entry: ConfigEntry,
        device_name: str,
        desc: dict[str, Any],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._key = desc["key"]
        self._attr_name = desc["name"]
        self._attr_unique_id = f"{entry.entry_id}_{self._key}"
        self._attr_native_unit_of_measurement = desc.get("unit")
        self._attr_icon = desc.get("icon")
        dc = desc.get("device_class")
        self._attr_device_class = _DEVICE_CLASS_MAP.get(dc) if dc else None
        sc = desc.get("state_class")
        self._attr_state_class = _STATE_CLASS_MAP.get(sc) if sc else None
        self._attr_device_info = _device_info(entry, device_name)

    @property
    def native_value(self) -> float | int | str | None:
        """Return derived value."""
        bundle = self.coordinator.derived_bundle()
        val = bundle.get(self._key)
        if val is None:
            return None
        if self._key in ("thunder_risk_text", "next_precip_type", "next_bad_visibility", "next_precip_time", "next_snow_share"):
            return val
        if isinstance(val, float):
            return round(val, 2)
        return val

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Extra context for next-event sensors."""
        if self._key == "next_precip_type":
            b = self.coordinator.derived_bundle()
            return {
                "amount_mm_h": b.get("next_precip_amount"),
                "time": b.get("next_precip_time"),
                "snow_share": b.get("next_snow_share"),
            }
        if self._key == "next_bad_visibility":
            b = self.coordinator.derived_bundle()
            return {"time": b.get("next_bad_visibility_time")}
        return {}


class SmhiCurrentSensor(CoordinatorEntity[SmhiLocalCoordinator], SensorEntity):
    """Summary sensor: state = symbol_code, attributes = all current fields."""

    _attr_has_entity_name = True
    _attr_name = "Current"
    _attr_icon = "mdi:weather-partly-cloudy"

    def __init__(
        self,
        coordinator: SmhiLocalCoordinator,
        entry: ConfigEntry,
        device_name: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_current"
        self._attr_device_info = _device_info(entry, device_name)

    @property
    def native_value(self) -> int | str | None:
        """Symbol code."""
        bundle = self.coordinator.current_bundle()
        if not bundle:
            return None
        return bundle.get("symbol_code")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """All current + key derived fields."""
        bundle = self.coordinator.current_bundle()
        derived = self.coordinator.derived_bundle()
        if not bundle:
            return {}
        return {
            "time": bundle.get("time"),
            "temperature": bundle.get("air_temperature"),
            "humidity": bundle.get("relative_humidity"),
            "pressure": bundle.get("air_pressure_at_mean_sea_level"),
            "wind_speed": bundle.get("wind_speed"),
            "wind_bearing": bundle.get("wind_from_direction"),
            "wind_gust": bundle.get("wind_speed_of_gust"),
            "visibility": bundle.get("visibility_in_air"),
            "precipitation": bundle.get("precipitation_amount_mean"),
            "precipitation_probability": bundle.get("probability_of_precipitation"),
            "condition": bundle.get("condition"),
            "symbol_code": bundle.get("symbol_code"),
            "feels_like": bundle.get("feels_like"),
            "thunder_risk_12h": derived.get("thunder_risk_12h"),
            "precip_next_12h": derived.get("precip_next_12h"),
            "next_precip_type": derived.get("next_precip_type"),
            "next_precip_time": derived.get("next_precip_time"),
        }



class SmhiMetaSensor(CoordinatorEntity[SmhiLocalCoordinator], SensorEntity):
    """Forecast metadata (created time, grid point)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmhiLocalCoordinator,
        entry: ConfigEntry,
        device_name: str,
        desc: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._key = desc["key"]
        self._attr_name = desc["name"]
        self._attr_unique_id = f"{entry.entry_id}_{self._key}"
        self._attr_icon = desc.get("icon")
        self._attr_device_info = _device_info(entry, device_name)

    @property
    def native_value(self) -> str | None:
        return self.coordinator.meta_bundle().get(self._key)


class SmhiFireSensor(CoordinatorEntity[SmhiLocalCoordinator], SensorEntity):
    """Fire weather index sensors (fwif1g daily)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmhiLocalCoordinator,
        entry: ConfigEntry,
        device_name: str,
        desc: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._key = desc["key"]
        self._attr_name = desc["name"]
        self._attr_unique_id = f"{entry.entry_id}_fire_{self._key}"
        self._attr_native_unit_of_measurement = desc.get("unit")
        self._attr_icon = desc.get("icon")
        sc = desc.get("state_class")
        self._attr_state_class = _STATE_CLASS_MAP.get(sc) if sc else None
        self._attr_device_info = _device_info(entry, device_name)

    @property
    def native_value(self) -> float | int | str | None:
        bundle = self.coordinator.fire_bundle()
        val = bundle.get(self._key)
        if val is None:
            return None
        if self._key in ("fwi_index_sv", "grassfire_sv"):
            return val
        try:
            f = float(val)
            if f in (9999.0, -9999.0):
                return None
            return round(f, 2) if not f.is_integer() else int(f)
        except (TypeError, ValueError):
            return val


class SmhiWarningSensor(CoordinatorEntity[SmhiLocalCoordinator], SensorEntity):
    """IBWW weather warnings summary."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmhiLocalCoordinator,
        entry: ConfigEntry,
        device_name: str,
        desc: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._key = desc["key"]
        self._attr_name = desc["name"]
        self._attr_unique_id = f"{entry.entry_id}_warn_{self._key}"
        self._attr_icon = desc.get("icon")
        sc = desc.get("state_class")
        self._attr_state_class = _STATE_CLASS_MAP.get(sc) if sc else None
        self._attr_device_info = _device_info(entry, device_name)

    @property
    def native_value(self) -> str | int | None:
        bundle = self.coordinator.warnings_bundle()
        return bundle.get(self._key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._key != "warnings_summary":
            return None
        bundle = self.coordinator.warnings_bundle()
        return {"warnings": bundle.get("warnings_list") or []}


class SmhiWaterSensor(CoordinatorEntity[SmhiLocalCoordinator], SensorEntity):
    """Optional hydro/ocean observation sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmhiLocalCoordinator,
        entry: ConfigEntry,
        device_name: str,
        desc: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._key = desc["key"]
        self._attr_name = desc["name"]
        self._attr_unique_id = f"{entry.entry_id}_water_{self._key}"
        self._attr_native_unit_of_measurement = desc.get("unit")
        self._attr_icon = desc.get("icon")
        dc = desc.get("device_class")
        self._attr_device_class = _DEVICE_CLASS_MAP.get(dc) if dc else None
        sc = desc.get("state_class")
        self._attr_state_class = _STATE_CLASS_MAP.get(sc) if sc else None
        self._attr_device_info = _device_info(entry, device_name)

    @property
    def native_value(self) -> float | int | str | None:
        bundle = self.coordinator.water_bundle()
        if not bundle:
            return None
        val = bundle.get(self._key)
        if val is None:
            return None
        if self._key == "water_station":
            return val
        try:
            f = float(val)
            return round(f, 2) if not float(f).is_integer() else int(f)
        except (TypeError, ValueError):
            return val

    @property
    def available(self) -> bool:
        # Available when coordinator is ok; value may still be None if water disabled
        return super().available


class SmhiIceSensor(CoordinatorEntity[SmhiLocalCoordinator], SensorEntity):
    """Optional ice observation sensors (hydroobs, seasonal)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmhiLocalCoordinator,
        entry: ConfigEntry,
        device_name: str,
        desc: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._key = desc["key"]
        self._attr_name = desc["name"]
        self._attr_unique_id = f"{entry.entry_id}_ice_{self._key}"
        self._attr_native_unit_of_measurement = desc.get("unit")
        self._attr_icon = desc.get("icon")
        dc = desc.get("device_class")
        self._attr_device_class = _DEVICE_CLASS_MAP.get(dc) if dc else None
        sc = desc.get("state_class")
        self._attr_state_class = _STATE_CLASS_MAP.get(sc) if sc else None
        self._attr_device_info = _device_info(entry, device_name)

    @property
    def native_value(self) -> float | int | str | None:
        bundle = self.coordinator.ice_bundle()
        if not bundle:
            return None
        val = bundle.get(self._key)
        if val is None:
            return None
        if self._key in ("ice_station", "ice_observed_at", "ice_status"):
            return val
        try:
            f = float(val)
            return round(f, 1) if not float(f).is_integer() else int(f)
        except (TypeError, ValueError):
            return val
