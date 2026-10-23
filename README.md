# SMHI Local

[![Open your Home Assistant instance and repository inside a hacs repository.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=razzietheman&repository=smhi_local&category=integration)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Home Assistant-integration för **SMHI Open Data**: punktprognos (**snow1g**), brandrisk (**fwif1g**) och konsekvensbaserade varningar (**IBWW**).

Bygger en `weather`-entitet plus sensorer direkt från API:erna, med **minne av senaste giltiga prognos** så dashboards inte blir `unavailable` vid tillfälliga nätverks-/API-fel.

**Version:** 1.4.1  
**Attribution:** SMHI Open Data Powered by Rasmus

---

## Innehåll

1. [Vad integrationen gör](#vad-integrationen-gör)
2. [Installation](#installation)
3. [Plats (lat/lon)](#plats-latlon)
4. [Teknisk arkitektur](#teknisk-arkitektur)
5. [Cache av senaste giltiga prognos](#cache-av-senaste-giltiga-prognos)
6. [Weather-entitet](#weather-entitet)
7. [Aktuella sensorer (snow1g)](#aktuella-sensorer-snow1g)
8. [Härledda sensorer](#härledda-sensorer)
9. [Metadata](#metadata)
10. [Brandrisk (fwif1g)](#brandrisk-fwif1g)
11. [Varningar (IBWW) – länsfilter](#varningar-ibww--länsfilter)
12. [Options](#options)
13. [Jämförelse med officiella SMHI](#jämförelse-med-officiella-smhi)
14. [API-referens](#api-referens)
15. [Ändringslogg (utdrag)](#ändringslogg-utdrag)

---

## Vad integrationen gör

| Källa | Användning |
|-------|------------|
| **snow1g** punktprognos | Aktuellt väder, hourly/daily forecast, ~20+ sensorer |
| **fwif1g** dygn | Brandrisk / FWI-index och relaterade mått |
| **IBWW** varningar | Aktiva vädervarningar, **filtrerade till ditt län** |

En config entry (lat/lon) → en enhet i HA med weather + alla sensorer. Uppdateringsintervall är konfigurerbart (default 300 s).

---

## Installation

### HACS (rekommenderas)
1. Klicka på knappen högst upp för att öppna direkt i HACS, eller gör det manuellt: HACS → Integrations → ⋮ → *Custom repositories*
2. URL till repot, kategori **Integration**
3. Installera **SMHI Local** → starta om HA
4. *Inställningar → Enheter och tjänster → Lägg till integration → SMHI Local*

### Manuellt
Kopiera `custom_components/smhi_local` till din HA-config och starta om.

---

## Plats (lat/lon)

### Config flow
Vid setup fylls formuläret med Home Assistants egna koordinater:

| Fält | Källa |
|------|--------|
| **Namn** | Default `SMHI` (blir enhetsnamn) |
| **Latitud** | `hass.config.latitude` |
| **Longitud** | `hass.config.longitude` |

Samma värden som *System → Allmänt → Plats*. Du kan ange valfri punkt inom SMHI:s täckning.

### Unique id
```text
smhi_{lat:.3f}_{lon:.3f}
```
Samma plats kan inte läggas till två gånger. Flera orter = flera config entries.

### Anrop
Koordinater avrundas till **4 decimaler** i URL (~11 m):

```text
…/snow1g/…/point/lon/{lon}/lat/{lat}/data.json
…/fwif1g/version/1/daily/…/point/lon/{lon}/lat/{lat}/data.json
```

Inget API-nyckel. Timeout 20 s. Delad `aiohttp`-session via HA.

**Exempel (Skövde):** `lon/13.8451/lat/58.3912`

---

## Teknisk arkitektur

```text
Config entry (lat, lon, name, options)
        │
        ▼  poll (default 300 s)
SmhiLocalCoordinator
        │
        ├── GET snow1g  → timeSeries + createdTime/referenceTime/geometry
        ├── GET fwif1g  → brandrisk (närmaste dygn)
        └── GET IBWW    → varningslista (filtreras till län)
        │
        ├── lyckad snow1g → spara _last_good
        └── misslyckad    → returnera _last_good (fire/warnings kan uppdateras ovanpå)
        │
        ├── current_bundle()   → aktuella sensorer + weather state
        ├── derived_bundle()   → nästa nederbörd, 12 h, åska, sikt …
        ├── fire_bundle()      → FWI m.m.
        ├── warnings_bundle()  → filtrerade varningar
        └── meta_bundle()      → prognos skapad, modellpunkt
```

- **Platforms:** `sensor`, `weather`
- **Normalisering:** snow1g-fält → interna nycklar (äldre pmp3g stöds fortfarande om det dyker upp)

**Aktuellt väder** = tidpunkten i `timeSeries` med minsta `|t − now|` (närmaste prognospunkt).

---

## Cache av senaste giltiga prognos

Vid HTTP-fel, nätverksfel eller tom `timeSeries` returneras **`_last_good`** i RAM. Sensorer och weather fortsätter visa senaste lyckade prognos i stället för `unavailable`.

| Aspekt | Beteende |
|--------|----------|
| Lagring | Processminne (inte disk) |
| HA-omstart | Cache töms; fylls vid första lyckade poll |
| Första start utan nät | `ConfigEntryNotReady` |
| Åldrande data | Visas tills ny hämtning lyckas |

Motsvarar idén bakom en `latest_valid`-templatesensor, men centralt för alla entiteter.

---

## Weather-entitet

| Egenskap | Källa |
|----------|--------|
| `condition` | Wsymb2 → HA-nyckel (`sunny`, `cloudy`, …), natt via `sun.sun` när möjligt |
| `temperature` / `humidity` / `pressure` | snow1g |
| `wind_speed` / `wind_bearing` | snow1g |
| `visibility` | snow1g |
| Forecast hourly & daily | Hela (cachade) `timeSeries` |
| Attribution | `SMHI Open Data Powered by Rasmus` |

`condition` måste vara engelska HA-nycklar. Svensk text: sensorn **Förhållande**.

---

## Aktuella sensorer (snow1g)

Från närmaste prognospunkt:

| Friendly name | Nyckel | Enhet |
|---------------|--------|-------|
| Temperatur | `air_temperature` | °C |
| Känns som | `feels_like` | °C (temp + fukt + vind) |
| Luftfuktighet | `relative_humidity` | % |
| Lufttryck | `air_pressure_at_mean_sea_level` | hPa |
| Vindhastighet | `wind_speed` | m/s |
| Vindby | `wind_speed_of_gust` | m/s |
| Vindriktning | `wind_direction_sv` | — (t.ex. Sydost) |
| Vindriktning grader | `wind_from_direction` | ° |
| Sikt | `visibility_in_air` | km |
| Nederbörd | `precipitation_amount_mean` | mm/h |
| Nederbörd min / max / median | ensemble | mm/h |
| Nederbördsrisk | `probability_of_precipitation` | % |
| Vädersymbol | `symbol_code` | 1–27 |
| Förhållande | `condition_sv` | Klart, Mulet, … |
| Molntyp | `cloud_type` | t.ex. Stratocumulus |
| Molnmängd | `cloud_cover_pct` | % (oktas→%) |
| Lågt / Medelhögt / Högt molntäcke | | % |
| Molnbas / Molntopp | | m |
| Åskrisk nu | `thunderstorm_probability` | % |
| Risk för frusen nederbörd | `probability_of_frozen_precipitation` | % |

---

## Härledda sensorer

Skannar framtida punkter i cachad `timeSeries`:

| Friendly name | Nyckel | Beskrivning |
|---------------|--------|-------------|
| **Nästa nederbördstyp** | `next_precip_type` | Regn, Snö, … eller *Ingen nederbörd väntas* |
| **Nästa nederbördsmängd** | `next_precip_amount` | mm/h |
| **Nästa nederbördstid** | `next_precip_time` | t.ex. `20:00 onsdag 21 oktober - 00:00 torsdag 22 oktober` |
| **Nederbörd kommande 12h** | `precip_next_12h` | mm (summa) |
| **Åskrisk** | `thunder_risk_text` | *Liten åskrisk 4% i kväll klockan 23* |
| **Åskrisk max %** | `thunder_risk_12h` | % |
| **Nästa dåliga sikt** | `next_bad_visibility` | *Måttlig sikt (9.5 km), onsdag …* eller *God sikt* |
| **Snöandel nästa nederbörd** | `next_snow_share` | *Allt snö* / *Ej tillämpligt* / … |

Tröskel nederbörd: **≥ 0,1 mm**. Dålig sikt: **&lt; 10 km** inom 48 h.

> **OBS:** Gamla template-id `sensor.smhi_nasta_nederbord` motsvaras av **`sensor.smhi_nasta_nederbordstyp`** i integrationen.

---

## Metadata

| Friendly name | Innehåll |
|---------------|----------|
| Prognos skapad | `createdTime` (lokal tid) |
| Prognos referenstid | `referenceTime` |
| Modellpunkt | Faktisk grid `lat, lon` som SMHI svarade med |

---

## Brandrisk (fwif1g)

Dygnsprognos, närmaste `validTime`:

| Sensor | Beskrivning |
|--------|-------------|
| **Brandrisk** | Text: Liten risk … Extremt stor risk |
| FWI-värde / FWI-index | Numeriskt index |
| ISI, BUI, FFMC, DMC, DC | Klassiska FWI-komponenter |
| Gräsbrandsrisk | Textnivå (eller ej tillämpligt) |
| Potentiell spridningshastighet | m/min |
| Skogstorkt index | Numeriskt |

---

## Varningar (IBWW) – länsfilter

API: `https://opendata-download-warnings.smhi.se/ibww/api/version/1/warning.json` (hela Sverige).

Integrationen **filtrerar till ditt län** så du inte får Skåne/Gotland när du bor i Skövde.

| Sensor | Tillstånd |
|--------|-----------|
| **Varningar** | t.ex. `1 aktiva · Meddelande: Risk för vattenbrist (Västra Götalands län)` |
| **Antal varningar** | Heltal |

**Attribut:** `warnings` (lista), `filter_area` (aktivt län).

### Hur filtret väljs
1. **Options → Varningsområde** om ifyllt  
2. Annars **auto** från lat/lon (ungefärliga länsboxar) → Skövde ≈ *Västra Götalands län*  
3. Värdet `all` / `alla` / `*` → ingen filter (hela landet)

Matchar både `areaName` och `affectedAreas` (delsträng, skiftlägesokänsligt).

---

## Options

*Integrationen → Konfigurera*

| Alternativ | Default | Beskrivning |
|------------|---------|-------------|
| **Uppdateringsintervall** | 300 s | 60–3600 s – hur ofta API:erna pollas |
| **Varningsområde** | auto från lat/lon | Länsnamn, t.ex. `Västra Götalands län`. Tomt = auto. `all` = hela Sverige |

Ändring laddar om config entry.

---

## Jämförelse med officiella SMHI

| | Officiella SMHI (Core) | SMHI Local |
|--|------------------------|------------|
| Underhåll | Home Assistant-projektet | Denna custom/HACS |
| Weather + forecast | Ja (även twice-daily) | Ja (hourly/daily) |
| Brandrisk FWI | Ja | Ja (fwif1g) |
| Varningar | Nej (separat integration) | Ja, med **länsfilter** |
| Svenska “premium”-sensorer (nästa nederbörd, åskrisk-text, molntyp, 12 h-summa) | Byggs med templates | Inbyggt |
| Cache vid API-glitch | Standard HA | `_last_good` → stabil UI |
| Poll-intervall | ~30 min | Valbart |

Båda använder SMHI:s öppna data. SMHI Local är ett **lager ovanpå** samma källa, optimerat för dashboard, TTS och automations utan 20 templates.

---

## API-referens

| Tjänst | Endpoint |
|--------|----------|
| Prognos | `…/snow1g/version/1/geotype/point/lon/{lon}/lat/{lat}/data.json` |
| Brandrisk | `…/fwif1g/version/1/daily/geotype/point/lon/{lon}/lat/{lat}/data.json` |
| Varningar | `https://opendata-download-warnings.smhi.se/ibww/api/version/1/warning.json` |

Ingen autentisering. Villkor: [SMHI Open Data](https://opendata.smhi.se).

---

## Ändringslogg (utdrag)

### 1.4.1
- Länsfilter för IBWW-varningar (auto från koordinater + options)
- Attribut `filter_area` på varningssensorn
- Options: *Varningsområde*

### 1.4.0
- Brandrisk (fwif1g) och IBWW-varningar
- Extra snow1g-fält: molnbas/topp, molnnivåer %, nederbörd min/max/median, vind i grader, prognosmetadata, modellpunkt

### 1.3.x
- Första publika paketeringen med weather, härledda sensorer och last-good-cache

---

## Licens

MIT – se [LICENSE](LICENSE).  
Prognos-, brandrisk- och varningsdata tillhör SMHI.  
Integrationen: **SMHI Open Data Powered by Rasmus**.
