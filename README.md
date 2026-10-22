# SMHI Local

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/razzietheman/smhi_local?include_prereleases)](https://github.com/razzietheman/smhi_local/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Home Assistant-integration för **SMHI Open Data** (SNOW1g point forecast) – lokal prognos utan den officiella SMHI-integrationen, med **latest-valid-cache** så UI inte flimrar vid API-avbrott.

**SMHI Open Data Powered by Rasmus**

## Funktioner

- **weather.smhi_skovde** – condition, temp, fukt, tryck, vind, sikt + **hourly/daily** forecast
- **Sensorer** för temperatur, känns som, vind (text + grader), sikt, molnmängd %, molntyp, nederbörd, …
- **Härledda** sensorer i samma stil som templates:
  - Nästa nederbördstyp / mängd / tid (start–slut)
  - Nederbörd kommande 12 h
  - Åskrisk (t.ex. `Liten åskrisk 4% i kväll klockan 23`)
  - Nästa dåliga sikt (t.ex. `Måttlig sikt (9.5 km), onsdag 21 oktober kl 19:00`)
  - Snöandel nästa nederbörd
  - Risk för frusen nederbörd
- **Cache** av senaste giltiga `timeSeries` vid nätverks-/API-fel
- Config flow (lat/lon, default HA-position) + options (uppdateringsintervall)
- Svenska + engelska strängar

## Installation

### HACS (rekommenderas)

1. HACS → Tre prickar → **Custom repositories**
2. URL: `https://github.com/razzietheman/smhi_local` · Kategori: **Integration**
3. Installera **SMHI Local** → starta om HA
4. **Inställningar → Enheter & tjänster → Lägg till → SMHI Local**

### Manuell

1. Kopiera `custom_components/smhi_local` till `config/custom_components/`
2. Starta om Home Assistant
3. Lägg till integrationen som ovan

## Options (efter setup)

| Alternativ | Standard | Beskrivning |
|------------|----------|-------------|
| Uppdateringsintervall | 300 s | Hur ofta SMHI hämtas |

## Exempel – väderentitet

```text
weather.smhi_skovde
  condition: partlycloudy
  temperature: 10.4
  humidity: 95
  … + hourly/daily forecast
```

## Exempel – sensorer

| Sensor | Exempel state |
|--------|----------------|
| Vindriktning | `Sydost` |
| Förhållande | `Mulet` |
| Molntyp | `Låga valkmoln (Stratocumulus, Sc)` |
| Åskrisk | `Liten åskrisk 4% i kväll klockan 23` |
| Nästa nederbördstid | `20:00 onsdag 21 oktober - 00:00 torsdag 22 oktober` |
| Nästa dåliga sikt | `Måttlig sikt (9.5 km), onsdag 21 oktober kl 19:00` |

## Migration från REST + templates

1. Installera integrationen och jämför värden
2. Uppdatera dashboards/automationer till nya entity_id
3. Ta bort `sensor.smhi_prognos_hemma` (REST), `latest_valid`, UI-templates och template-`weather.smhi_skovde`

Se även [LOVELACE_EXAMPLES.md](LOVELACE_EXAMPLES.md).

## Data & attribution

Prognosdata från [SMHI Open Data](https://opendata.smhi.se) (kategori **snow1g**).  
Attribution i HA: **SMHI Open Data Powered by Rasmus**.

## Licens

MIT – se [LICENSE](LICENSE).
