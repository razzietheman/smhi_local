```markdown
# SMHI Local

[![Open your Home Assistant instance and repository inside a hacs repository.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=razzietheman&repository=smhi_local&category=integration)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Home Assistant-integration för **SMHI Open Data**: punktprognos (**snow1g**), brandrisk (**fwif1g**), konsekvensbaserade varningar (**IBWW**) samt valfri hav-/sjödata (**ocobs** / **hydroobs**).

Bygger en `weather`-entitet plus sensorer direkt från API:erna, med **minne av senaste giltiga prognos** så dashboards inte blir `unavailable` vid tillfälliga nätverks-/API-fel.

**Version:** 1.4.3  
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
11. [Varningar (IBWW) – punkt-i-polygon](#varningar-ibww--punkt-i-polygon)
12. [Hav- och sjödata (valfritt)](#hav--och-sjödata-valfritt)
13. [Options](#options)
14. [Jämförelse med officiella SMHI](#jämförelse-med-officiella-smhi)
15. [API-referens](#api-referens)
16. [Ändringslogg (utdrag)](#ändringslogg-utdrag)

---

## Vad integrationen gör

| Källa | Användning |
|-------|------------|
| **snow1g** punktprognos | Aktuellt väder, hourly/daily forecast, ~20+ sensorer |
| **fwif1g** dygn | Brandrisk / FWI-index och relaterade mått |
| **IBWW** varningar | Aktiva vädervarningar, **filtrerade mot din lat/lon (polygon)** |
| **hydroobs** / **ocobs** | Valfritt: vattenstånd, vattentemperatur, våghöjd från närmaste station |

En config entry (lat/lon) → en enhet i HA med weather + alla sensorer. Uppdateringsintervall är konfigurerbart (default 300 s).

---

## Installation

### HACS (rekommenderas)
1. Klicka på knappen högst upp för att öppna direkt i HACS, eller: HACS → Integrations → ⋮ → *Custom repositories*
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
        ├── GET snow1g   → timeSeries + createdTime/referenceTime/geometry
        ├── GET fwif1g   → brandrisk (närmaste dygn)
        ├── GET IBWW     → varningar (punkt-i-polygon mot lat/lon)
        └── GET hydro/ocobs (valfritt) → närmaste vattenstation
        │
        ├── lyckad snow1g → spara _last_good
        └── misslyckad    → returnera _last_good (övrigt kan uppdateras ovanpå)
        │
        ├── current_bundle() / derived_bundle() / fire_bundle()
        ├── warnings_bundle()  → polygon-filtrerade varningar
        ├── water_bundle()     → vattenstånd, temp, våghöjd …
        └── meta_bundle()
```

- **Platforms:** `sensor`, `weather`
- **Aktuellt väder** = tidpunkten i `timeSeries` närmast `now()`

---

## Cache av senaste giltiga prognos

Vid HTTP-fel, nätverksfel eller tom `timeSeries` returneras **`_last_good`** i RAM. Sensorer och weather fortsätter visa senaste lyckade prognos i stället för `unavailable`.

| Aspekt | Beteende |
|--------|----------|
| Lagring | Processminne (inte disk) |
| HA-omstart | Cache töms; fylls vid första lyckade poll |
| Första start utan nät | `ConfigEntryNotReady` |
| Åldrande data | Visas tills ny hämtning lyckas |

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

Svensk text för väderläge: sensorn **Förhållande**.

---

## Aktuella sensorer (snow1g)

Från närmaste prognospunkt: temperatur, känns som, fukt, tryck, vind (hastighet/by/riktning text + grader), sikt, nederbörd (mean/min/max/median), nederbördsrisk, vädersymbol, förhållande, molntyp, molnmängd, lågt/medel/högt molntäcke, molnbas/molntopp, åskrisk nu, risk för frusen nederbörd.

---

## Härledda sensorer

| Friendly name | Beskrivning |
|---------------|-------------|
| **Nästa nederbördstyp** | Regn, Snö, … / *Ingen nederbörd väntas* |
| **Nästa nederbördsmängd** | mm/h |
| **Nästa nederbördstid** | Start–slut, t.ex. `20:00 onsdag … - 00:00 torsdag …` |
| **Nederbörd kommande 12h** | mm (summa) |
| **Åskrisk** | t.ex. *Liten åskrisk 4% i kväll klockan 23* |
| **Åskrisk max %** | Numeriskt max inom 12 h |
| **Nästa dåliga sikt** | Klass + datum/tid, eller *God sikt* |
| **Snöandel nästa nederbörd** | *Allt snö* / *Ej tillämpligt* / … |

> Gamla template-id `sensor.smhi_nasta_nederbord` → **`sensor.smhi_nasta_nederbordstyp`**.

---

## Metadata

| Sensor | Innehåll |
|--------|----------|
| Prognos skapad | `createdTime` |
| Prognos referenstid | `referenceTime` |
| Modellpunkt | Faktisk grid `lat, lon` |

---

## Brandrisk (fwif1g)

| Sensor | Beskrivning |
|--------|-------------|
| **Brandrisk** | Text: Liten risk … Extremt stor risk |
| FWI-värde / FWI-index | Numeriskt |
| ISI, BUI, FFMC, DMC, DC | FWI-komponenter |
| Gräsbrandsrisk | Textnivå |
| Potentiell spridningshastighet | m/min |
| Skogstorkt index | Numeriskt |

---

## Varningar (IBWW) – punkt-i-polygon

API:et returnerar **hela Sverige**. Från **1.4.2** filtreras varningar med **ray-casting** mot varje `warningAreas[].area.geometry` (GeoJSON Polygon/MultiPolygon, EPSG:4326).

Din config entry:s **lat/lon** måste ligga **inuti** zonen – annars visas den inte.  
Exempel Skövde: *Västkusten*, *Dalsland* och liknande zoner filtreras bort även om de nämner Götaland i namnet.

| Sensor | Exempel |
|--------|---------|
| **Varningar** | `1 aktiva · Meddelande: Risk för vattenbrist (Västra Götalands län)` |
| **Antal varningar** | Heltal |

**Attribut:** `warnings`, `filter_area`, `filter_mode` (`point_in_polygon` / `all`), per rad `in_polygon`.

| Varningsområde (options) | Effekt |
|--------------------------|--------|
| **Tomt** (rekommenderas) | Bara zoner som täcker din punkt |
| `all` / `alla` | Hela Sverige |
| Länsnamn | Används främst om polygon saknas (äldre fallback) |

---

## Hav- och sjödata (valfritt)

Från **1.4.3**. Av som standard – aktiveras under *Konfigurera*.

| Källa | API | Typiska mätvärden |
|-------|-----|-------------------|
| **hydro** | hydroobs | Sjö/vattendrag: vattenstånd (cm), vattentemperatur |
| **ocean** | ocobs | Hav: vattenstånd, havstemperatur, signifikant våghöjd |
| **auto** | båda | Väljer källa vars närmaste station ligger närmast dig |

**Station:** Haversine från din lat/lon (eller manuellt stations-ID).

| Sensor | Enhet |
|--------|--------|
| Vattenstånd | cm |
| Vattentemperatur | °C |
| Våghöjd | m (ocean) |
| Vattenstation | namn |
| Avstånd till vattenstation | km |

> Inland (t.ex. Skövde) kan få närmaste *live*-sjöstation tiotals km bort (t.ex. Vänern). Avståndssensorn visar det tydligt. Alla stationer har inte `latest-hour`/`latest-day`.

---

## Options

*Integrationen → Konfigurera*

| Alternativ | Default | Beskrivning |
|------------|---------|-------------|
| **Uppdateringsintervall** | 300 s | 60–3600 s |
| **Varningsområde** | tomt | Tomt = punkt-i-polygon. `all` = hela Sverige |
| **Aktivera hav- och sjödata** | av | På för hydro/ocobs |
| **Typ av vattenstation** | auto | auto / hydro / ocean / av |
| **Manuellt stations-ID** | tomt | Åsidosätter närmaste-station |

Fältetiketter är korta; hjälptext ligger i `data_description` så den inte krockar med värdet i UI.

---

## Jämförelse med officiella SMHI

| | Officiella SMHI (Core) | SMHI Local |
|--|------------------------|------------|
| Weather + forecast | Ja (+ twice-daily) | Ja (hourly/daily) |
| Brandrisk FWI | Ja | Ja |
| Varningar | Nej | Ja, **polygon mot din punkt** |
| Hav/sjö-observationer | Nej | Valfritt (hydro/ocobs) |
| Svenska “premium”-sensorer | Templates | Inbyggt |
| Cache vid API-glitch | Standard | `_last_good` |
| Poll-intervall | ~30 min | Valbart |

---

## API-referens

| Tjänst | Endpoint |
|--------|----------|
| Prognos | `…/snow1g/…/point/lon/{lon}/lat/{lat}/data.json` |
| Brandrisk | `…/fwif1g/version/1/daily/…/point/lon/{lon}/lat/{lat}/data.json` |
| Varningar | `https://opendata-download-warnings.smhi.se/ibww/api/version/1/warning.json` |
| Sjö/vattendrag | `https://opendata-download-hydroobs.smhi.se/api/version/1.0/…` |
| Hav | `https://opendata-download-ocobs.smhi.se/api/version/1.0/…` |

Ingen autentisering. Villkor: [SMHI Open Data](https://opendata.smhi.se).

---

## Ändringslogg (utdrag)

### 1.4.3
- Options: korta etiketter + `data_description` (hjälptext krockar inte med fältvärdet)
- Valfri hav-/sjödata (hydroobs / ocobs): närmaste station, manuellt ID
- Sensorer: vattenstånd, vattentemperatur, våghöjd, stationsnamn, avstånd
- Nya installationer: tomt varningsområde = punkt-i-polygon

### 1.4.2
- Varningar filtreras med **punkt-i-polygon** mot SMHI:s GeoJSON-zoner
- Västkust-/Dalsland-varningar m.m. visas inte om din punkt inte ligger i zonen
- Attribut `filter_mode`, `in_polygon`

### 1.4.1
- Länsfilter för IBWW (föregångare till polygon-filter)
- Options: *Varningsområde*

### 1.4.0
- Brandrisk (fwif1g) och IBWW-varningar
- Extra snow1g-fält (molnbas, ensemble-nederbörd, metadata, …)

### 1.3.x
- Första publika paketeringen med weather, härledda sensorer och last-good-cache

---

## Licens

MIT – se [LICENSE](LICENSE).  
Prognos-, brandrisk-, varnings- och observationsdata tillhör SMHI.  
Integrationen: **SMHI Open Data Powered by Rasmus**.
```
