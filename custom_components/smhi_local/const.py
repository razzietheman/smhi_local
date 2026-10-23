"""Constants for SMHI Local integration."""

DOMAIN = "smhi_local"

# Config
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_NAME = "name"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_WARNING_AREA = "warning_area"
WARNING_AREA_ALL = "all"  # show all counties

DEFAULT_NAME = "SMHI"
DEFAULT_UPDATE_INTERVAL = 300  # seconds

# SMHI SNOW1g (pmp3g retired 2026-03-31)
API_URL = (
    "https://opendata-download-metfcst.smhi.se/api/category/snow1g"
    "/version/1/geotype/point/lon/{lon}/lat/{lat}/data.json"
)
API_FIRE_URL = (
    "https://opendata-download-metfcst.smhi.se/api/category/fwif1g"
    "/version/1/daily/geotype/point/lon/{lon}/lat/{lat}/data.json"
)
API_WARNINGS_URL = (
    "https://opendata-download-warnings.smhi.se/ibww/api/version/1/warning.json"
)

# FWI-index (fwiindex) → Swedish legend (SMHI/MSB)
FWI_INDEX_SV = {
    -1: "Ej tillämpligt",
    1: "Liten risk",
    2: "Måttlig risk",
    3: "Stor risk",
    4: "Mycket stor risk",
    5: "Extremt stor risk",
    6: "Extremt stor risk (5E)",
}
GRASSFIRE_SV = {
    -1: "Ej tillämpligt / snötäcke",
    1: "Liten risk",
    2: "Måttlig risk",
    3: "Stor risk",
    4: "Mycket stor risk",
    5: "Extremt stor risk",
}

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
    "precipitation_amount_min": "precipitation_amount_min",
    "precipitation_amount_max": "precipitation_amount_max",
    "precipitation_amount_median": "precipitation_amount_median",
    "precipitation_amount_mean_deterministic": "precipitation_amount_mean_deterministic",
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
        "key": "wind_from_direction",
        "name": "Vindriktning grader",
        "unit": "°",
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:compass-outline",
    },
    {
        "key": "cloud_base_altitude",
        "name": "Molnbas",
        "unit": "m",
        "device_class": "distance",
        "state_class": "measurement",
        "icon": "mdi:arrow-collapse-down",
    },
    {
        "key": "cloud_top_altitude",
        "name": "Molntopp",
        "unit": "m",
        "device_class": "distance",
        "state_class": "measurement",
        "icon": "mdi:arrow-collapse-up",
    },
    {
        "key": "low_cloud_pct",
        "name": "Lågt molntäcke",
        "unit": "%",
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:weather-cloudy",
    },
    {
        "key": "medium_cloud_pct",
        "name": "Medelhögt molntäcke",
        "unit": "%",
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:weather-cloudy",
    },
    {
        "key": "high_cloud_pct",
        "name": "Högt molntäcke",
        "unit": "%",
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:weather-cloudy",
    },
    {
        "key": "precipitation_amount_min",
        "name": "Nederbörd min",
        "unit": "mm/h",
        "device_class": "precipitation_intensity",
        "state_class": "measurement",
        "icon": "mdi:weather-rainy",
    },
    {
        "key": "precipitation_amount_max",
        "name": "Nederbörd max",
        "unit": "mm/h",
        "device_class": "precipitation_intensity",
        "state_class": "measurement",
        "icon": "mdi:weather-pouring",
    },
    {
        "key": "precipitation_amount_median",
        "name": "Nederbörd median",
        "unit": "mm/h",
        "device_class": "precipitation_intensity",
        "state_class": "measurement",
        "icon": "mdi:weather-rainy",
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

# Metadata sensors (from forecast header / cache)
META_SENSOR_TYPES: tuple[dict, ...] = (
    {
        "key": "forecast_created",
        "name": "Prognos skapad",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "icon": "mdi:clock-check-outline",
    },
    {
        "key": "forecast_reference",
        "name": "Prognos referenstid",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "icon": "mdi:clock-start",
    },
    {
        "key": "grid_point",
        "name": "Modellpunkt",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "icon": "mdi:map-marker-radius",
    },
)

# Fire weather (fwif1g daily) – nearest valid day
FIRE_SENSOR_TYPES: tuple[dict, ...] = (
    {
        "key": "fwi_index_sv",
        "name": "Brandrisk",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "icon": "mdi:pine-tree-fire",
    },
    {
        "key": "fwi",
        "name": "FWI-värde",
        "unit": None,
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:fire",
    },
    {
        "key": "fwiindex",
        "name": "FWI-index",
        "unit": None,
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:numeric",
    },
    {
        "key": "isi",
        "name": "Initial spridning (ISI)",
        "unit": None,
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:spread",
    },
    {
        "key": "bui",
        "name": "Bränsleupplag (BUI)",
        "unit": None,
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:tree",
    },
    {
        "key": "ffmc",
        "name": "Fint bränsle (FFMC)",
        "unit": None,
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:leaf",
    },
    {
        "key": "dmc",
        "name": "Duff moisture (DMC)",
        "unit": None,
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:layers-triple",
    },
    {
        "key": "dc",
        "name": "Drought code (DC)",
        "unit": None,
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:water-off",
    },
    {
        "key": "grassfire_sv",
        "name": "Gräsbrandsrisk",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "icon": "mdi:grass",
    },
    {
        "key": "rn",
        "name": "Potentiell spridningshastighet",
        "unit": "m/min",
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:speedometer",
    },
    {
        "key": "forestdry",
        "name": "Skogstorkt index",
        "unit": None,
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:forest",
    },
)

# Warnings (IBWW)
WARNING_SENSOR_TYPES: tuple[dict, ...] = (
    {
        "key": "warnings_summary",
        "name": "Varningar",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "icon": "mdi:alert",
    },
    {
        "key": "warnings_count",
        "name": "Antal varningar",
        "unit": None,
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:counter",
    },
)


# Approximate län bounding boxes (lat_min, lat_max, lon_min, lon_max) for auto warning filter
# Rough boxes – good enough to pick home county from HA coordinates
COUNTY_BOXES: tuple[tuple[str, float, float, float, float], ...] = (
    ("Skåne län", 55.3, 56.5, 12.5, 14.6),
    ("Blekinge län", 56.0, 56.5, 14.5, 16.0),
    ("Hallands län", 56.3, 57.6, 11.8, 13.5),
    ("Kronobergs län", 56.4, 57.3, 13.5, 15.5),
    ("Kalmar län", 56.2, 58.1, 15.3, 17.2),
    ("Gotlands län", 56.9, 58.0, 18.0, 19.5),
    ("Jönköpings län", 56.9, 58.2, 13.3, 15.4),
    ("Östergötlands län", 57.7, 58.9, 14.7, 17.0),
    ("Västra Götalands län", 57.2, 59.4, 10.9, 14.7),
    ("Värmlands län", 58.7, 61.0, 11.7, 14.6),
    ("Örebro län", 58.7, 60.1, 14.3, 15.9),
    ("Södermanlands län", 58.7, 59.6, 15.6, 17.6),
    ("Stockholms län", 58.7, 60.3, 17.2, 19.4),
    ("Uppsala län", 59.4, 60.7, 16.7, 18.8),
    ("Västmanlands län", 59.2, 60.3, 15.5, 17.0),
    ("Dalarnas län", 60.0, 62.3, 12.5, 16.5),
    ("Gävleborgs län", 60.3, 62.3, 15.3, 17.8),
    ("Västernorrlands län", 62.0, 64.0, 15.5, 19.5),
    ("Jämtlands län", 61.5, 65.0, 12.0, 16.5),
    ("Västerbottens län", 63.5, 66.5, 15.0, 22.0),
    ("Norrbottens län", 65.0, 69.1, 16.0, 25.0),
)


def guess_county(lat: float, lon: float) -> str | None:
    """Best-effort län from coordinates (first matching box)."""
    for name, la0, la1, lo0, lo1 in COUNTY_BOXES:
        if la0 <= lat <= la1 and lo0 <= lon <= lo1:
            return name
    return None
