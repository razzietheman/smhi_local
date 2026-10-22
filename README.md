# SMHI Local

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Home Assistant-integration för **SMHI Open Data** (kategori **snow1g**, punktprognos).  
Bygger `weather`-entitet + sensorer direkt från API:ets `timeSeries`, med **minne av senaste giltiga prognos** så dashboards inte blir `unavailable` vid tillfälliga nätverks-/API-fel.

**Attribution:** SMHI Open Data Powered by Rasmus

---

## Innehåll

1. [Installation & plats (lat/lon)](#installation--plats-latlon)
2. [Teknisk arkitektur](#teknisk-arkitektur)
3. [Hur cachen fungerar](#hur-cachen-fungerar)
4. [Närmaste prognospunkt](#närmaste-prognospunkt)
5. [Weather-entitet](#weather-entitet)
6. [Aktuella sensorer](#aktuella-sensorer)
7. [Härledda sensorer](#härledda-sensorer)
8. [Entity-id och namngivning](#entity-id-och-namngivning)
9. [Options](#options)
10. [API-referens](#api-referens)

---

## Installation & plats (lat/lon)

### Config flow

Vid **Lägg till integration → SMHI Local** fylls formuläret i automatiskt med Home Assistants egna koordinater:

| Fält | Källa | Krav |
|------|--------|------|
| **Namn** | Default `SMHI` | Fritext – blir enhetsnamn i HA |
| **Latitud** | `hass.config.latitude` | Valideras som latitud |
| **Longitud** | `hass.config.longitude` | Valideras som longitud |

Det är samma värden som **Inställningar → System → Allmänt → Plats** (och som `zone.home` normalt speglar). Du kan ändra till valfri punkt där SMHI har täckning.

### Unique id per plats

```text
smhi_{lat avrundad 3 decimaler}_{lon avrundad 3 decimaler}
```

Samma plats kan inte läggas till två gånger. Vill du ha flera orter: skapa flera config entries med olika koordinater.

### Anrop till SMHI

Koordinaterna sparas i config entry och används vid varje poll:

```text
https://opendata-download-metfcst.smhi.se/api/category/snow1g/version/1/geotype/point/lon/{lon}/lat/{lat}/data.json
```

- `lat` / `lon` avrundas till **4 decimaler** i URL:en (~11 m precision).
- Inget API-nyckel behövs (öppen data).
- Timeout: 20 sekunder.
- Delad `aiohttp`-session via Home Assistants `async_get_clientsession`.

**Exempel (Skövde):**  
`.../lon/13.8451/lat/58.3912/data.json`

SMHI interpolerar till närmaste modellpunkt; det är **punktprognos**, inte stationsobservation.

---

## Teknisk arkitektur

```text
┌─────────────────┐     poll (default 300 s)     ┌──────────────────────┐
│  Config Entry   │ ───────────────────────────► │  SmhiLocalCoordinator│
│  lat, lon, name │                              │  _async_update_data  │
└─────────────────┘                              └──────────┬───────────┘
                                                            │
                     HTTP GET snow1g                        ▼
                                              ┌─────────────────────────┐
                                              │  SMHI Open Data API     │
                                              │  timeSeries[]           │
                                              └──────────┬──────────────┘
                                                         │
                         lyckad / misslyckad             ▼
                                              ┌─────────────────────────┐
                                              │  data + _last_good      │
                                              │  { timeSeries, … }      │
                                              └──────────┬──────────────┘
                     ┌───────────────────────────────────┼──────────────────┐
                     ▼                                   ▼                  ▼
            current_bundle()                    derived_bundle()      weather.py
            närmaste punkt                      12 h / 48 h scan      hourly/daily
                     │                                   │
                     ▼                                   ▼
              SENSOR_TYPES                      DERIVED_SENSOR_TYPES
```

- **Platforms:** `sensor`, `weather`
- **Coordinator:** en per config entry; alla entiteter delar samma data
- **Normalisering:** snow1g-fält (t.ex. `air_temperature`) mappas till interna nycklar; äldre pmp3g-format stöds fortfarande om det skulle dyka upp

---

## Hur cachen fungerar

Problemet med ren REST + templates: när SMHI eller nätet strular blir `sensor.smhi_prognos_*` **unavailable** och hela väderkortet tomt.

**SMHI Local** speglar idén bakom `sensor.smhi_prognos_latest_valid`, men i Python i coordinators minne:

### Flöde vid varje uppdatering

1. Bygg URL med entry:s lat/lon.
2. `GET` mot SMHI.
3. **HTTP ≠ 200**, **nätverksfel**, **oväntat fel** eller **tom `timeSeries`**:
   - Om `_last_good` finns → **returnera den** (ingen `UpdateFailed` utåt).
   - Sensorer och weather fortsätter visa senaste lyckade prognos.
   - Logg: warning/error, men UI flimrar inte.
4. **Lyckat svar:**
   - Normalisera varje punkt i `timeSeries`.
   - Spara:
     ```python
     {
       "timeSeries": [...],
       "fetched_at": "<ISO nu>",
       "latitude": lat,
       "longitude": lon,
     }
     ```
   - Sätt `self._last_good = result` och returnera samma objekt till coordinators `data`.

### Vad som läser cachen

Både aktuella och härledda värden gör:

```python
data = self.data or self._last_good or {}
series = data.get("timeSeries") or []
```

Alltså: om coordinators `data` av någon anledning är tom, faller man tillbaka till `_last_good`.

### Begränsningar

| Aspekt | Beteende |
|--------|----------|
| **Var** | Endast i RAM (processminne) |
| **Efter omstart av HA** | Cache töms; första lyckade hämtningen fyller den igen |
| **Första start utan nät** | `ConfigEntryNotReady` – integrationen startar inte förrän första lyckade poll |
| **Åldrande data** | Visar sista giltiga prognos tills ny hämtning lyckas (kan vara flera intervall gammal) |

Det motsvarar template-mönstret *"spara last good attributes vid unavailable"*, men centralt för alla sensorer och weather.

---

## Närmaste prognospunkt

SMHI levererar en tidsserie (timmar, senare grövre steg). **Aktuellt väder** är inte "observation nu", utan den punkt i `timeSeries` vars `time` ligger **närmast `now()`** (minsta absoluta tidsskillnad).

Alla **aktuella sensorer** (temperatur, vind, sikt, …) och weather-state bygger på den punkten.

---

## Weather-entitet

| Egenskap | Källa |
|----------|--------|
| `condition` | Wsymb2 `symbol_code` → HA-nyckel (`sunny`, `cloudy`, `rainy`, …), natt via `sun.sun` när möjligt |
| `temperature` | `air_temperature` |
| `humidity` | `relative_humidity` |
| `pressure` | `air_pressure_at_mean_sea_level` |
| `wind_speed` | `wind_speed` |
| `wind_bearing` | `wind_from_direction` |
| `visibility` | `visibility_in_air` |
| Forecast hourly/daily | Byggs från hela (cachade) `timeSeries` |
| Attribution | `SMHI Open Data Powered by Rasmus` |

`condition` på weather **måste** vara engelska HA-nycklar. Svensk text finns på sensorn **Förhållande**.

---

## Aktuella sensorer

Värden från **närmaste** `timeSeries`-punkt (plus beräknade fält).

| Friendly name | Nyckel | Enhet | Beskrivning |
|---------------|--------|-------|-------------|
| **Temperatur** | `air_temperature` | °C | Lufttemperatur |
| **Känns som** | `feels_like` | °C | Upplevd temperatur (australiensisk formel: temp, fukt, vind) |
| **Luftfuktighet** | `relative_humidity` | % | Relativ fukt |
| **Lufttryck** | `air_pressure_at_mean_sea_level` | hPa | Tryck reducerat till havsnivå |
| **Vindhastighet** | `wind_speed` | m/s | Medelvind |
| **Vindby** | `wind_speed_of_gust` | m/s | Byvind |
| **Vindriktning** | `wind_direction_sv` | — | 16-strecks kompass på svenska (`Sydost`, `Nord-Nordväst`, …) från `wind_from_direction` |
| **Sikt** | `visibility_in_air` | km | Sikt i luft |
| **Nederbörd** | `precipitation_amount_mean` | mm/h | Medelnederbörd för steget |
| **Nederbördsrisk** | `probability_of_precipitation` | % | Sannolikhet för nederbörd |
| **Vädersymbol** | `symbol_code` | — | SMHI Wsymb2 (1–27) |
| **Förhållande** | `condition_sv` | — | Svensk label: Klart, Mulet, Regn, … |
| **Molntyp** | `cloud_type` | — | Klassning från låg/medel/hög molnfraktion + bas/topphöjd (t.ex. Stratocumulus, Cirrus) |
| **Molnmängd** | `cloud_cover_pct` | % | `(cloud_area_fraction / 8) × 100` (oktas → procent) |
| **Åskrisk nu** | `thunderstorm_probability` | % | Åsksannolikhet i aktuell punkt |
| **Risk för frusen nederbörd** | `probability_of_frozen_precipitation` | % | Frusen nederbörd i aktuell punkt |

### Molntyp (förenklad logik)

1. Alla nivåer 0 → `Klar himmel`
2. Stor vertikal utsträckning (bas < 3 km, tjocklek > 4 km) → Nimbostratus / Cumulonimbus (beroende på åska)
3. Dominerande nivå (låg / medel / hög) + molnbas/tjocklek → Cu, Sc, St, As, Ac, Ci, Cs, Cc, eller generellt "Låga/Medelhöga/Höga moln"

### Vindriktning (band)

Samma gränser som klassisk 16-punkts kompass (t.ex. 123,75–146,25° → **Sydost**).

---

## Härledda sensorer

Skannar **framtida** punkter i (cachad) `timeSeries`.

| Friendly name | Nyckel | Enhet | Logik |
|---------------|--------|-------|--------|
| **Nästa nederbördstyp** | `next_precip_type` | — | Första framtida punkt med `precipitation_amount_mean ≥ 0,1`. Typ från `predominant_precipitation_type_at_surface` (pcat 0–11). Snökoder + temp > 2 °C → **Regn**. Annars: Snö, Regnskurar, … Saknas → `Ingen nederbörd väntas` |
| **Nästa nederbördsmängd** | `next_precip_amount` | mm/h | `precipitation_amount_mean` för den punkten |
| **Nästa nederbördstid** | `next_precip_time` | — | Start–slut för sammanhängande period ≥ 0,1 mm. Exempel: `20:00 onsdag 21 oktober - 00:00 torsdag 22 oktober` eller `Ingen nederbörd` |
| **Nederbörd kommande 12h** | `precip_next_12h` | mm | Summa `precipitation_amount_mean` för punkter med `now ≤ t ≤ now+12h`, avrundat 1 decimal |
| **Åskrisk** | `thunder_risk_text` | — | Max `thunderstorm_probability` inom 12 h (+ Wsymb2 11/21). Text: `Ingen åskrisk` / `Liten\|Måttlig\|Hög åskrisk X% i kväll klockan 23` |
| **Åskrisk max %** | `thunder_risk_12h` | % | Numeriskt max i samma fönster |
| **Nästa dåliga sikt** | `next_bad_visibility` | — | Första punkt inom **48 h** med sikt **< 10 km**. Klass: Mycket dålig (<1) / Dålig (<4) / Måttlig (<10). Format: `Måttlig sikt (9.5 km), onsdag 21 oktober kl 19:00`. Annars `God sikt` |
| **Snöandel nästa nederbörd** | `next_snow_share` | — | Vid nästa nederbörd: rent regn → `Ej tillämpligt`; annars `precipitation_frozen_part` → `Allt regn` / `Allt snö` / `XX% snö` / `Ej tillämpligt` |

### Åskrisk – nivåer

| Max % | Textnivå |
|-------|----------|
| 0 | Ingen åskrisk |
| 1–24 | Liten åskrisk |
| 25–49 | Måttlig åskrisk |
| ≥ 50 | Hög åskrisk |

Relativ tid: `i natt` / `på förmiddag` / `i eftermiddag` / `i kväll` (+ i morgon / veckodag).

### Nederbördstyp (pcat)

| Kod | Text |
|-----|------|
| 0 | Ingen nederbörd |
| 1 | Snö |
| 2 | Snöblandat regn |
| 3 | Regn |
| 4 | Duggregn |
| 5 | Underkylt regn |
| 6 | Underkylt duggregn |
| 7 | Snöbyar |
| 8 | Regnskurar |
| 9 | Kraftiga regnskurar |
| 10 | Snöblandade skurar |
| 11 | Kraftiga snöbyar |

---

## Entity-id och namngivning

- Enhetsnamn = **Namn** i config flow (default `SMHI`).
- Sensorer använder `has_entity_name`:  
  `sensor.smhi_temperatur`, `sensor.smhi_vindriktning`, …  
  (exakt slug beror på HA:s översättning av friendly name).
- Weather: typiskt `weather.smhi` eller `weather.<ditt_namn>`.
- Unique id per sensor: `{config_entry_id}_{key}` – stabilt vid omstart.

---

## Options

Efter setup: **Integrationen → Konfigurera**

| Alternativ | Default | Intervall | Effekt |
|------------|---------|-----------|--------|
| **Uppdateringsintervall** | 300 s | 60–3600 s | `DataUpdateCoordinator.update_interval` – hur ofta SMHI pollas |

Ändring triggar reload av config entry.

---

## API-referens

| | |
|--|--|
| **Bas** | `https://opendata-download-metfcst.smhi.se` |
| **Kategori** | `snow1g` (ersätter pensionerad `pmp3g`) |
| **Geotyp** | `point` |
| **Svar** | JSON med `timeSeries[]` – varje element `time` + `data{…}` |
| **Auth** | Ingen |
| **Licens / villkor** | SMHI Open Data – ange källa; denna integration sätter attribution i HA |

Dokumentation: [SMHI Open Data](https://opendata.smhi.se)

---

## Kort jämförelse med REST + templates

| | REST + templates | SMHI Local |
|--|------------------|------------|
| Hämtning | `rest`-sensor + scan_interval | Coordinator + options-intervall |
| Avbrott | Enskilda templates → unavailable | `_last_good` → oförändrad UI |
| Aktuellt värde | Jinja-loop närmaste tid | `_nearest_entry()` i Python |
| Weather | Template-weather eller manuellt kort | Native `weather` + forecast |
| Underhåll | ~20 template-sensorer | En integration, en plats |

---

## Licens

MIT – se [LICENSE](LICENSE).  
Prognosdata tillhör SMHI; integrationen är **SMHI Open Data Powered by Rasmus**.
