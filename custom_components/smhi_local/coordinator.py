"""DataUpdateCoordinator for SMHI Local – snow1g fetch, cache, derived fields."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from aiohttp import ClientError, ClientSession

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    API_FIRE_URL,
    API_URL,
    API_WARNINGS_URL,
    BAD_VISIBILITY_KM,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    FWI_INDEX_SV,
    GRASSFIRE_SV,
    PARAM_MAP,
    PCAT_LABELS,
    PRECIP_THRESHOLD_MM,
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


def _is_night(dt: Any, hass: HomeAssistant) -> bool:
    """Night from sun.sun elevation when possible."""
    try:
        elev = hass.states.get("sun.sun")
        if elev is not None and elev.state in ("below_horizon", "above_horizon"):
            return elev.state == "below_horizon"
    except Exception:  # noqa: BLE001
        pass
    hour = dt_util.as_local(dt).hour if dt else dt_util.now().hour
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
        try:
            tp = float((e.get("data") or {}).get("precipitation_amount_mean") or 0)
        except (TypeError, ValueError):
            tp = 0.0
        if tp >= PRECIP_THRESHOLD_MM and not raining:
            start_iso = e["time"]
            raining = True
        if raining and tp >= PRECIP_THRESHOLD_MM:
            stop_iso = e["time"]
        if raining and tp < PRECIP_THRESHOLD_MM:
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
    """Degrees → Swedish compass label (same bands as template)."""
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
    """Relative time phrase matching premium weather report style."""
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
    wd = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"][
        dtl.weekday()
    ]
    if h < 6:
        if days == 0:
            return f"i natt klockan {hh}"
        if days == 1:
            return f"i morgon natt klockan {hh}"
        return f"på {wd} natt klockan {hh}"
    if h < 12:
        if days == 0:
            return f"på förmiddag klockan {hh}"
        if days == 1:
            return f"i morgon förmiddag klockan {hh}"
        return f"på {wd} förmiddag klockan {hh}"
    if h < 18:
        if days == 0:
            return f"i eftermiddag klockan {hh}"
        if days == 1:
            return f"i morgon eftermiddag klockan {hh}"
        return f"på {wd} eftermiddag klockan {hh}"
    if days == 0:
        return f"i kväll klockan {hh}"
    if days == 1:
        return f"i morgon kväll klockan {hh}"
    return f"på {wd} kväll klockan {hh}"



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
    # Show one decimal if needed, else strip trailing .0
    vis_s = f"{vis:.1f}".rstrip("0").rstrip(".") if vis != int(vis) else str(int(vis))
    # Match template style: always one decimal when float from API often is
    vis_s = f"{vis:g}" if vis == int(vis) else f"{vis:.1f}"
    return f"{label} ({vis_s} km), {_format_datum_kl(iso)}"


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

    @property
    def latitude(self) -> float:
        return float(self.entry.data[CONF_LATITUDE])

    @property
    def longitude(self) -> float:
        return float(self.entry.data[CONF_LONGITUDE])

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

    def current_bundle(self) -> dict[str, Any]:
        """Current values + condition from nearest point."""
        data = self.data or self._last_good or {}
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
        raw_data["cloud_type"] = _cloud_type(raw_data)
        raw_data["wind_direction_sv"] = _wind_direction_sv(
            raw_data.get("wind_from_direction")
        )
        return raw_data

    def derived_bundle(self) -> dict[str, Any]:
        """Scan future series for next precip, 12h sum, thunder, bad visibility."""
        data = self.data or self._last_good or {}
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

            # Next precipitation (template: first future point with pmean >= 0.1)
            if not found_precip and ts >= now_ts:
                try:
                    pmean = float(d.get("precipitation_amount_mean") or 0)
                except (TypeError, ValueError):
                    pmean = 0.0
                if pmean >= PRECIP_THRESHOLD_MM:
                    found_precip = True
                    result["next_precip_type"] = _precip_type_label(d)
                    result["next_precip_amount"] = round(pmean, 2)
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

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch snow1g + fire + warnings; keep last good on failure."""
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
                    fire_ok = True
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

        if snow_ok:
            self._last_good = result
            return result

        if self._last_good:
            # merge newer fire/warnings onto last good snow if available
            merged = dict(self._last_good)
            if fire_ok:
                merged["fire"] = result["fire"]
            if warn_ok:
                merged["warnings"] = result["warnings"]
            merged["fetched_at"] = result["fetched_at"]
            self._last_good = merged
            return merged

        raise UpdateFailed("SMHI snow1g unavailable and no cached forecast")

    def meta_bundle(self) -> dict[str, Any]:
        """Forecast metadata for sensors."""
        data = self.data or self._last_good or {}
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
        data = self.data or self._last_good or {}
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

    def warnings_bundle(self) -> dict[str, Any]:
        """Summarise IBWW warnings (Sweden-wide list)."""
        data = self.data or self._last_good or {}
        warnings = data.get("warnings") or []
        if not warnings:
            return {
                "warnings_count": 0,
                "warnings_summary": "Inga aktiva varningar",
                "warnings_list": [],
            }

        level_rank = {"RED": 4, "ORANGE": 3, "YELLOW": 2, "MESSAGE": 1}
        items = []
        max_rank = 0
        max_label = "Meddelande"
        for w in warnings:
            event = (w.get("event") or {}).get("sv") or (w.get("event") or {}).get("en") or "?"
            areas = w.get("warningAreas") or []
            for a in areas:
                lvl = a.get("warningLevel") or {}
                code = lvl.get("code") or "MESSAGE"
                label = lvl.get("sv") or lvl.get("en") or code
                area = (a.get("areaName") or {}).get("sv") or "?"
                rank = level_rank.get(code, 0)
                if rank > max_rank:
                    max_rank = rank
                    max_label = label
                items.append(
                    {
                        "event": event,
                        "level": label,
                        "level_code": code,
                        "area": area,
                        "id": a.get("id"),
                    }
                )

        count = len(items)
        # short summary
        top = items[:3]
        bits = [f"{i['level']}: {i['event']} ({i['area']})" for i in top]
        extra = f" · +{count - 3} till" if count > 3 else ""
        summary = f"{count} aktiva · {max_label}"
        if bits:
            summary = f"{count} aktiva · " + " · ".join(bits) + extra

        return {
            "warnings_count": count,
            "warnings_summary": summary,
            "warnings_list": items,
        }
