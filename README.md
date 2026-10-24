# SMHI Local

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.4.3-blue.svg)](https://github.com/razzietheman/smhi_local)

Home Assistant-integration för **SMHI Open Data**: punktprognos (**snow1g**), brandrisk (**fwif1g**), vädervarningar (**IBWW**), samt valfri hav-, sjö- och isdata (**hydroobs** / **ocobs** / **iceobs**).  
Ger `weather`-entitet + sensorer med **cache av senaste giltiga prognos**, så dashboards inte blir `unavailable` vid tillfälliga nätverks-/API-fel.

**Attribution:** SMHI Open Data Powered by Rasmus

---

## Innehåll

1. [Vad gör integrationen?](#vad-gör-integrationen)
2. [Installation](#installation)
3. [Plats (lat/lon)](#plats-latlon)
4. [Teknisk arkitektur](#teknisk-arkitektur)
5. [Cache (last good)](#cache-last-good)
6. [Weather-entitet](#weather-entitet)
7. [Aktuella sensorer (snow1g)](#aktuella-sensorer-snow1g)
8. [Härledda sensorer](#härledda-sensorer)
9. [Metadata](#metadata)
10. [Brandrisk (fwif1g)](#brandrisk-fwif1g)
11. [Varningar (IBWW) – punkt-i-polygon](#varningar-ibww--punkt-i-polygon)
12. [Hav-, sjö- och isdata (valfritt)](#hav--sjö--och-isdata-valfritt)
13. [Options](#options)
14. [Jämförelse med officiella SMHI](#jämförelse-med-officiella-smhi)
15. [API-referens](#api-referens)
16. [Ändringslogg (kort)](#ändringslogg-kort)

---

## Vad gör integrationen?

| Källa | Vad du får |
|-------|------------|
| **snow1g** punktprognos | Weather + temp, vind, sikt, moln, nederbörd, åska, “nästa regn”, 12 h-summa, … |
| **fwif1g** dygn | Brandrisk (FWI), gräsbrand, spridning, m.m. |
| **IBWW** varningar | Aktiva varningar/meddelanden, **filtrerade med punkt-i-polygon** |
| **hydroobs** / **ocobs** | Valfritt: vattenstånd, vattentemperatur, våghöjd från närmaste station |
| **iceobs** | Valfritt: istjocklek, isbeskaffenhet och snötäcke på is |

Allt pollas av en gemensam **DataUpdateCoordinator**. Prognosen har **`_last_good`-cache** i minnet.

---

## Installation

### HACS (rekommenderas)

1. HACS → Integrations → ⋮ → *Custom repositories*
2. URL till ditt repo, kategori **Integration**
3. Installera **SMHI Local** → starta om Home Assistant
4. *Inställningar → Enheter och tjänster → Lägg till integration → SMHI Local*

### Manuellt

Kopiera `custom_components/smhi_local` till din HA-config och starta om.

---

## Plats (lat/lon)

### Config flow

| Fält | Default | Beskrivning |
|------|---------|-------------|
| **Namn** | `SMHI` | Enhetsnamn i HA |
| **Latitud** | `hass.config.latitude` | HA-platsen |
| **Longitud** | `hass.config.longitude` | HA-platsen |

Samma koordinater som *System → Allmänt → Plats* / `zone.home`. Valfri punkt inom SMHI:s täckning fungerar.

**Unique id:** `smhi_{lat:.3f}_{lon:.3f}` – en config entry per plats.

### API-anrop (exempel Skövde)

```text
…/snow1g/…/point/lon/13.8451/lat/58.3912/data.json
…/fwif1g/…/daily/…/point/lon/13.8451/lat/58.3912/data.json
```

- Lat/lon avrundas till **4 decimaler** i URL (~11 m).
- Ingen API-nyckel.
- Timeout 20 s, delad `aiohttp`-session.

SMHI svarar med närmaste **modellpunkt** (punktprognos, inte observationsstation).

---

## Teknisk arkitektur

```text
Config entry (lat, lon, name, options)
        │
        ▼  poll (default 300 s)
SmhiLocalCoordinator._async_update_data
        │
        ├── GET snow1g  → timeSeries, createdTime, geometry
        ├── GET fwif1g  → brandrisk (närmaste dygn)
        ├── GET IBWW    → warning.json (punkt-i-polygon mot lat/lon)
        ├── GET water   → hydroobs / ocobs (närmaste station via Haversine)
        └── GET ice     → iceobs (valfri isdata för vinterhalvåret)
        │
        ├── lyckad snow1g → spara _last_good
        └── misslyckad snow1g → returnera _last_good (övrigt kan uppdateras ovanpå)
        │
        ├── current_bundle()   → aktuella fält
        ├── derived_bundle()   → nästa nederbörd, 12 h, åska, sikt
        ├── fire_bundle()
        ├── warnings_bundle()  → polygon-filtrerade varningar
        ├── water_bundle()     → vattenstånd, temp, våghöjd
        ├── ice_bundle()       → istjocklek, isbeskaffenhet
        └── weather entity     → hourly / daily forecast
```

- **Platforms:** `sensor`, `weather`
- **Normalisering:** snow1g-fält → interna nycklar

---

## Cache (last good)

Vid HTTP-fel, nätverksfel eller tom `timeSeries` för **prognosen**:

- Om `_last_good` finns → den returneras (sensorer/weather fortsätter visa data).
- Logg skrivs, UI flimrar inte till `unavailable`.

```python
data = self.data or self._last_good or {}
```

| Begränsning | Beteende |
|-------------|----------|
| Lagring | Endast RAM |
| HA-omstart | Cache töms |
| Första start utan nät | `ConfigEntryNotReady` |
| Gammal data | Visas tills ny lyckad poll |

**Aktuellt väder** = tidpunkt i `timeSeries` närmast `now()` (minsta `|t − now|`).

---

## Weather-entitet

| Egenskap | Källa |
|----------|--------|
| `condition` | Wsymb2 → HA (`sunny`, `cloudy`, `rainy`, …), natt via `sun.sun` |
| `temperature` / `humidity` / `pressure` | snow1g |
| `wind_speed` / `wind_bearing` | snow1g |
| `visibility` | snow1g |
| Forecast | hourly + daily från cachad `timeSeries` |
| Attribution | `SMHI Open Data Powered by Rasmus` |

Svensk condition-text: sensorn **Förhållande**.

---

## Aktuella sensorer (snow1g)

Från **närmaste** prognospunkt.

| Friendly name | Nyckel | Enhet | Beskrivning |
|---------------|--------|-------|-------------|
| Temperatur | `air_temperature` | °C | |
| Känns som | `feels_like` | °C | Upplevd temp (temp, fukt, vind) |
| Luftfuktighet | `relative_humidity` | % | |
| Lufttryck | `air_pressure_at_mean_sea_level` | hPa | |
| Vindhastighet | `wind_speed` | m/s | |
| Vindby | `wind_speed_of_gust` | m/s | |
| Vindriktning | `wind_direction_sv` | — | Svensk kompass (Sydost, …) |
| Vindriktning grader | `wind_from_direction` | ° | Numerisk bäring |
| Sikt | `visibility_in_air` | km | |
| Nederbörd | `precipitation_amount_mean` | mm/h | |
| Nederbörd min / max / median | ensemble | mm/h | Osäkerhetsintervall |
| Nederbördsrisk | `probability_of_precipitation` | % | |
| Vädersymbol | `symbol_code` | — | Wsymb2 1–27 |
| Förhållande | `condition_sv` | — | Klart, Mulet, Regn, … |
| Molntyp | `cloud_type` | — | Cu, Sc, Cb, … |
| Molnmängd | `cloud_cover_pct` | % | oktas → % |
| Lågt / Medelhögt / Högt molntäcke | | % | Per nivå |
| Molnbas / Molntopp | | m | |
| Åskrisk nu | `thunderstorm_probability` | % | |
| Risk för frusen nederbörd | `probability_of_frozen_precipitation` | % | |

---

## Härledda sensorer

Skannar **framtida** punkter i (cachad) tidsserie.

| Friendly name | Nyckel | Logik |
|---------------|--------|--------|
| **Nästa nederbördstyp** | `next_precip_type` | Första punkt ≥ 0,1 mm; pcat (+ temp-override) |
| **Nästa nederbördsmängd** | `next_precip_amount` | mm/h för den punkten |
| **Nästa nederbördstid** | `next_precip_time` | Start–slut, t.ex. `20:00 onsdag … - 00:00 torsdag …` |
| **Nederbörd kommande 12h** | `precip_next_12h` | Summa mean, 1 decimal |
| **Åskrisk** | `thunder_risk_text` | Max 12 h: *Liten åskrisk 4% i kväll klockan 23* |
| **Åskrisk max %** | `thunder_risk_12h` | Numeriskt |
| **Nästa dåliga sikt** | `next_bad_visibility` | Första &lt; 10 km inom 48 h, med klass + datum |
| **Snöandel nästa nederbörd** | `next_snow_share` | *Allt snö* / *XX% snö* / *Ej tillämpligt* |

---

## Metadata

| Friendly name | Innehåll |
|---------------|----------|
| Prognos skapad | `createdTime` (lokal tid) |
| Prognos referenstid | `referenceTime` |
| Modellpunkt | Faktisk grid `lat, lon` från `geometry` |

---

## Brandrisk (fwif1g)

Dygnsprognos, närmaste `validTime` till nu.

| Friendly name | Beskrivning |
|---------------|-------------|
| **Brandrisk** | Text: Liten risk … Extremt stor risk (FWI-index) |
| FWI-värde / FWI-index | Numeriskt |
| Initial spridning (ISI), Bränsleupplag (BUI), m.fl. | FWI-komponenter |
| **Gräsbrandsrisk** | Textnivå |
| Potentiell spridningshastighet | m/min |

---

## Varningar (IBWW) – punkt-i-polygon

API: `https://opendata-download-warnings.smhi.se/ibww/api/version/1/warning.json`  
Filtreras med **ray-casting** mot varje `warningAreas[].area.geometry` (GeoJSON). Din lat/lon måste ligga inuti zonen för att varningen ska visas.

| Sensor | Innehåll |
|--------|----------|
| **Varningar** | Sammanfattning, t.ex. `1 aktiv · Meddelande: Risk för vattenbrist (Västra Götalands län)` |
| **Antal varningar** | Antal aktiva efter polygonfilter |

**Attribut:** `warnings`, `filter_area`, `filter_mode` (`point_in_polygon`).

---

## Hav-, sjö- och isdata (valfritt)

Av som standard – aktiveras under *Konfigurera*. Använder Haversine-beräkning för att automatiskt hitta närmaste aktiva mätstation baserat på din lat/lon.

| Sensor | Enhet | Beskrivning |
|--------|-------|-------------|
| **Vattenstånd** | cm | Från närmaste sjö- (`hydroobs`) eller havsstation (`ocobs`) |
| **Vattentemperatur** | °C | Mätvärde från stationen |
| **Våghöjd** | m | Signifikant våghöjd (endast havstationer) |
| **Vattenstation** | — | Namn på aktiv mätstation |
| **Avstånd till vattenstation** | km | Fågelvägen till stationen |
| **Istjocklek** | cm | Från närmaste ismätning (`iceobs`, vintertid) |
| **Isbeskaffenhet** | — | Textbeskrivning (t.ex. kärnis, stampis) |

---

## Options

*Integrationen → Konfigurera*

| Alternativ | Default | Beskrivning |
|------------|---------|-------------|
| **Uppdateringsintervall** | 300 s | 60–3600 s |
| **Varningsområde** | tomt | Tomt = punkt-i-polygon. `all` = hela Sverige |
| **Aktivera hav- och sjödata** | av | På för hydro/ocobs |
| **Typ av vattenstation** | auto | auto / hydro / ocean / av |
| **Manuellt stations-ID** | tomt | Åsidosätter automatisk närmaste-station |

---

## Jämförelse med officiella SMHI

| | **Core SMHI** | **SMHI Local** |
|--|---------------|----------------|
| Weather + forecast | daily / hourly / twice-daily | hourly + daily |
| Brandrisk (FWI) | Ja | Ja (fwif1g) |
| Varningar | Nej | Ja, **punkt-i-polygon** |
| Hav / sjö / is-observationer | Nej | Valfritt (`hydroobs`, `ocobs`, `iceobs`) |
| Svenska “premium”-sensorer | Bygg själv | Inbyggt |
| Cache vid API-glitch | Standard HA | Explicit `_last_good` för prognos |

---

## API-referens

| Tjänst | URL-mönster |
|--------|-------------|
| Prognos | `…/snow1g/version/1/geotype/point/lon/{lon}/lat/{lat}/data.json` |
| Brandrisk | `…/fwif1g/version/1/daily/geotype/point/lon/{lon}/lat/{lat}/data.json` |
| Varningar | `https://opendata-download-warnings.smhi.se/ibww/api/version/1/warning.json` |
| Sjö/vattendrag | `https://opendata-download-hydroobs.smhi.se/api/version/1.0/…` |
| Hav | `https://opendata-download-ocobs.smhi.se/api/version/1.0/…` |
| Is | `https://opendata-download-iceobs.smhi.se/api/version/1.0/…` |

- Auth: ingen  
- Villkor: [SMHI Open Data](https://opendata.smhi.se)  
- Attribution i HA: **SMHI Open Data Powered by Rasmus**

---

## Ändringslogg (utdrag)

### 1.4.3
- Stöd för **isobservationer (`iceobs`)** samt hav/sjö-data (`ocobs`/`hydroobs`) med automatisk Haversine-sökning.
- Options-flöde uppdaterat med korta etiketter och `data_description`.
- Punkt-i-polygon som standard för nya installationer av IBWW-varningar.

### 1.4.2
- Varningar filtreras med **punkt-i-polygon** mot SMHI:s GeoJSON-zoner.

### 1.4.0
- Brandrisk (fwif1g) och IBWW-varningar tillagda.

---

## Licens

MIT – se [LICENSE](LICENSE).  
Prognos-, brandrisk-, varnings- och observationsdata tillhör SMHI; integrationen är **SMHI Open Data Powered by Rasmus**.
