# SMHI Local

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.5.1-blue.svg)](https://github.com/razzietheman/smhi_local)

Home Assistant-integration för **SMHI Open Data**: punktprognos (**snow1g**),
**brandrisk** (fwif1g), **vädervarningar** (IBWW) samt valfria **vatten- och
isobservationer** (hydroobs/ocobs). Integrationen ger en `weather`-entitet och
61 sensorer med **persistent last-good-cache**, ålderskontroll och en egen
**Datastatus**-sensor.

**Attribution:** SMHI Open Data Powered by Rasmus

---

## Innehåll

1. [Vad gör integrationen?](#vad-gör-integrationen)
2. [Installation](#installation)
3. [Plats (lat/lon)](#plats-latlon)
4. [Teknisk arkitektur](#teknisk-arkitektur)
5. [Cache och datastatus](#cache-och-datastatus)
6. [Weather-entitet](#weather-entitet)
7. [Aktuella sensorer (snow1g)](#aktuella-sensorer-snow1g)
8. [Härledda sensorer](#härledda-sensorer)
9. [Metadata](#metadata)
10. [Brandrisk (fwif1g)](#brandrisk-fwif1g)
11. [Varningar (IBWW)](#varningar-ibww)
12. [Vatten och is (valfritt)](#vatten-och-is-valfritt)
13. [Options](#options)
14. [Jämförelse med officiella SMHI](#jämförelse-med-officiella-smhi)
15. [API-referens](#api-referens)
16. [Utveckling och tester](#utveckling-och-tester)
17. [Ändringslogg (kort)](#ändringslogg-kort)

---

## Vad gör integrationen?

| Källa | Vad du får |
|-------|------------|
| **snow1g** punktprognos | Weather + temp, vind, sikt, moln, nederbörd, åska, "nästa regn", 12 h-summa, … |
| **fwif1g** dygn | Brandrisk (FWI), gräsbrand, spridning, m.m. |
| **IBWW** varningar | Aktiva varningar/meddelanden, filtrerade till din punkt |
| **hydroobs / ocobs** (valfritt) | Vattenstånd, vattentemperatur, våghöjd, istjocklek |

Allt pollas av en gemensam **DataUpdateCoordinator**. Varje lager har egen
"last good"-bevarande, och alla entitetsvärden beräknas **en gång per
uppdatering** i stället för av varje sensor separat.

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

| Fält | Default | Beskrivning |
|------|---------|-------------|
| **Namn** | `SMHI` | Enhetsnamn i HA |
| **Latitud** | `hass.config.latitude` | HA-platsen |
| **Longitud** | `hass.config.longitude` | HA-platsen |

**Unique id:** `smhi_{lat:.3f}_{lon:.3f}` – en config entry per plats.

- Lat/lon avrundas till **4 decimaler** i API-anropen (~11 m).
- Ingen API-nyckel, endast HTTPS och delad `aiohttp`-session.
- Timeout 20 s (25–30 s för observationskällorna).

SMHI svarar med närmaste **modellpunkt** för prognosen, inte en
observationsstation.

---

## Teknisk arkitektur

```text
Config entry (lat, lon, name, options)
        │  poll (default 300 s)
        ▼
SmhiLocalCoordinator._async_update_data
        ├── GET snow1g   → timeSeries, createdTime, geometry
        ├── GET fwif1g   → brandrisk (närmaste dygn)
        ├── GET IBWW     → hela Sverige, filtreras lokalt
        ├── GET hydroobs/ocobs (valfritt) → vatten / is
        │
        ├── varje lager: nytt värde vid lyckad hämtning,
        │               tidigare giltigt värde vid fel
        ├── last_success_at = senaste lyckade snow1g-hämtning
        ├── _finalize() → current/derived/meta/fire/warnings/
        │                 water/ice/status-beräkning en gång
        └── spara cache till .storage/smhi_local.<entry_id>
```

- **Platforms:** `sensor`, `weather`
- **Normalisering:** snow1g-fält → interna nycklar (äldre pmp3g stöds också)
- **Fel vid första start:** `ConfigEntryNotReady` om ingen cachad prognos finns

---

## Cache och datastatus

### Persistent cache

Cachen sparas med Home Assistant `Store` i
`.storage/smhi_local.<entry_id>` och överlever omstart. Den innehåller
senaste giltiga prognos, per-lagers senaste lyckade tidpunkter och de senaste
giltiga molnhöjderna. Härledda bundlar räknas om vid uppstart i stället för
att sparas.

### Åldersgräns (TTL)

| Inställning | Värde |
|-------------|-------|
| `CACHE_MAX_AGE_MINUTES` | **360 min (6 h)** |
| `CLOUD_LOOKAHEAD_MINUTES` | **180 min (3 h)** – begränsar fallbacksökning i tidsserien |

Om senaste lyckade prognos är äldre än 6 timmar:

- Visas **Datastatus = `Gammal data`**.
- Vanliga sensorer och weather-entiteten blir **`unavailable`** i stället för
  att visa gammal data som aktuell.
- Datastatus-sensorn förblir tillgänglig så att du kan se orsaken.

`fetched_at` uppdateras vid varje poll, men `last_success_at` flyttas **inte**
när prognosen misslyckas. Därför kan inte en lyckad poll av t.ex. brandrisk få
en gammal prognos att se färsk ut.

### Datastatus-sensorn

`Datastatus` har tillstånden `Aktuell`, `Gammal data` och `Ingen data` samt
attributen:

| Attribut | Innehåll |
|----------|----------|
| `last_success_at` / `last_success_at_iso` | Senaste lyckade prognoshämtning |
| `fetched_at` / `fetched_at_iso` | Senaste poll (även vid fel) |
| `age_minutes` | Prognosens ålder i minuter |
| `ttl_minutes` | Tillåten ålder (360) |

Weather-entiteten har motsvarande attribut `data_status`, `last_success_at`,
`fetched_at` och `cache_ttl_minutes`.

### Molnhöjd

SMHI använder `9999` för saknad molnhöjd. Integrationen söker då först bland
prognospunkter inom ±3 timmar, därefter bland sparade värden. sensors
`Molnbas`/`Molntopp` får attributen `estimated` och `source`
(`current`/`series`/`cache`) så att du ser när värdet är skattat.

---

## Weather-entitet

| Egenskap | Källa |
|----------|-------|
| `condition` | Wsymb2 → HA (`sunny`, `clear-night`, `cloudy`, `rainy`, …) |
| Natt/dag | Solens elevation för **varje prognostidpunkt** (inte nuvarande `sun.sun`-state) |
| `temperature` / `humidity` / `pressure` | snow1g |
| `wind_speed` / `wind_bearing` | snow1g |
| `visibility` | snow1g |
| Forecast | hourly + daily från senaste giltiga `timeSeries` |
| Filtrering | Hourly och daily hoppar över förflutna tids-/dagspunkter |
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
| Vindriktning | `wind_direction_sv` | — | Svensk kompass (Sydost, …), attribut `degrees` |
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
| Molnbas / Molntopp | | m | Med attributen `estimated` och `source` |
| Åskrisk nu | `thunderstorm_probability` | % | |
| Risk för frusen nederbörd | `probability_of_frozen_precipitation` | % | |
| **Datastatus** | `data_status` | — | `Aktuell` / `Gammal data` / `Ingen data` |

---

## Härledda sensorer

Skannar **framtida** punkter i senaste giltiga tidsserie.

| Friendly name | Nyckel | Logik |
|---------------|--------|-------|
| **Nästa nederbördstyp** | `next_precip_type` | Första punkt ≥ 0,1 mm; pcat (+ temp-override) |
| **Nästa nederbördsmängd** | `next_precip_amount` | mm/h för den punkten |
| **Nästa nederbördstid** | `next_precip_time` | Start–slut, t.ex. `20:00 onsdag 21 oktober - 00:00 torsdag 22 oktober` |
| **Nederbörd kommande 12h** | `precip_next_12h` | Summa mean, 1 decimal |
| **Åskrisk** | `thunder_risk_text` | Max 12 h: *Liten åskrisk 4% i kväll klockan 23* |
| **Åskrisk max %** | `thunder_risk_12h` | Numeriskt |
| **Nästa dåliga sikt** | `next_bad_visibility` | Första < 10 km inom 48 h, med klass + datum |
| **Snöandel nästa nederbörd** | `next_snow_share` | *Allt snö* / *XX% snö* / *Ej tillämpligt* |

**Entity-id (exempel):** `sensor.smhi_nasta_nederbordstyp` – inte det gamla
template-namnet `sensor.smhi_nasta_nederbord`.

### Nederbördstyp (pcat)

| Kod | Text |
|-----|------|
| 0 | Ingen nederbörd |
| 1 | Snö |
| 2 | Snöblandat regn |
| 3 | Regn |
| 4 | Duggregn |
| 5–6 | Underkylt regn / duggregn |
| 7–11 | Snöbyar, regnskurar, kraftiga varianter, … |

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

Ett svar utan användbara parametrar räknas inte som en lyckad hämtning – då
behålls föregående giltiga brandriskvärde.

---

## Varningar (IBWW)

API: `https://opendata-download-warnings.smhi.se/ibww/api/version/1/warning.json`
(returnerar **hela Sverige** – filtrering sker i integrationen).

| Sensor | Innehåll |
|--------|----------|
| **Varningar** | Sammanfattning, t.ex. `1 aktiv · Gul: Risk för vattenbrist (Västra Götalands län)` |
| **Antal varningar** | Antal efter filter |

**Attribut:** `warnings` (lista), `filter_area` (aktivt filter),
`filter_mode` (`all` eller `point_in_polygon`).

### Filterlägen

| Inställning | Beteende |
|-------------|----------|
| **Tomt (default)** | Punkt-i-polygon: bara varningar vars zon täcker din lat/lon |
| **Fritext, t.ex. `Stockholms län`** | Polygonträff **eller** namnmatchning (`OR` som tidigare utlovat) |
| `all` / `alla` | Ingen filtrering – hela landet |

Om en varningsyta saknar polygon kan den bara matchas via namn när ett
namnfilter anges. I defaultläget ignoreras den.

---

## Vatten och is (valfritt)

Aktiveras under *Konfigurera*.

| Alternativ | Källa | Sensorer |
|------------|-------|----------|
| **Aktivera hav- och sjödata** | hydroobs (sjö/vattendrag) eller ocobs (hav) | Vattenstånd, vattentemperatur, våghöjd, station, avstånd, tid |
| **Aktivera isinformation** | hydroobs parameter 7 (säsongsdata) | Istjocklek, station, observationstid, status |

- `Typ av vattenstation`: `auto` (närmaste), `hydro`, `ocean` eller `av`.
- Manuellt stations-ID kan anges för både vatten och is.
- **Felaktigt stations-ID loggas och ger inga nya observationer** – integrationen
  faller inte tyst tillbaka till en annan station. Tidigare giltiga värden kan
  behållas tills ett nytt giltigt svar finns.
- Istjocklek saknas ofta under sommaren; sensorn visar då status i stället för
  ett påhittat värde.

---

## Options

*Integrationen → Konfigurera*

| Alternativ | Default | Beskrivning |
|------------|---------|-------------|
| **Uppdateringsintervall** | 300 s | 60–3600 – hur ofta coordinator pollar |
| **Varningsområde** | tomt | punkt-i-polygon, namn, eller `all` |
| **Aktivera hav- och sjödata** | av | hydroobs/ocobs |
| **Typ av vattenstation** | auto | hydro / ocean / auto / av |
| **Manuellt stations-ID** | tomt | Vattenstation |
| **Aktivera isinformation** | av | hydroobs param 7 |
| **Manuellt isstations-ID** | tomt | Isstation |

Ändring laddar om config entry. Optionsflödet fungerar både på Home Assistant
2024.8–2024.10 och nyare versioner.

---

## Jämförelse med officiella SMHI

| | **Core SMHI** | **SMHI Local** |
|--|---------------|----------------|
| Underhåll | Home Assistant | Community / detta repo |
| Weather + forecast | daily / hourly / twice-daily | hourly + daily |
| Brandrisk (FWI) | Ja | Ja (fwif1g) |
| Varningar | Nej (separata custom) | Ja, punktfiltrerade |
| Vatten/is | Nej | Ja (valfritt) |
| Svenska "premium"-texter | Bygg själv | Inbyggt |
| Cache vid API-glitch | Standard HA | Per-lager last-good + TTL + status |
| Poll-intervall | ~30 min | Valbart |

Samma datakälla (SMHI Open Data) – olika lager ovanpå.

---

## API-referens

| Tjänst | URL-mönster |
|--------|-------------|
| Prognos | `…/snow1g/version/1/geotype/point/lon/{lon}/lat/{lat}/data.json` |
| Brandrisk | `…/fwif1g/version/1/daily/geotype/point/lon/{lon}/lat/{lat}/data.json` |
| Varningar | `https://opendata-download-warnings.smhi.se/ibww/api/version/1/warning.json` |
| Vatten (sjö) | `…/hydroobs/version/1/parameter/{param}/station/{id}/period/{period}/data.json` |
| Vatten (hav) | `…/ocobs/version/1/parameter/{param}/station/{id}/period/{period}/data.json` |
| Is | hydroobs parameter `7` (istjocklek) |

- Auth: ingen
- Villkor: [SMHI Open Data](https://opendata.smhi.se)
- Attribution i HA: **SMHI Open Data Powered by Rasmus**

---

## Utveckling och tester

```bash
pip install -r requirements_test.txt
python -m py_compile custom_components/smhi_local/*.py
python -m pytest -q
```

Testerna täcker normalisering, symbol→condition, soltid för natt/dag,
molnhöjdsfönster, TTL, per-lager-cache, varningsfilter, stations-ID,
prognosfönster, entiteters tillgänglighet och config/options-flow.

Integrationen är på **Bronze** i HA:s quality scale. Återstående förbättringar
(t.ex. fler HA-harness-tester, ikonöversättningar och reparationer) spåras i
`quality_scale.yaml`.

---

## Ändringslogg (kort)

### 1.5.1
- Rätt natt/dag för varje prognostidpunkt; daily hoppar över förflutna dagar.
- Cache med **6 h TTL**, `last_success_at` och ny **Datastatus**-sensor;
  vanliga entiteter blir `unavailable` när prognosen är för gammal.
- Per-lager "last good": brandrisk, varningar, vatten och is behålls vid fel.
- Molnhöjdsfallback begränsas till ±3 h och märks med `estimated`/`source`.
- Alla bundlar beräknas en gång per coordinator-uppdatering.
- Varningsfilter följer dokumenterad `OR`-semantik mellan polygon och namn.
- Felaktigt manuellt stations-ID loggas i stället för tyst fallback.
- Optionsflöde kompatibelt med både äldre och nyare Home Assistant.
- Borttagna dubbletter/oanvänd imports, uppdaterad README, 31 enhetstester
  och CI som kör pytest i stället för bara `py_compile`.

### 1.5.0
- Persistent cache via HA `Store` och utökade vatten-/isalternativ.

### 1.4.1
- Länsfilter för IBWW-varningar (auto från koordinater + options **Varningsområde**).

### 1.4.0
- Brandrisk (fwif1g), varningar (IBWW)
- Fler snow1g-fält: ensemble-nederbörd, molnbas/nivåer, metadata

### 1.3.x
- Grund: snow1g, weather, härledda sensorer, last-good-cache

---

## Licens

MIT – se [LICENSE](LICENSE).  
Prognos-, brandrisk- och varningsdata tillhör SMHI; integrationen är
**SMHI Open Data Powered by Rasmus**.
