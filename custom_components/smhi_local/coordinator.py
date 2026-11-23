"""DataUpdateCoordinator for SMHI Local – snow1g fetch, cache, derived fields."""
from __future__ import annotations

from datetime import timedelta
import math
import logging
from typing import Any

from aiohttp import ClientError, ClientSession

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

STORAGE_VERSION = 1

from .const import (
    API_FIRE_URL,
    API_URL,
    API_WARNINGS_URL,
    BAD_VISIBILITY_KM,
    CACHE_MAX_AGE_MINUTES,
    CLOUD_LOOKAHEAD_MINUTES,
    DATA_STATUS_CURRENT,
    DATA_STATUS_NONE,
    DATA_STATUS_STALE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    CONF_WARNING_AREA,
    CONF_ENABLE_WATER,
    CONF_WATER_SOURCE,
    CONF_WATER_STATION_ID,
    CONF_ENABLE_ICE,
    CONF_ICE_STATION_ID,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    FWI_INDEX_SV,
    GRASSFIRE_SV,
    PARAM_MAP,
    PCAT_LABELS,
    PRECIP_PROBABILITY_THRESHOLD_PCT,
    PRECIP_THRESHOLD_MM,
    WARNING_AREA_ALL,
    WATER_SOURCE_AUTO,
    WATER_SOURCE_HYDRO,
    WATER_SOURCE_OCEAN,
    WATER_SOURCE_OFF,
    HYDRO_BASE,
    OCEAN_BASE,
)

_LOGGER = logging.getLogger(__name__)

# Wsymb2 → precip type label
_SYMBOL_PRECIP = {
    **{s: "Regnskurar" for s in (8, 9, 10)},
    11: "Åskskurar",
    **{s: "Snöblandade skurar" for s in (12, 13, 14)},
    **{s: "Snöskurar" for s in (15, 16, 17)},
    **{s: "Regn" for s in (18, 19, 20)},
    21: "Åska",
    **{s: "Snöblandat regn" for s in (22, 23, 24)},
    **{s: "Snö" for s in (25, 26, 27)},
}

_SNOW_SYMBOLS = {12, 13, 14, 15, 16, 17, 22, 23, 24, 25, 26, 27}
_SLEET_SYMBOLS = {12, 13, 14, 22, 23, 24}


def _normalize_entry(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize snow1g (flat data) or legacy pmp3g (parameters[]) entry."""
    # snow1g: time + data dict
    if "data" in raw and isinstance(raw.get("data"), dict):
        valid = raw.get("time") or raw.get("validTime")
        if not valid:
            return None
        data: dict[str, Any] = {}
        for name, val in raw["data"].items():
            key = PARAM_MAP.get(name, name)
            if val is None or val == 9999:
                continue
            if key in ("symbol_code", "precipitation_category"):
                try:
                    data[key] = int(val)
                except (TypeError, ValueError):
                    data[key] = val
            else:
                try:
                    data[key] = float(val)
                except (TypeError, ValueError):
                    data[key] = val
        return {"time": valid, "data": data}

    # pmp3g legacy
    valid = raw.get("validTime") or raw.get("time")
    params = raw.get("parameters") or []
    if not valid:
        return None
    data = {}
    for p in params:
        name = p.get("name")
        values = p.get("values") or []
        if name not in PARAM_MAP or not values:
            continue
        key = PARAM_MAP[name]
        val = values[0]
        if val == 9999:
            continue
        if key in ("symbol_code", "precipitation_category"):
            try:
                data[key] = int(val)
            except (TypeError, ValueError):
                data[key] = val
        else:
            try:
                data[key] = float(val)
            except (TypeError, ValueError):
                data[key] = val
    return {"time": valid, "data": data}


CONDITION_SV = {
    "clear-night": "Klar natt",
    "sunny": "Klart",
    "partlycloudy": "Växlande molnighet",
    "cloudy": "Mulet",
    "rainy": "Regn",
    "snowy-rainy": "Snöblandat regn",
    "snowy": "Snö",
    "lightning-rainy": "Åska",
    "fog": "Dimma",
}


def _symbol_to_condition(symbol: int, night: bool) -> str:
    """Map SMHI Wsymb2 to HA weather condition."""
    if symbol == 1:
        return "clear-night" if night else "sunny"
    if symbol in (2, 3):
        return "partlycloudy"
    if symbol == 7:
        return "fog"
    if symbol in (4, 5, 6):
        return "cloudy"
    if symbol in (8, 9, 10, 11, 18, 19, 20, 21):
        return "lightning-rainy" if symbol in (11, 21) else "rainy"
    if symbol in (12, 13, 14, 22, 23, 24):
        return "snowy-rainy"
    if symbol in (15, 16, 17, 25, 26, 27):
        return "snowy"
    return "cloudy"


def _feels_like(
    temp: float | None, wind: float | None, humidity: float | None
) -> float | None:
    """Apparent temperature (Australian formula)."""
    if temp is None:
        return None
    try:
        t = float(temp)
        e = (
            (float(humidity) / 100.0) * 6.105 * (2.71828 ** (17.27 * t / (237.7 + t)))
            if humidity is not None
            else 0.0
        )
        v = float(wind) if wind is not None else 0.0
        return round(t + 0.33 * e - 0.70 * v - 4.0, 1)
    except (TypeError, ValueError, OverflowError):
        return float(temp)


def _is_night(dt: Any, hass: HomeAssistant | None) -> bool:
    """Night for *this forecast timestamp* (not the current sun state).

    HA's ``is_up`` helper uses astral for the given point in time, so hourly
    and daily forecasts get correct clear-night/sunny conditions.
    """
    if dt is None:
        hour = dt_util.now().hour
        return hour < 6 or hour >= 21
    try:
        from homeassistant.helpers.sun import is_up  # HA core dependency

        return not is_up(hass, dt_util.as_utc(dt))
    except Exception as ex:  # noqa: BLE001
        _LOGGER.debug("SMHI Local: sun calculation unavailable (%s)", ex)
    hour = dt_util.as_local(dt).hour
    return hour < 6 or hour >= 21


def _precip_type_label(data: dict[str, Any]) -> str:
    """Match template sensor.smhi_nasta_nederbord (pcat + temp override)."""
    try:
        code = int(data.get("precipitation_category"))
    except (TypeError, ValueError):
        code = None
    try:
        temp = float(data.get("air_temperature") or 0)
    except (TypeError, ValueError):
        temp = 0.0

    snow_codes = {1, 2, 7, 10, 11}
    if code is not None and code in snow_codes and temp > 2:
        return "Regn"
    if code is not None:
        return PCAT_LABELS.get(code, "Okänd nederbörd")
    # Fallback: Wsymb2
    symbol = int(data.get("symbol_code") or 0)
    return _SYMBOL_PRECIP.get(symbol, "Okänd nederbörd")



def _snow_share_text(data: dict[str, Any]) -> str:
    """Match template sensor.smhi_snoandel_nasta_nederbord."""
    try:
        code = int(data.get("precipitation_category"))
    except (TypeError, ValueError):
        code = None
    try:
        temp = float(data.get("air_temperature") or 0)
    except (TypeError, ValueError):
        temp = 0.0

    pure_rain = code in (3, 4, 8, 9) or (code in (1, 2) and temp > 2)
    if pure_rain:
        return "Ej tillämpligt"

    spp = data.get("precipitation_frozen_part")
    try:
        spp_i = int(spp) if spp is not None else -9
    except (TypeError, ValueError):
        spp_i = -9
    if spp_i == -9 or spp is None:
        return "Ej tillämpligt"
    if spp_i == 0:
        return "Allt regn"
    if spp_i == 100:
        return "Allt snö"
    return f"{spp_i}% snö"


def _as_float(value: Any) -> float:
    """Float or 0.0 for missing/invalid SMHI values."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _precip_event_value(data: dict[str, Any]) -> float | None:
    """Amount for a real precipitation event, or None when it is just risk.

    SMHI:s ensemble mean can be >= 0.1 mm with only a few percent probability
    (light drizzle in a small share of the members). Using the mean alone made
    "next precipitation" span five days. Prefer deterministic/median values and
    accept the mean only when probability is high enough.
    """
    det = _as_float(data.get("precipitation_amount_mean_deterministic"))
    med = _as_float(data.get("precipitation_amount_median"))
    if det >= PRECIP_THRESHOLD_MM:
        return det
    if med >= PRECIP_THRESHOLD_MM:
        return med
    mean = _as_float(data.get("precipitation_amount_mean"))
    prob = _as_float(data.get("probability_of_precipitation"))
    if mean >= PRECIP_THRESHOLD_MM and prob >= PRECIP_PROBABILITY_THRESHOLD_PCT:
        return mean
    return None


def _precip_period_text(series: list[dict[str, Any]], now_ts: float) -> str:
    """Start–stop range for next precip event (template Nästa Nederbördstid)."""
    start_iso = None
    stop_iso = None
    raining = False
    done = False
    for e in series:
        if not e or done:
            continue
        dt = dt_util.parse_datetime(e.get("time", ""))
        if dt is None:
            continue
        ts = dt.timestamp()
        if ts < now_ts:
            continue
        wet = _precip_event_value(e.get("data") or {}) is not None
        if wet and not raining:
            start_iso = e["time"]
            raining = True
        if raining and wet:
            stop_iso = e["time"]
        if raining and not wet:
            done = True

    if start_iso is None:
        return "Ingen nederbörd"
    if stop_iso is None:
        stop_iso = start_iso

    def parts(iso: str) -> tuple[str, str, str, str]:
        dtl = dt_util.as_local(dt_util.parse_datetime(iso))
        wd = _WEEKDAYS_SV[dtl.weekday()]
        mon = _MONTHS_SV[dtl.month]
        return dtl.strftime("%H:%M"), wd, str(dtl.day), mon

    st, sw, sd, sm = parts(start_iso)
    et, ew, ed, em = parts(stop_iso)
    if sd == ed and sm == em:
        return f"{st} - {et} {sw} {sd} {sm}"
    return f"{st} {sw} {sd} {sm} - {et} {ew} {ed} {em}"


def _format_local_time(iso: str | None) -> str | None:
    """ISO → local 'YYYY-MM-DD HH:MM' for readable sensor state."""
    if not iso:
        return None
    dt = dt_util.parse_datetime(iso)
    if dt is None:
        return iso
    return dt_util.as_local(dt).strftime("%Y-%m-%d %H:%M")


def _cloud_type(data: dict[str, Any]) -> str:
    """Classify cloud type – same rules as template sensor.molntyp."""

    def f(key: str, default: float = 0.0) -> float:
        try:
            v = float(data.get(key) if data.get(key) is not None else default)
            # SMHI uses -8 / 9999 as missing
            if v in (-8.0, 9999.0):
                return default
            return v
        except (TypeError, ValueError):
            return default

    low = f("low_type_cloud_area_fraction")
    med = f("medium_type_cloud_area_fraction")
    high = f("high_type_cloud_area_fraction")
    base = f("cloud_base_altitude", -1.0)
    top = f("cloud_top_altitude", -1.0)
    tstm = f("thunderstorm_probability")

    has_altitude = base > 0 and top > 0
    thickness = (top - base) if has_altitude else 0.0

    if low == 0 and med == 0 and high == 0:
        return "Klar himmel"

    # Extreme vertical extent
    if has_altitude and base < 3000 and thickness > 4000:
        if tstm > 0:
            return "Vertikala åsk- eller bymoln (Cumulonimbus, Cb)"
        return "Vertikala regn- eller snömoln (Nimbostratus, Ns)"

    # Low dominates
    if low >= med and low >= high and low > 0:
        if has_altitude and base < 2000:
            if thickness > 1500:
                return "Låga stackmoln (Cumulus, Cu)"
            if thickness > 500:
                return "Låga valkmoln (Stratocumulus, Sc)"
            return "Låga dimmoln (Stratus, St)"
        return "Låga moln"

    # Medium dominates
    if med >= low and med >= high and med > 0:
        if has_altitude and 2000 <= base < 6000:
            if thickness > 2000:
                return "Medelhöga skiktmoln (Altostratus, As)"
            return "Medelhöga böljemoln (Altocumulus, Ac)"
        return "Medelhöga moln"

    # High
    if high > 0:
        if has_altitude and base >= 6000:
            if thickness < 500:
                return "Höga fjädermoln (Cirrus, Ci)"
            if thickness < 1500:
                return "Höga slöjmoln (Cirrostratus, Cs)"
            return "Höga makrillmoln (Cirrocumulus, Cc)"
        return "Höga moln"

    return "Okänt"



def _wind_direction_sv(degrees: float | None) -> str:
    """Bearing → Swedish compass label (16-point)."""
    if degrees is None:
        return "Okänt"
    try:
        d = float(degrees) % 360
    except (TypeError, ValueError):
        return "Okänt"
    if d >= 348.75 or d < 11.25:
        return "Nord"
    if d < 33.75:
        return "Nord-Nordost"
    if d < 56.25:
        return "Nordost"
    if d < 78.75:
        return "Ost-Nordost"
    if d < 101.25:
        return "Ost"
    if d < 123.75:
        return "Ost-Sydost"
    if d < 146.25:
        return "Sydost"
    if d < 168.75:
        return "Syd-Sydost"
    if d < 191.25:
        return "Syd"
    if d < 213.75:
        return "Syd-Sydväst"
    if d < 236.25:
        return "Sydväst"
    if d < 258.75:
        return "Väst-Sydväst"
    if d < 281.25:
        return "Väst"
    if d < 303.75:
        return "Väst-Nordväst"
    if d < 326.25:
        return "Nordväst"
    return "Nord-Nordväst"


def _relative_when_sv(iso: str | None) -> str:
    """Relative time phrase matching premium weather report style.

    Day parts: natt 00–06, morgon/bitti 06–09, förmiddag 09–12,
    eftermiddag 12–18, kväll 18–24. 06:00 is *not* förmiddag.
    """
    if not iso:
        return ""
    dt = dt_util.parse_datetime(iso)
    if dt is None:
        return ""
    dtl = dt_util.as_local(dt)
    today = dt_util.now().date()
    days = (dtl.date() - today).days
    h = dtl.hour
    hh = dtl.strftime("%H")
    wd = _WEEKDAYS_SV[dtl.weekday()]

    if h < 6:
        part = "natt"
    elif h < 9:
        part = "bitti"
    elif h < 12:
        part = "förmiddag"
    elif h < 18:
        part = "eftermiddag"
    else:
        part = "kväll"

    if days == 0:
        if part == "natt":
            return f"i natt klockan {hh}"
        if part == "bitti":
            return f"på morgonen klockan {hh}"
        if part == "kväll":
            return f"i kväll klockan {hh}"
        return f"på {part}en klockan {hh}"
    if days == 1:
        if part == "bitti":
            return f"i morgon bitti klockan {hh}"
        if part == "natt":
            return f"i morgon natt klockan {hh}"
        return f"i morgon {part} klockan {hh}"
    if part == "bitti":
        return f"på {wd} bitti klockan {hh}"
    return f"på {wd} {part} klockan {hh}"


_MONTHS_SV = {
    1: "januari", 2: "februari", 3: "mars", 4: "april",
    5: "maj", 6: "juni", 7: "juli", 8: "augusti",
    9: "september", 10: "oktober", 11: "november", 12: "december",
}
_WEEKDAYS_SV = {
    0: "måndag", 1: "tisdag", 2: "onsdag", 3: "torsdag",
    4: "fredag", 5: "lördag", 6: "söndag",
}


def _visibility_label(vis: float) -> str:
    """Classify visibility like template sensor.smhi_nasta_daliga_sikt."""
    if vis < 1:
        return "Mycket dålig sikt"
    if vis < 4:
        return "Dålig sikt"
    if vis < 10:
        return "Måttlig sikt"
    return "God sikt"


def _format_datum_kl(iso: str) -> str:
    """'onsdag 21 oktober kl 19:00'."""
    dt = dt_util.parse_datetime(iso)
    if dt is None:
        return ""
    local = dt_util.as_local(dt)
    wd = _WEEKDAYS_SV[local.weekday()]
    month = _MONTHS_SV[local.month]
    return f"{wd} {local.day} {month} kl {local.strftime('%H:%M')}"


def _visibility_text(vis: float, iso: str) -> str:
    label = _visibility_label(vis)
    # Match template style: integers without decimals, fractions with one.
    vis_s = f"{vis:g}" if vis == int(vis) else f"{vis:.1f}"
    return f"{label} ({vis_s} km), {_format_datum_kl(iso)}"



def _point_in_ring(lon: float, lat: float, ring: list) -> bool:
    """Ray-casting point-in-polygon for one linear ring [[lon, lat], ...]."""
    n = len(ring)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        try:
            xi, yi = float(ring[i][0]), float(ring[i][1])
            xj, yj = float(ring[j][0]), float(ring[j][1])
        except (TypeError, ValueError, IndexError):
            j = i
            continue
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-30) + xi
        ):
            inside = not inside
        j = i
    return inside


def _point_in_geometry(lon: float, lat: float, geom: dict | None) -> bool:
    """True if (lon, lat) lies inside GeoJSON Polygon or MultiPolygon (EPSG:4326)."""
    if not geom or not isinstance(geom, dict):
        return False
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    if gtype == "Polygon":
        if not coords or not coords[0]:
            return False
        if not _point_in_ring(lon, lat, coords[0]):
            return False
        # holes
        for hole in coords[1:]:
            if hole and _point_in_ring(lon, lat, hole):
                return False
        return True
    if gtype == "MultiPolygon":
        for poly in coords:
            if not poly or not poly[0]:
                continue
            if _point_in_ring(lon, lat, poly[0]):
                if any(_point_in_ring(lon, lat, h) for h in poly[1:] if h):
                    continue
                return True
        return False
    return False



def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def _obs_station_periods(
    session: ClientSession, base: str, parameter: int, station_key: str
) -> list[str]:
    """Return available period keys for a station."""
    st_url = f"{base}/parameter/{parameter}/station/{station_key}.json"
    try:
        async with session.get(st_url, timeout=20) as resp:
            if resp.status != 200:
                _LOGGER.debug("SMHI station periods %s: HTTP %s", st_url, resp.status)
                return []
            st = await resp.json()
    except Exception as ex:  # noqa: BLE001
        _LOGGER.warning("SMHI station periods %s failed: %s", st_url, ex)
        return []
    return [p.get("key") for p in (st.get("period") or []) if p.get("key")]


async def _obs_nearest_station(
    session: ClientSession,
    base: str,
    parameter: int,
    lat: float,
    lon: float,
    manual_id: str | None = None,
    *,
    prefer_live: bool = True,
) -> dict[str, Any] | None:
    """Pick nearest station for an obs parameter (or manual id).

    When prefer_live is True, stations with latest-hour/day/months are preferred
    over archive-only stations (important for hydro water level near inland towns).
    """
    url = f"{base}/parameter/{parameter}.json"
    try:
        async with session.get(url, timeout=25) as resp:
            if resp.status != 200:
                _LOGGER.warning("SMHI station list %s: HTTP %s", url, resp.status)
                return None
            payload = await resp.json()
    except Exception as ex:  # noqa: BLE001
        _LOGGER.warning("SMHI station list %s failed: %s", url, ex)
        return None
    stations = payload.get("station") or []
    if manual_id:
        mid = str(manual_id).strip()
        for s in stations:
            if str(s.get("key")) == mid or str(s.get("id")) == mid:
                s = dict(s)
                try:
                    s["_distance_km"] = round(
                        _haversine_km(
                            lat, lon, float(s["latitude"]), float(s["longitude"])
                        ),
                        1,
                    )
                except (KeyError, TypeError, ValueError):
                    s["_distance_km"] = None
                return s
        # Never silently substitute another station for an explicit user choice.
        _LOGGER.warning(
            "SMHI station ID %s not found for parameter %s at %s", mid, parameter, base
        )
        return None

    candidates: list[tuple[float, dict[str, Any]]] = []
    for s in stations:
        # Keep active stations; also keep those without active flag
        if s.get("active") is False:
            continue
        try:
            slat = float(s["latitude"])
            slon = float(s["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        d = _haversine_km(lat, lon, slat, slon)
        candidates.append((d, s))
    if not candidates:
        # last resort: include inactive (archive-only networks)
        for s in stations:
            try:
                slat = float(s["latitude"])
                slon = float(s["longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            d = _haversine_km(lat, lon, slat, slon)
            candidates.append((d, s))
    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])

    if prefer_live:
        # Check nearest N stations for live periods (limit HTTP)
        live_best = None
        live_d = float("inf")
        for d, s in candidates[:25]:
            key = str(s.get("key"))
            periods = await _obs_station_periods(session, base, parameter, key)
            if any(p in periods for p in ("latest-hour", "latest-day", "latest-months")):
                if d < live_d:
                    live_d = d
                    live_best = s
                    # first match is nearest with live among scanned; can break if sorted
                    break
        if live_best is not None:
            live_best = dict(live_best)
            live_best["_distance_km"] = round(live_d, 1)
            live_best["_periods_hint"] = "live"
            return live_best

    # Fallback: absolute nearest (may be archive-only)
    d, s = candidates[0]
    s = dict(s)
    s["_distance_km"] = round(d, 1)
    s["_periods_hint"] = "nearest"
    return s


async def _obs_latest_value(
    session: ClientSession,
    base: str,
    parameter: int,
    station_key: str,
    *,
    allow_archive: bool = False,
) -> tuple[float | None, int | None]:
    """Fetch latest numeric value (+ optional unix ms date) for station/parameter."""
    st_url = f"{base}/parameter/{parameter}/station/{station_key}.json"
    try:
        async with session.get(st_url, timeout=20) as resp:
            if resp.status != 200:
                _LOGGER.debug("SMHI observation %s: HTTP %s", st_url, resp.status)
                return None, None
            st = await resp.json()
    except Exception as ex:  # noqa: BLE001
        _LOGGER.warning("SMHI observation %s failed: %s", st_url, ex)
        return None, None
    periods = [p.get("key") for p in (st.get("period") or []) if p.get("key")]
    order = ["latest-hour", "latest-day", "latest-months"]
    if allow_archive:
        order.append("corrected-archive")
    for period in order:
        if period not in periods:
            continue
        data_url = (
            f"{base}/parameter/{parameter}/station/{station_key}"
            f"/period/{period}/data.json"
        )
        try:
            async with session.get(data_url, timeout=30) as resp:
                if resp.status != 200:
                    _LOGGER.debug("SMHI observation data %s: HTTP %s", data_url, resp.status)
                    continue
                payload = await resp.json()
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("SMHI observation data %s failed: %s", data_url, ex)
            continue
        values = payload.get("value") or []
        if not values:
            continue
        last = values[-1]
        try:
            val = float(last.get("value"))
        except (TypeError, ValueError):
            continue
        date_ms = last.get("date")
        try:
            date_ms = int(date_ms) if date_ms is not None else None
        except (TypeError, ValueError):
            date_ms = None
        return val, date_ms
    return None, None



def _valid_cloud_altitude(val: Any) -> float | None:
    """Return altitude in metres or None if missing/sentinel (9999, -1, -9, …)."""
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if f in (9999.0, -1.0, -9.0, -8.0) or f < 0:
        return None
    return f


def _cloud_altitude_from_series(
    series: list[dict[str, Any]],
    key: str,
    now_ts: float,
    window_seconds: float = CLOUD_LOOKAHEAD_MINUTES * 60,
) -> float | None:
    """Nearest timeSeries point within a limited window with a valid altitude."""
    best_val: float | None = None
    best_diff = float("inf")
    for e in series:
        if not e or "data" not in e:
            continue
        dt = dt_util.parse_datetime(e.get("time") or "")
        if dt is None:
            continue
        diff = abs(dt.timestamp() - now_ts)
        if diff > window_seconds:
            continue
        val = _valid_cloud_altitude((e.get("data") or {}).get(key))
        if val is None:
            continue
        if diff < best_diff:
            best_diff = diff
            best_val = val
    return best_val

def _data_is_stale(data: dict[str, Any] | None) -> bool:
    """True when no forecast exists or the last successful fetch is too old."""
    if not data or not data.get("timeSeries"):
        return True
    stamp = data.get("last_success_at") or data.get("fetched_at")
    if not stamp:
        return True
    dt = dt_util.parse_datetime(stamp)
    if dt is None:
        return True
    try:
        age = (dt_util.utcnow() - dt_util.as_utc(dt)).total_seconds()
    except Exception:  # noqa: BLE001
        return True
    return age > CACHE_MAX_AGE_MINUTES * 60


def _cache_age_minutes(data: dict[str, Any] | None) -> int | None:
    """Age of the last successful forecast fetch, in whole minutes."""
    if not data:
        return None
    stamp = data.get("last_success_at") or data.get("fetched_at")
    dt = dt_util.parse_datetime(stamp) if stamp else None
    if dt is None:
        return None
    try:
        return max(0, int((dt_util.utcnow() - dt_util.as_utc(dt)).total_seconds() // 60))
    except Exception:  # noqa: BLE001
        return None


class SmhiLocalCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch SMHI forecast; keep last good timeSeries on failure."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        session: ClientSession,
    ) -> None:
        """Initialize."""
        interval = entry.options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
            config_entry=entry,
        )
        self.entry = entry
        self.session = session
        self._last_good: dict[str, Any] | None = None
        # Hold last valid cloud altitudes so history has no gaps on SMHI 9999
        self._last_cloud_base: float | None = None
        self._last_cloud_top: float | None = None
        # Persist cache across HA restarts (.storage/smhi_local.<entry_id>)
        self._store = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )

    @property
    def source_data(self) -> dict[str, Any]:
        """Raw data (live or cached) used as input for all bundles."""
        return self.data or self._last_good or {}

    @property
    def data_is_stale(self) -> bool:
        """Cached forecast older than CACHE_MAX_AGE_MINUTES."""
        return _data_is_stale(self.source_data)

    @property
    def latitude(self) -> float:
        return float(self.entry.data[CONF_LATITUDE])

    @property
    def longitude(self) -> float:
        return float(self.entry.data[CONF_LONGITUDE])

    async def async_load_cache(self) -> None:
        """Restore last_good + cloud holds from disk (survives HA restart)."""
        try:
            data = await self._store.async_load()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("SMHI Local: could not load persistent cache")
            return
        if not data or not isinstance(data, dict):
            return
        last_good = data.get("last_good")
        if isinstance(last_good, dict) and last_good.get("timeSeries"):
            self._last_good = last_good
            _LOGGER.info(
                "SMHI Local: restored forecast cache (%s points, saved %s)",
                len(last_good.get("timeSeries") or []),
                data.get("saved_at"),
            )
        base = data.get("last_cloud_base")
        top = data.get("last_cloud_top")
        try:
            self._last_cloud_base = float(base) if base is not None else None
        except (TypeError, ValueError):
            self._last_cloud_base = None
        try:
            self._last_cloud_top = float(top) if top is not None else None
        except (TypeError, ValueError):
            self._last_cloud_top = None

    async def async_save_cache(self) -> None:
        """Write last_good + cloud holds to disk (without derived bundles)."""
        if self._last_good is None and self._last_cloud_base is None:
            return
        last_good = {
            key: value
            for key, value in self._last_good.items()
            if key != "_bundles"
        } if self._last_good else None
        payload = {
            "saved_at": dt_util.utcnow().isoformat(),
            "last_good": last_good,
            "last_cloud_base": self._last_cloud_base,
            "last_cloud_top": self._last_cloud_top,
        }
        try:
            await self._store.async_save(payload)
            _LOGGER.debug("SMHI Local: persistent cache saved")
        except Exception:  # noqa: BLE001
            _LOGGER.exception("SMHI Local: could not save persistent cache")

    def _nearest_entry(
        self, series: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Pick timeSeries entry closest to now."""
        now_ts = dt_util.now().timestamp()
        best: dict[str, Any] | None = None
        best_diff = float("inf")
        for e in series:
            if not e or "time" not in e:
                continue
            dt = dt_util.parse_datetime(e["time"])
            if dt is None:
                continue
            diff = abs(dt.timestamp() - now_ts)
            if diff < best_diff:
                best_diff = diff
                best = e
        return best

    def _cached_bundle(self, name: str, compute) -> dict[str, Any]:
        """Return a bundle computed once per coordinator update."""
        data = self.source_data
        bundles = data.get("_bundles") or {}
        if isinstance(bundles.get(name), dict):
            return bundles[name]
        return compute(data)

    def current_bundle(self) -> dict[str, Any]:
        """Current values + condition from nearest point."""
        return self._cached_bundle("current", self._compute_current)

    def _resolve_cloud_altitude(
        self,
        raw_data: dict[str, Any],
        series: list[dict[str, Any]],
        key: str,
        now_ts: float,
    ) -> tuple[float | None, str]:
        """Current value, else nearby series value, else held value."""
        val = _valid_cloud_altitude(raw_data.get(key))
        if val is not None:
            return val, "current"
        val = _cloud_altitude_from_series(series, key, now_ts)
        if val is not None:
            return val, "series"
        held = self._last_cloud_base if key == "cloud_base_altitude" else self._last_cloud_top
        if held is not None:
            return held, "cache"
        return None, "none"

    def _compute_current(self, data: dict[str, Any]) -> dict[str, Any]:
        """Compute current values + condition from nearest point."""
        series = data.get("timeSeries") or []
        entry = self._nearest_entry(series)
        if not entry:
            return {}

        raw_data = dict(entry.get("data") or {})
        symbol = int(raw_data.get("symbol_code") or 6)
        dt = dt_util.parse_datetime(entry["time"])
        night = _is_night(dt, self.hass) if dt else False
        condition = _symbol_to_condition(symbol, night)
        raw_data["condition"] = condition
        raw_data["condition_sv"] = CONDITION_SV.get(condition, condition)
        raw_data["time"] = entry["time"]
        raw_data["feels_like"] = _feels_like(
            raw_data.get("air_temperature"),
            raw_data.get("wind_speed"),
            raw_data.get("relative_humidity"),
        )
        # Molnmängd % – snow1g: cloud_area_fraction (0–8 oktas) same as old template
        caf = raw_data.get("cloud_area_fraction")
        if caf is not None:
            try:
                raw_data["cloud_cover_pct"] = int(round(float(caf) / 8 * 100))
            except (TypeError, ValueError):
                raw_data["cloud_cover_pct"] = None
        elif raw_data.get("cloud_cover") is not None:
            try:
                # already oktas 0–8
                raw_data["cloud_cover_pct"] = int(round(float(raw_data["cloud_cover"]) / 8 * 100))
            except (TypeError, ValueError):
                raw_data["cloud_cover_pct"] = None
        else:
            raw_data["cloud_cover_pct"] = None
        # Cloud levels % (oktas 0–8 → percent)
        for src, dst in (
            ("low_type_cloud_area_fraction", "low_cloud_pct"),
            ("medium_type_cloud_area_fraction", "medium_cloud_pct"),
            ("high_type_cloud_area_fraction", "high_cloud_pct"),
        ):
            raw = raw_data.get(src)
            if raw is not None:
                try:
                    v = float(raw)
                    if v in (-8.0, 9999.0):
                        raw_data[dst] = None
                    else:
                        raw_data[dst] = int(round(v / 8 * 100))
                except (TypeError, ValueError):
                    raw_data[dst] = None
            else:
                raw_data[dst] = None
        # Cloud base/top: SMHI uses 9999 when missing. Fall back only to points
        # within CLOUD_LOOKAHEAD_MINUTES, then to the last held value, and mark
        # the result as estimated so users can see it is not a direct reading.
        now_ts = dt_util.now().timestamp()
        base, base_source = self._resolve_cloud_altitude(
            raw_data, series, "cloud_base_altitude", now_ts
        )
        top, top_source = self._resolve_cloud_altitude(
            raw_data, series, "cloud_top_altitude", now_ts
        )
        raw_data["cloud_base_altitude"] = base
        raw_data["cloud_top_altitude"] = top
        raw_data["cloud_base_altitude_estimated"] = base_source != "current"
        raw_data["cloud_top_altitude_estimated"] = top_source != "current"
        raw_data["cloud_altitude_source"] = f"{base_source}/{top_source}"
        if base is not None:
            self._last_cloud_base = base
        if top is not None:
            self._last_cloud_top = top

        raw_data["cloud_type"] = _cloud_type(raw_data)
        raw_data["wind_direction_sv"] = _wind_direction_sv(
            raw_data.get("wind_from_direction")
        )
        return raw_data

    def derived_bundle(self) -> dict[str, Any]:
        """Scan future series for next precip, 12h sum, thunder, bad visibility."""
        return self._cached_bundle("derived", self._compute_derived)

    def _compute_derived(self, data: dict[str, Any]) -> dict[str, Any]:
        """Compute derived sensors from the full timeSeries."""
        series = data.get("timeSeries") or []
        now_ts = dt_util.now().timestamp()
        horizon_12h = now_ts + 12 * 3600
        horizon_48h = now_ts + 48 * 3600

        result: dict[str, Any] = {
            "next_precip_type": "Ingen nederbörd väntas",
            "next_precip_amount": None,
            "next_precip_time": "Ingen nederbörd",
            "precip_next_12h": 0.0,
            "thunder_risk_12h": 0,
            "next_bad_visibility": "God sikt",
            "next_bad_visibility_time": None,
            "next_snow_share": "Ingen nederbörd väntas",
        }

        found_precip = False
        found_bad_vis = False
        precip_sum = 0.0
        max_tstm = 0.0
        max_tstm_time: str | None = None

        for e in series:
            if not e or "time" not in e or "data" not in e:
                continue
            dt = dt_util.parse_datetime(e["time"])
            if dt is None:
                continue
            ts = dt.timestamp()
            d = e["data"]

            # 12h precip sum – same window as template: now .. now+12h
            if now_ts <= ts <= horizon_12h:
                try:
                    precip_sum += float(d.get("precipitation_amount_mean") or 0)
                except (TypeError, ValueError):
                    pass
                try:
                    tstm = float(d.get("thunderstorm_probability") or 0)
                    if tstm > max_tstm:
                        max_tstm = tstm
                        max_tstm_time = e["time"]
                except (TypeError, ValueError):
                    pass
                # symbol 11/21 also counts as thunder signal
                sym = int(d.get("symbol_code") or 0)
                if sym in (11, 21) and max_tstm < 80.0:
                    max_tstm = max(max_tstm, 80.0)
                    max_tstm_time = e["time"]

            # Next real precipitation – see _precip_event_value() for why the
            # ensemble mean alone is not enough.
            if not found_precip and ts >= now_ts:
                amount = _precip_event_value(d)
                if amount is not None:
                    found_precip = True
                    result["next_precip_type"] = _precip_type_label(d)
                    result["next_precip_amount"] = round(amount, 2)
                    result["next_precip_time_iso"] = e["time"]
                    result["next_snow_share"] = _snow_share_text(d)

            # Next moderate/bad visibility within 48h (template: vis < 10)
            if not found_bad_vis and now_ts <= ts <= horizon_48h:
                try:
                    vis = float(d.get("visibility_in_air"))
                except (TypeError, ValueError):
                    vis = None
                if vis is not None and vis < BAD_VISIBILITY_KM:
                    found_bad_vis = True
                    result["next_bad_visibility"] = _visibility_text(vis, e["time"])
                    result["next_bad_visibility_time"] = _format_local_time(e["time"])
                    result["next_bad_visibility_time_iso"] = e["time"]
                    result["next_bad_visibility_km"] = vis

        result["next_precip_time"] = _precip_period_text(series, now_ts)
        result["precip_next_12h"] = round(precip_sum, 1)
        risk_pct = int(round(max_tstm))
        result["thunder_risk_12h"] = risk_pct
        if risk_pct == 0:
            result["thunder_risk_text"] = "Ingen åskrisk"
        else:
            when = _relative_when_sv(max_tstm_time)
            if risk_pct < 25:
                level = "Liten åskrisk"
            elif risk_pct < 50:
                level = "Måttlig åskrisk"
            else:
                level = "Hög åskrisk"
            result["thunder_risk_text"] = (
                f"{level} {risk_pct}% {when}".strip()
            )
        return result

    def _finalize(self, data: dict[str, Any]) -> dict[str, Any]:
        """Compute all entity bundles once, after every layer is resolved."""
        data["_bundles"] = {
            "current": self._compute_current(data),
            "derived": self._compute_derived(data),
            "meta": self._compute_meta(data),
            "fire": self._compute_fire(data),
            "warnings": self._compute_warnings(data),
            "water": self._compute_water(data),
            "ice": self._compute_ice(data),
            "status": self._compute_status(data),
        }
        return data

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all layers; preserve last good per layer on failure."""
        lat = round(self.latitude, 4)
        lon = round(self.longitude, 4)
        url = API_URL.format(lat=lat, lon=lon)
        fire_url = API_FIRE_URL.format(lat=lat, lon=lon)

        snow_ok = False
        fire_ok = False
        warn_ok = False
        result: dict[str, Any] = {
            "timeSeries": [],
            "fetched_at": dt_util.now().isoformat(),
            "latitude": lat,
            "longitude": lon,
            "createdTime": None,
            "referenceTime": None,
            "geometry": None,
            "fire": None,
            "warnings": [],
            "last_success_at": None,
        }

        # --- snow1g ---
        try:
            async with self.session.get(url, timeout=20) as response:
                if response.status != 200:
                    text = await response.text()
                    _LOGGER.error("SMHI snow1g %s: %s", response.status, text[:200])
                else:
                    payload = await response.json()
                    raw_series = payload.get("timeSeries") or []
                    series: list[dict[str, Any]] = []
                    for item in raw_series:
                        norm = _normalize_entry(item)
                        if norm:
                            series.append(norm)
                    if series:
                        result["timeSeries"] = series
                        result["createdTime"] = payload.get("createdTime")
                        result["referenceTime"] = payload.get("referenceTime")
                        result["geometry"] = payload.get("geometry")
                        snow_ok = True
                    else:
                        _LOGGER.error("SMHI snow1g empty timeSeries")
        except ClientError as ex:
            _LOGGER.warning("SMHI snow1g network error: %s", ex)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("SMHI snow1g unexpected error")

        # --- fire fwif1g daily ---
        try:
            async with self.session.get(fire_url, timeout=20) as response:
                if response.status != 200:
                    text = await response.text()
                    _LOGGER.warning("SMHI fire %s: %s", response.status, text[:200])
                else:
                    payload = await response.json()
                    fire_series = payload.get("timeSeries") or []
                    # pick nearest validTime to now
                    now_ts = dt_util.now().timestamp()
                    best = None
                    best_diff = float("inf")
                    for entry in fire_series:
                        vt = entry.get("validTime")
                        dt = dt_util.parse_datetime(vt) if vt else None
                        if dt is None:
                            continue
                        diff = abs(dt.timestamp() - now_ts)
                        if diff < best_diff:
                            best_diff = diff
                            best = entry
                    fire_data: dict[str, Any] = {}
                    if best:
                        for p in best.get("parameters") or []:
                            name = p.get("name")
                            values = p.get("values") or []
                            if not name or not values:
                                continue
                            val = values[0]
                            if val in (9999, 9999.0):
                                continue
                            fire_data[name] = val
                        fire_data["validTime"] = best.get("validTime")
                    result["fire"] = {
                        "approvedTime": payload.get("approvedTime"),
                        "referenceTime": payload.get("referenceTime"),
                        "geometry": payload.get("geometry"),
                        "data": fire_data,
                    }
                    fire_ok = any(
                        key != "validTime" for key in fire_data
                    )
                    if not fire_ok:
                        _LOGGER.debug("SMHI fire response contained no usable parameters")
        except ClientError as ex:
            _LOGGER.warning("SMHI fire network error: %s", ex)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("SMHI fire unexpected error")

        # --- IBWW warnings ---
        try:
            async with self.session.get(API_WARNINGS_URL, timeout=20) as response:
                if response.status != 200:
                    text = await response.text()
                    _LOGGER.warning("SMHI warnings %s: %s", response.status, text[:200])
                else:
                    payload = await response.json()
                    if isinstance(payload, list):
                        result["warnings"] = payload
                        warn_ok = True
                    else:
                        result["warnings"] = []
        except ClientError as ex:
            _LOGGER.warning("SMHI warnings network error: %s", ex)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("SMHI warnings unexpected error")


        # --- Water observations (optional hydroobs / ocobs) ---
        result["water"] = None
        water_ok = False
        enable_water = bool(self.entry.options.get(CONF_ENABLE_WATER, False))
        water_source = self.entry.options.get(CONF_WATER_SOURCE, WATER_SOURCE_AUTO)
        manual_id = str(self.entry.options.get(CONF_WATER_STATION_ID) or "").strip() or None
        if enable_water and water_source != WATER_SOURCE_OFF:
            try:
                water = await self._async_fetch_water(
                    lat, lon, water_source, manual_id
                )
                result["water"] = water
                water_ok = bool(water) and any(
                    water.get(key) is not None
                    for key in ("water_level", "water_temperature", "wave_height")
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("SMHI water observations failed")

        # --- Ice observations (hydroobs param 7, seasonal) ---
        result["ice"] = None
        ice_ok = False
        enable_ice = bool(self.entry.options.get(CONF_ENABLE_ICE, False))
        ice_manual = str(self.entry.options.get(CONF_ICE_STATION_ID) or "").strip() or None
        if enable_ice:
            try:
                ice = await self._async_fetch_ice(lat, lon, ice_manual)
                result["ice"] = ice
                ice_ok = bool(ice) and ice.get("ice_thickness") is not None
            except Exception:  # noqa: BLE001
                _LOGGER.exception("SMHI ice observations failed")

        # --- Resolve every layer independently, keeping the last good value ---
        previous = dict(self._last_good or {})
        layer_ok = {
            "fire": fire_ok,
            "warnings": warn_ok,
            "water": water_ok,
            "ice": ice_ok,
        }
        for key, ok in layer_ok.items():
            if ok:
                result[f"last_{key}_success_at"] = result["fetched_at"]
            else:
                result[key] = previous.get(key, result.get(key))
                result[f"last_{key}_success_at"] = previous.get(
                    f"last_{key}_success_at"
                )

        if snow_ok:
            final = dict(result)
            final["last_success_at"] = result["fetched_at"]
        else:
            if not previous:
                raise UpdateFailed("SMHI snow1g unavailable and no cached forecast")
            final = dict(previous)
            for key, ok in layer_ok.items():
                if ok:
                    final[key] = result[key]
                    final[f"last_{key}_success_at"] = result[f"last_{key}_success_at"]
            # last_success_at deliberately stays at the last snow1g success.
            final["fetched_at"] = result["fetched_at"]
            final["latitude"] = lat
            final["longitude"] = lon

        self._last_good = self._finalize(final)
        await self.async_save_cache()
        return self._last_good

    def meta_bundle(self) -> dict[str, Any]:
        """Forecast metadata for sensors."""
        return self._cached_bundle("meta", self._compute_meta)

    def _compute_meta(self, data: dict[str, Any]) -> dict[str, Any]:
        """Compute forecast metadata."""
        created = data.get("createdTime")
        ref = data.get("referenceTime")
        geom = data.get("geometry") or {}
        coords = None
        try:
            c0 = geom.get("coordinates")
            # snow1g: [lon, lat] ; fire sometimes [[lon, lat]]
            if c0 and isinstance(c0[0], (int, float)):
                coords = c0
            elif c0 and isinstance(c0[0], (list, tuple)):
                coords = c0[0]
        except (TypeError, IndexError, KeyError):
            coords = None
        grid = None
        if coords and len(coords) >= 2:
            grid = f"{float(coords[1]):.4f}, {float(coords[0]):.4f}"
        return {
            "forecast_created": _format_local_time(created) if created else None,
            "forecast_reference": _format_local_time(ref) if ref else None,
            "grid_point": grid,
        }

    def fire_bundle(self) -> dict[str, Any]:
        """Fire weather indices for nearest day."""
        return self._cached_bundle("fire", self._compute_fire)

    def _compute_fire(self, data: dict[str, Any]) -> dict[str, Any]:
        """Compute fire weather indices."""
        fire = data.get("fire") or {}
        d = dict(fire.get("data") or {})
        try:
            idx = int(float(d.get("fwiindex")))
        except (TypeError, ValueError):
            idx = -1
        try:
            gf = int(float(d.get("grassfire")))
        except (TypeError, ValueError):
            gf = -1
        d["fwi_index_sv"] = FWI_INDEX_SV.get(idx, f"Okänd ({idx})")
        d["grassfire_sv"] = GRASSFIRE_SV.get(gf, f"Okänd ({gf})")
        return d

    def _warning_area_filter(self) -> str | None:
        """Optional name filter. None = geometry-only (default). 'all' = no filter."""
        opt = self.entry.options.get(CONF_WARNING_AREA)
        if opt is None:
            opt = self.entry.data.get(CONF_WARNING_AREA)
        if opt is not None and str(opt).strip().lower() in (
            WARNING_AREA_ALL,
            "*",
            "alla",
            "all",
        ):
            return WARNING_AREA_ALL
        if opt is not None and str(opt).strip():
            return str(opt).strip()
        return None

    def warnings_bundle(self) -> dict[str, Any]:
        """IBWW warnings relevant to the configured point."""
        return self._cached_bundle("warnings", self._compute_warnings)

    def _compute_warnings(self, data: dict[str, Any]) -> dict[str, Any]:
        """Filter IBWW warnings.

        Default: only areas whose GeoJSON polygon contains lat/lon.
        warning_area=all: every active warning in Sweden.
        warning_area=<name>: geometry hit OR name match.
        """
        warnings = data.get("warnings") or []
        area_opt = self._warning_area_filter()
        show_all = area_opt == WARNING_AREA_ALL
        name_filter = None if show_all or area_opt is None else area_opt.lower()
        lon = float(self.longitude)
        lat = float(self.latitude)

        if not warnings:
            return {
                "warnings_count": 0,
                "warnings_summary": "Inga aktiva varningar",
                "warnings_list": [],
                "filter_area": "geometry" if not show_all else "all",
                "filter_mode": "all" if show_all else "point_in_polygon",
            }

        items: list[dict[str, Any]] = []

        for w in warnings:
            event = (
                (w.get("event") or {}).get("sv")
                or (w.get("event") or {}).get("en")
                or "?"
            )
            for a in w.get("warningAreas") or []:
                area_name = (a.get("areaName") or {}).get("sv") or "?"
                affected = a.get("affectedAreas") or []
                affected_names = " ".join(
                    (x.get("sv") or x.get("en") or "")
                    for x in affected
                    if isinstance(x, dict)
                )
                geom = (a.get("area") or {}).get("geometry")
                inside = bool(geom and _point_in_geometry(lon, lat, geom))

                if not show_all:
                    name_hit = bool(
                        name_filter
                        and name_filter in f"{area_name} {affected_names}".lower()
                    )
                    if name_filter:
                        # Documented OR semantics: polygon hit or name match.
                        if not (inside or name_hit):
                            continue
                    elif not inside:
                        # Default: strict point-in-polygon (no polygon → skip).
                        continue
                # show_all: keep every area

                lvl = a.get("warningLevel") or {}
                code = lvl.get("code") or "MESSAGE"
                label = lvl.get("sv") or lvl.get("en") or code
                items.append(
                    {
                        "event": event,
                        "level": label,
                        "level_code": code,
                        "area": area_name,
                        "id": a.get("id"),
                        "in_polygon": inside,
                    }
                )

        count = len(items)
        mode = "all" if show_all else "point_in_polygon"
        if count == 0:
            return {
                "warnings_count": 0,
                "warnings_summary": "Inga aktiva varningar för din plats",
                "warnings_list": [],
                "filter_area": area_opt or "geometry",
                "filter_mode": mode,
            }

        top = items[:3]
        bits = [f"{i['level']}: {i['event']} ({i['area']})" for i in top]
        extra = f" · +{count - 3} till" if count > 3 else ""
        summary = f"{count} aktiva · " + " · ".join(bits) + extra

        return {
            "warnings_count": count,
            "warnings_summary": summary,
            "warnings_list": items,
            "filter_area": area_opt or "geometry",
            "filter_mode": mode,
        }

    async def _async_fetch_water(
        self,
        lat: float,
        lon: float,
        source: str,
        manual_id: str | None,
    ) -> dict[str, Any]:
        """Resolve nearest hydro/ocean station and latest readings."""
        out: dict[str, Any] = {
            "water_level": None,
            "water_temperature": None,
            "wave_height": None,
            "water_station": None,
            "water_station_distance": None,
            "source": source,
        }

        async def hydro_bundle() -> dict[str, Any]:
            st = await _obs_nearest_station(
                self.session, HYDRO_BASE, 3, lat, lon, manual_id, prefer_live=True
            )
            if not st:
                return {}
            key = str(st.get("key"))
            # Prefer live; fall back to corrected-archive (many lake stations)
            level, level_date = await _obs_latest_value(
                self.session, HYDRO_BASE, 3, key, allow_archive=True
            )
            # Hydro water temperature network is sparse/inactive – try same station,
            # then nearest temp station including archive
            temp, _ = await _obs_latest_value(
                self.session, HYDRO_BASE, 4, key, allow_archive=True
            )
            if temp is None:
                st_t = await _obs_nearest_station(
                    self.session, HYDRO_BASE, 4, lat, lon, None, prefer_live=True
                )
                if st_t:
                    temp, _ = await _obs_latest_value(
                        self.session,
                        HYDRO_BASE,
                        4,
                        str(st_t.get("key")),
                        allow_archive=True,
                    )
            return {
                "water_level": level,
                "water_temperature": temp,
                "wave_height": None,
                "water_station": st.get("name") or key,
                "water_station_distance": st.get("_distance_km"),
                "source": WATER_SOURCE_HYDRO,
                "station_id": key,
                "water_level_date_ms": level_date,
            }


        async def ocean_bundle() -> dict[str, Any]:
            st = await _obs_nearest_station(
                self.session, OCEAN_BASE, 6, lat, lon, manual_id
            )
            if not st:
                # fall back to sea temp station list
                st = await _obs_nearest_station(
                    self.session, OCEAN_BASE, 5, lat, lon, manual_id
                )
            if not st:
                return {}
            key = str(st.get("key"))
            level, _ = await _obs_latest_value(self.session, OCEAN_BASE, 6, key, allow_archive=True)
            temp, _ = await _obs_latest_value(self.session, OCEAN_BASE, 5, key, allow_archive=True)
            if temp is None:
                st_t = await _obs_nearest_station(
                    self.session, OCEAN_BASE, 5, lat, lon, None
                )
                if st_t:
                    temp, _ = await _obs_latest_value(
                        self.session, OCEAN_BASE, 5, str(st_t.get("key"))
                    )
            wave, _ = await _obs_latest_value(self.session, OCEAN_BASE, 1, key)
            if wave is None:
                st_w = await _obs_nearest_station(
                    self.session, OCEAN_BASE, 1, lat, lon, None
                )
                if st_w:
                    wave, _ = await _obs_latest_value(
                        self.session, OCEAN_BASE, 1, str(st_w.get("key"))
                    )
            return {
                "water_level": level,
                "water_temperature": temp,
                "wave_height": wave,
                "water_station": st.get("name") or key,
                "water_station_distance": st.get("_distance_km"),
                "source": WATER_SOURCE_OCEAN,
                "station_id": key,
            }

        if source == WATER_SOURCE_HYDRO:
            return {**out, **(await hydro_bundle())}
        if source == WATER_SOURCE_OCEAN:
            return {**out, **(await ocean_bundle())}

        # auto: compare nearest hydro level vs ocean level distance
        h_st = await _obs_nearest_station(self.session, HYDRO_BASE, 3, lat, lon, manual_id)
        o_st = await _obs_nearest_station(self.session, OCEAN_BASE, 6, lat, lon, manual_id)
        h_d = (h_st or {}).get("_distance_km", 9999) or 9999
        o_d = (o_st or {}).get("_distance_km", 9999) or 9999
        if h_st and h_d <= o_d:
            return {**out, **(await hydro_bundle())}
        if o_st:
            return {**out, **(await ocean_bundle())}
        if h_st:
            return {**out, **(await hydro_bundle())}
        return out

    def water_bundle(self) -> dict[str, Any]:
        """Latest water observation fields for sensors."""
        return self._cached_bundle("water", self._compute_water)

    def _compute_water(self, data: dict[str, Any]) -> dict[str, Any]:
        """Compute water observation fields."""
        return dict(data.get("water") or {})

    async def _async_fetch_ice(
        self, lat: float, lon: float, manual_id: str | None
    ) -> dict[str, Any]:
        """Ice thickness from hydroobs (param 7); seasonal archive data."""
        out: dict[str, Any] = {
            "ice_thickness": None,
            "ice_station": None,
            "ice_station_distance": None,
            "ice_observed_at": None,
            "ice_status": "Ingen isdata",
            "station_id": None,
        }
        st = await _obs_nearest_station(
            self.session, HYDRO_BASE, 7, lat, lon, manual_id
        )
        if not st:
            return out
        key = str(st.get("key"))
        thickness, date_ms = await _obs_latest_value(
            self.session, HYDRO_BASE, 7, key, allow_archive=True
        )
        out["water_station"] = None  # noqa: keep keys stable
        out["ice_station"] = st.get("name") or key
        out["ice_station_distance"] = st.get("_distance_km")
        out["station_id"] = key
        out["ice_thickness"] = thickness
        if date_ms:
            try:
                observed = dt_util.utc_from_timestamp(date_ms / 1000.0)
                local = dt_util.as_local(observed)
                out["ice_observed_at"] = local.strftime("%Y-%m-%d %H:%M")
                age_days = (dt_util.utcnow() - observed).total_seconds() / 86400
                if thickness is not None and age_days <= 120:
                    out["ice_status"] = f"Istjocklek {thickness:g} cm"
                elif thickness is not None:
                    out["ice_status"] = f"Senaste mätning {out['ice_observed_at']} ({thickness:g} cm)"
                else:
                    out["ice_status"] = "Ingen aktuell isdata"
            except Exception:  # noqa: BLE001
                out["ice_observed_at"] = str(date_ms)
                out["ice_status"] = "Isdata tillgänglig"
        elif thickness is not None:
            out["ice_status"] = f"Istjocklek {thickness:g} cm"
        return out

    def ice_bundle(self) -> dict[str, Any]:
        return self._cached_bundle("ice", self._compute_ice)

    def _compute_ice(self, data: dict[str, Any]) -> dict[str, Any]:
        return dict(data.get("ice") or {})

    def status_bundle(self) -> dict[str, Any]:
        """Freshness/status for the dedicated status sensor."""
        return self._cached_bundle("status", self._compute_status)

    def _compute_status(self, data: dict[str, Any]) -> dict[str, Any]:
        """Compute data status, age and original success timestamps."""
        if not data.get("timeSeries"):
            status = DATA_STATUS_NONE
        elif _data_is_stale(data):
            status = DATA_STATUS_STALE
        else:
            status = DATA_STATUS_CURRENT
        return {
            "data_status": status,
            "data_status_last_success": _format_local_time(data.get("last_success_at")),
            "data_status_fetched_at": _format_local_time(data.get("fetched_at")),
            "data_status_age_minutes": _cache_age_minutes(data),
            "data_status_ttl_minutes": CACHE_MAX_AGE_MINUTES,
            "data_status_last_success_iso": data.get("last_success_at"),
            "data_status_fetched_at_iso": data.get("fetched_at"),
        }

