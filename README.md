# SMHI Local

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.4.1-blue.svg)](https://github.com/razzietheman/smhi_local)

Home Assistant-integration för **SMHI Open Data**: punktprognos (**snow1g**), **brandrisk** (fwif1g) och **vädervarningar** (IBWW).  
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
11. [Varningar (IBWW) – från 1.4.1](#varningar-ibww--från-141)
12. [Options](#options)
13. [Jämförelse med officiella SMHI](#jämförelse-med-officiella-smhi)
14. [API-referens](#api-referens)
15. [Ändringslogg (kort)](#ändringslogg-kort)

---

## Vad gör integrationen?

| Källa | Vad du får |
|--------|------------|
| **snow1g** punktprognos | Weather + temp, vind, sikt, moln, nederbörd, åska, “nästa regn”, 12 h-summa, … |
| **fwif1g** dygn | Brandrisk (FWI), gräsbrand, spridning, m.m. |
| **IBWW** varningar | Aktiva varningar/meddelanden, **filtrerade till ditt län** (1.4.1) |

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
        └── GET IBWW    → warning.json (hela landet, filtreras lokalt)
        │
        ├── lyckad snow1g → spara _last_good
        └── misslyckad snow1g → returnera _last_good (fire/warnings kan ändå uppdateras)
        │
        ├── current_bundle()   → aktuella fält
        ├── derived_bundle()   → nästa nederbörd, 12 h, åska, sikt
        ├── fire_bundle()
        ├── warnings_bundle()  → länsfilter
        └── weather entity     → hourly / daily forecast
```

- **Platforms:** `sensor`, `weather`
- **Normalisering:** snow1g-fält → interna nycklar (äldre pmp3g stöds om det dyker upp)

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

Motsvarar template-idén *latest_valid*, men centralt för alla prognosentiteter.

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
| **Nästa nederbördstid** | `next_precip_time` | Start–slut, t.ex. `20:00 onsdag 21 oktober - 00:00 torsdag 22 oktober` |
| **Nederbörd kommande 12h** | `precip_next_12h` | Summa mean, 1 decimal |
| **Åskrisk** | `thunder_risk_text` | Max 12 h: *Liten åskrisk 4% i kväll klockan 23* |
| **Åskrisk max %** | `thunder_risk_12h` | Numeriskt |
| **Nästa dåliga sikt** | `next_bad_visibility` | Första &lt; 10 km inom 48 h, med klass + datum |
| **Snöandel nästa nederbörd** | `next_snow_share` | *Allt snö* / *XX% snö* / *Ej tillämpligt* |

**Entity-id (exempel):** `sensor.smhi_nasta_nederbordstyp` – inte det gamla template-namnet `sensor.smhi_nasta_nederbord`.

### Nederbördstyp (pcat)

| Kod | Text |
|-----|------|
| 0 | Ingen nederbörd |
| 1 | Snö |
| 2 | Snöblandat regn |
| 3 | Regn |
| 4 | Duggregn |
| 5–6 | Underkylt regn / duggregn |
| 7–11 | Snöbyar, regnskurar, kraftiga varianter, …

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
| Initial spridning (ISI) | |
| Bränsleupplag (BUI) | |
| Fint bränsle (FFMC) | |
| Duff moisture (DMC) | |
| Drought code (DC) | |
| **Gräsbrandsrisk** | Text (eller ej tillämpligt / snötäcke) |
| Potentiell spridningshastighet | m/min |
| Skogstorkt index | |

---

## Varningar (IBWW) – från 1.4.1

API: `https://opendata-download-warnings.smhi.se/ibww/api/version/1/warning.json`  
(returnerar **hela Sverige** – filtrering sker i integrationen.)

| Sensor | Innehåll |
|--------|----------|
| **Varningar** | Sammanfattning, t.ex. `1 aktiv · Meddelande: Risk för vattenbrist (Västra Götalands län)` |
| **Antal varningar** | Antal efter filter |

**Attribut:** `warnings` (lista), `filter_area` (aktivt län).

### Länsfilter (1.4.1)

| Inställning | Beteende |
|-------------|----------|
| **Auto** (default) | Län från lat/lon via ungefärliga bounding boxes (Skövde → *Västra Götalands län*) |
| **Varningsområde** i options | Fritext, t.ex. `Västra Götalands län` |
| `all` / `alla` | Ingen filter – hela landet |

Matchar `areaName` och `affectedAreas` (delsträng, skiftlägesokänsligt).

**Uppgradering från 1.4.0:** Ladda om integrationen och sätt *Varningsområde* under Konfigurera om auto inte räcker.

---

## Options

*Integrationen → Konfigurera*

| Alternativ | Default | Beskrivning |
|------------|---------|-------------|
| **Uppdateringsintervall** | 300 s | 60–3600 – hur ofta coordinator pollar |
| **Varningsområde** | auto från lat/lon | Län-namn, eller `all` för hela Sverige |

Ändring laddar om config entry.

---

## Jämförelse med officiella SMHI

| | **Core SMHI** | **SMHI Local** |
|--|---------------|----------------|
| Underhåll | Home Assistant | Community / detta repo |
| Weather + forecast | daily / hourly / twice-daily | hourly + daily |
| Brandrisk (FWI) | Ja | Ja (fwif1g) |
| Varningar | Nej (separata custom) | Ja, **länsfiltrerade** |
| Svenska “premium”-texter (nästa regn, åskrisk-mening, molntyp) | Bygg själv | Inbyggt |
| Cache vid API-glitch | Standard HA | Explicit `_last_good` för prognos |
| Poll-intervall | ~30 min | Valbart |

Samma datakälla (SMHI Open Data) – olika lager ovanpå.

---

## API-referens

| Tjänst | URL-mönster |
|--------|-------------|
| Prognos | `…/snow1g/version/1/geotype/point/lon/{lon}/lat/{lat}/data.json` |
| Brandrisk | `…/fwif1g/version/1/daily/geotype/point/lon/{lon}/lat/{lat}/data.json` |
| Varningar | `https://opendata-download-warnings.smhi.se/ibww/api/version/1/warning.json` |

- Auth: ingen  
- Villkor: [SMHI Open Data](https://opendata.smhi.se)  
- Attribution i HA: **SMHI Open Data Powered by Rasmus**

---

## Kort jämförelse med REST + templates

| | REST + templates | SMHI Local |
|--|------------------|------------|
| Hämtning | rest + scan_interval | Coordinator + options |
| Avbrott | templates → unavailable | `_last_good` |
| Nästa nederbörd / åska / sikt | Jinja | Färdiga sensorer |
| Brandrisk + varningar | Egna anrop | Inbyggt |
| Underhåll | Många UI-templates | En integration |

---

## Ändringslogg (kort)

### 1.4.1
- Länsfilter för IBWW-varningar (auto från koordinater + options **Varningsområde**)
- Attribut `filter_area`
- Tomt resultat: *Inga aktiva varningar i &lt;län&gt;*

### 1.4.0
- Brandrisk (fwif1g), varningar (IBWW)
- Fler snow1g-fält: ensemble-nederbörd, molnbas/nivåer, metadata

### 1.3.x
- Grund: snow1g, weather, härledda sensorer, last-good-cache

---

## Licens

MIT – se [LICENSE](LICENSE).  
Prognos-, brandrisk- och varningsdata tillhör SMHI; integrationen är **SMHI Open Data Powered by Rasmus**.
