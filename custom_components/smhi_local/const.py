"""Constants for SMHI Local integration."""

DOMAIN = "smhi_local"

# Config
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_NAME = "name"
CONF_UPDATE_INTERVAL = "update_interval"

DEFAULT_NAME = "SMHI"
DEFAULT_UPDATE_INTERVAL = 300  # seconds

# SMHI SNOW1g (pmp3g retired 2026-03-31)
API_URL = (
    "https://opendata-download-metfcst.smhi.se/api/category/snow1g"
    "/version/1/geotype/point/lon/{lon}/lat/{lat}/data.json"
)

# Legacy short codes (pmp3g) + snow1g human-readable names → normalized keys
PARAM_MAP = {
    # pmp3g short
    "t": "air_temperature",
    "ws": "wind_speed",
    "wd": "wind_from_direction",
    "gust": "wind_speed_of_gust",
    "i10fg": "wind_speed_of_gust",
    "r": "relative_humidity",
    "msl": "air_pressure_at_mean_sea_level",
    "vis": "visibility_in_air",
    "Wsymb2": "symbol_code",
    "pmean": "precipitation_amount_mean",
    "spp": "probability_of_precipitation",
    "tstm": "thunderstorm_probability",
    "pcat": "precipitation_category",
    "tcc_mean": "cloud_cover",
    "lcc_mean": "low_cloud_cover",
    # snow1g names (pass-through / alias)
    "air_temperature": "air_temperature",
    "wind_speed": "wind_speed",
    "wind_from_direction": "wind_from_direction",
    "wind_speed_of_gust": "wind_speed_of_gust",
    "relative_humidity": "relative_humidity",
    "air_pressure_at_mean_sea_level": "air_pressure_at_mean_sea_level",
    "visibility_in_air": "visibility_in_air",
    "symbol_code": "symbol_code",
    "precipitation_amount_mean": "precipitation_amount_mean",
    "probability_of_precipitation": "probability_of_precipitation",
    "thunderstorm_probability": "thunderstorm_probability",
    "predominant_precipitation_type_at_surface": "precipitation_category",
    "total_cloud_cover": "cloud_cover",
    "cloud_area_fraction": "cloud_area_fraction",
    "cloud_area_fraction_low": "cloud_area_fraction_low",
    "cloud_area_fraction_medium": "cloud_area_fraction_medium",
    "cloud_area_fraction_high": "cloud_area_fraction_high",
    "low_type_cloud_area_fraction": "low_type_cloud_area_fraction",
    "medium_type_cloud_area_fraction": "medium_type_cloud_area_fraction",
    "high_type_cloud_area_fraction": "high_type_cloud_area_fraction",
    "cloud_base_altitude": "cloud_base_altitude",
    "cloud_top_altitude": "cloud_top_altitude",
    "probability_of_frozen_precipitation": "probability_of_frozen_precipitation",
    "precipitation_frozen_part": "precipitation_frozen_part",
}

# Thresholds for derived sensors
PRECIP_THRESHOLD_MM = 0.1
BAD_VISIBILITY_KM = 10.0  # måttlig eller sämre (template < 10 km)

# Precipitation category (pcat) → Swedish label
PCAT_LABELS = {
    0: "Ingen nederbörd",
    1: "Snö",
    2: "Snöblandat regn",
    3: "Regn",
    4: "Duggregn",
    5: "Underkylt regn",
    6: "Underkylt duggregn",
    7: "Snöbyar",
    8: "Regnskurar",
    9: "Kraftiga regnskurar",
    10: "Snöblandade skurar",
    11: "Kraftiga snöbyar",
}

# Sensor definitions for *current* nearest-point fields
SENSOR_TYPES: tuple[dict, ...] = (
    {
        "key": "air_temperature",
        "name": "Temperatur",
        "unit": "°C",
        "device_class": "temperature",
        "state_class": "measurement",
        "icon": "mdi:thermometer",
    },
    {
        "key": "feels_like",
        "name": "Känns som",
        "unit": "°C",
        "device_class": "temperature",
        "state_class": "measurement",
        "icon": "mdi:thermometer-lines",
    },
    {
        "key": "relative_humidity",
        "name": "Luftfuktighet",
        "unit": "%",
        "device_class": "humidity",
        "state_class": "measurement",
        "icon": "mdi:water-percent",
    },
    {
        "key": "air_pressure_at_mean_sea_level",
        "name": "Lufttryck",
        "unit": "hPa",
        "device_class": "pressure",
        "state_class": "measurement",
        "icon": "mdi:gauge",
    },
    {
        "key": "wind_speed",
        "name": "Vindhastighet",
        "unit": "m/s",
        "device_class": "wind_speed",
        "state_class": "measurement",
        "icon": "mdi:weather-windy",
    },
    {
        "key": "wind_speed_of_gust",
        "name": "Vindby",
        "unit": "m/s",
        "device_class": "wind_speed",
        "state_class": "measurement",
        "icon": "mdi:weather-windy-variant",
    },
    {
        "key": "wind_direction_sv",
        "name": "Vindriktning",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "icon": "mdi:compass",
    },
    {
        "key": "visibility_in_air",
        "name": "Sikt",
        "unit": "km",
        "device_class": "distance",
        "state_class": "measurement",
        "icon": "mdi:eye",
    },
    {
        "key": "precipitation_amount_mean",
        "name": "Nederbörd",
        "unit": "mm/h",
        "device_class": "precipitation_intensity",
        "state_class": "measurement",
        "icon": "mdi:weather-pouring",
    },
    {
        "key": "probability_of_precipitation",
        "name": "Nederbördsrisk",
        "unit": "%",
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:weather-rainy",
    },
    {
        "key": "symbol_code",
        "name": "Vädersymbol",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "icon": "mdi:weather-partly-cloudy",
    },
    {
        "key": "condition_sv",
        "name": "Förhållande",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "icon": "mdi:weather-cloudy",
    },
    {
        "key": "cloud_type",
        "name": "Molntyp",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "icon": "mdi:cloud-outline",
    },
    {
        "key": "cloud_cover_pct",
        "name": "Molnmängd",
        "unit": "%",
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:cloud",
    },
    {
        "key": "thunderstorm_probability",
        "name": "Åskrisk nu",
        "unit": "%",
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:weather-lightning",
    },
    {
        "key": "probability_of_frozen_precipitation",
        "name": "Risk för frusen nederbörd",
        "unit": "%",
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:snowflake-alert",
    },
)

# Derived sensors (computed across timeSeries)
DERIVED_SENSOR_TYPES: tuple[dict, ...] = (
    {
        "key": "next_precip_type",
        "name": "Nästa nederbördstyp",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "icon": "mdi:weather-rainy",
    },
    {
        "key": "next_precip_amount",
        "name": "Nästa nederbördsmängd",
        "unit": "mm/h",
        "device_class": "precipitation_intensity",
        "state_class": None,
        "icon": "mdi:cup-water",
    },
    {
        "key": "next_precip_time",
        "name": "Nästa nederbördstid",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "icon": "mdi:clock-outline",
    },
    {
        "key": "precip_next_12h",
        "name": "Nederbörd kommande 12h",
        "unit": "mm",
        "device_class": "precipitation",
        "state_class": "measurement",
        "icon": "mdi:weather-pouring",
    },
    {
        "key": "thunder_risk_text",
        "name": "Åskrisk",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "icon": "mdi:weather-lightning",
    },
    {
        "key": "thunder_risk_12h",
        "name": "Åskrisk max %",
        "unit": "%",
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:weather-lightning",
    },
    {
        "key": "next_bad_visibility",
        "name": "Nästa dåliga sikt",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "icon": "mdi:eye-off",
    },
    {
        "key": "next_snow_share",
        "name": "Snöandel nästa nederbörd",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "icon": "mdi:snowflake",
    },
)
