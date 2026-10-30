# 🌤️ SMHI Local

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.5.0-blue.svg)](https://github.com/razzietheman/smhi_local)

> Den ultimata **Nordic Weather & Water Hub** för Home Assistant. Kraftfull, robust och fylld med färdiga svenska sensorer för både vardag och busväder!

**SMHI Local** tar SMHI Open Data till nästa nivå. Utöver en komplett `weather`-entitet får du tillgång till **punkt-i-polygon-filtrerade varningar (IBWW)**, **brandrisk (FWI)** samt valfria **sjö-, hav- och isobservationer**.

### ✨ Varför välja SMHI Local?

* 💾 **Persistent `_last_good`-Cache (Nytt i v1.5.0!):** Säg adjö till gråa `unavailable`-kort – även efter en omstart av Home Assistant! Om SMHI ligger nere eller nätverket svajar när du startar om, laddas senast sparade data automatisk från disken via Home Assistant Store.

* 🎯 **Exakta Varningar (IBWW):** Inga mer falsklarm för grannlänet eller ute till havs! Varningar filtreras med geografisk ray-casting så att du enbart notifieras om din position ligger *inuti* varningszonen.

* 🧊 **Snyggt UI för Tillval:** Valfria modulaktiveringar (som is- och vattenmätningar) visar tydligt **"Ej aktiverad"** istället för förvirrande statusar som *"Okänd"*.

* 🇸🇪 **Svenska Smart-sensorer:** Färdigberäknade fält för *"Nästa regn"*, *"Åskrisk 12h"*, *"Upplevd temperatur (Känns som)"* och mycket mer – redo för dina automationer direkt.

## 📑 Innehållsförteckning

1. [Funktioner i översikt](#-funktioner-i-översikt)
2. [Installation (Marketplace / HACS)](#-installation)
3. [Konfiguration & Plats](#-konfiguration--plats)
4. [Teknisk Arkitektur](#-teknisk-arkitektur)
5. [Sensorer & Entiteter](#-sensorer--entiteter)
6. [Hav-, Sjö- och Isdata](#-hav--sjö--och-isdata-valfritt)
7. [Jämförelse med Officiella SMHI](#-jämförelse-med-officiella-smhi)
8. [Ändringslogg](#-ändringslogg)

## ⚡ Funktioner i översikt

| Datakälla | API / Tjänst | Beskrivning |
| ----- | ----- | ----- |
| 🌦️ **Prognos** | `snow1g` | Weather-entitet + detaljerade tim- och dygnsprognoser för temp, vind, fukt, sikt och moln. |
| 🔮 **Härlett** | *Inbyggd logik* | Skannar framtiden: *"Nästa nederbördstyp/tid"*, *"Regnmängd 12h"*, *"Åskrisk"*, etc. |
| 🔥 **Brandrisk** | `fwif1g` | FWI-index, gräsbrandsrisk, potentiell spridningshastighet och bränsleupplag. |
| ⚠️ **Varningar** | `IBWW` | Aktuella vädervarningar med **punkt-i-polygon** geofencing. |
| 🌊 **Vatten** | `hydroobs` / `ocobs` | Vattenstånd, vattentemperatur och våghöjd från närmaste station. |
| 🧊 **Is observations** | `iceobs` | Istjocklek, isbeskaffenhet och snötäcke på is under vinterhalvåret. |

## 📦 Installation

### Metod 1: Home Assistant Marketplace (HA 2026.11+) 🛍️

Från och med Home Assistant 2026.11 finns Marketplace inbyggt direkt i systemet:

1. Gå till **Inställningar → Marketplace** i Home Assistant.
2. Klicka på menyn (`⋮`) i övre högra hörnet → Välj **Anpassade källor** (*Custom repositories*).
3. Lägg till repository-URL: `https://github.com/razzietheman/smhi_local` och välj **Integration**.
4. Sök upp **SMHI Local** och klicka på **Installera**.
5. Starta om Home Assistant.

### Metod 2: HACS (Äldre HA-versioner) 🚀

1. Öppna **HACS → Integrationer → Custom repositories**.
2. Klistra in repository-URL:en och välj **Integration**.
3. Installera och starta om Home Assistant.

## 📍 Konfiguration & Plats

Efter installation konfigurerar du enkelt integrationen under **Inställningar → Enheter och tjänster → Lägg till integration → SMHI Local**.

* **Namn:** `SMHI` (kan anpassas)
* **Latitud / Longitud:** Hämtas automatiskt från din Home Assistant-plats (`zone.home`).
* **Unique ID:** `smhi_{lat:.3f}_{lon:.3f}` – gör det möjligt att lägga till flera platser samtidigt.

> **Obs:** Koordinaterna avrundas till 4 decimaler (~11 meters precision) när anropet görs mot SMHI:s grid-modell.

## 🏗️ Teknisk Arkitektur & Cache

Integrationen använder en central `DataUpdateCoordinator` som pollar SMHI med ett valbart intervall (standard 300 sekunder). Datan sparas kontinuerligt på disken via **Home Assistant Store** så att den alltid finns tillgänglig även vid omstarter.

```
                  ┌─────────────────────────────────────────┐
                  │ SmhiLocalCoordinator (Poll 300s)        │
                  └────────────────────┬────────────────────┘
                                       │
                         [Laddar HA Store vid start]
                                       │
      ┌──────────────────┬─────────────┼─────────────┬──────────────────┐
      ▼                  ▼             ▼             ▼                  ▼
  GET snow1g         GET fwif1g    GET IBWW      GET water          GET ice
 (Prognos)          (Brandrisk)   (Varningar)   (Hydro/Ocobs)      (Iceobs)
      │                  │             │             │                  │
      ├─► Lyckades? ────┼─────────────┼─────────────┼──────────────────┤
      │    ├── JA ──► Uppdatera RAM & spara till HA Store (Disk)        │
      │    └── NEJ ─► Använd laddad cache från Disk/RAM (Ingen offline)│
      │                                                                 │
      ▼                                                                 ▼
┌──────────────┐                                            ┌──────────────────────┐
│ Weather &    │                                            │ Tillvalssensorer     │
│ Kärnsensorer │                                            │ (Inaktiva = "Ej     │
└──────────────┘                                            │  aktiverad")         │
                                                            └──────────────────────┘
```

## 📊 Sensorer & Entiteter

### 1. Kärnsensorer (`snow1g`)

* **Temperatur & Känsla:** Lufttemperatur, `Känns som` (beräknad med fukt och vind).
* **Vind:** Hastighet, vindbyar, grader och svensk kompassriktning (ex: *Sydost*).
* **Nederbörd:** Aktuell mm/h, min/max/median (ensemble) samt risk för frusen nederbörd.
* **Moln & Sikt:** Molnmängd (%), molnbas, molntopp, molntyp och sikt i km.

### 2. Härledda sensorer (Smarta beräkningar)

* **Nästa nederbörd:** Tidsintervall för nästa regn/snö, mängd samt snöandel.
* **12h-översikt:** Total nederbördssumma kommande 12 timmar.
* **Åskrisk:** Max åskrisk i % samt textmeddelande (*"Liten åskrisk 4% i kväll klockan 23"*).

### 3. Varningar (IBWW med Punkt-i-Polygon)

Visar aktiva varningar från SMHI enbart om din valda position faktiskt ligger inuti varningens geografiska polygon.

* `sensor.smhi_varningar`
* `sensor.smhi_antal_varningar`

## snö 🌊 Hav-, Sjö- och Isdata (Valfritt)

Under **Konfigurera** på integrationen kan du aktivera mätstationer för vatten och is. Integrationen beräknar automatiskt den närmaste aktiva stationen med hjälp av **Haversine-formeln**.

| Sensor | Enhet | Status om ej aktiverad i inställningar |
| ----- | ----- | ----- |
| **Vattenstånd** | `cm` | Ej aktiverad |
| **Vattentemperatur** | `°C` | Ej aktiverad |
| **Våghöjd** | `m` | Ej aktiverad |
| **Istjocklek** | `cm` | Ej aktiverad |
| **Isbeskaffenhet** | — | Ej aktiverad |
| **Isobservationstid** | — | Ej aktiverad |

## ⚖️ Jämförelse med Officiella SMHI

| Funktion | Core SMHI | SMHI Local 🌤️ |
| ----- | ----- | ----- |
| Weather-entitet | ✅ | ✅ |
| Persistent cache över omstarter | ❌ | ✅ (Nytt i v1.5.0!) |
| Brandrisk (FWI) | ✅ | ✅ |
| Varningar (IBWW) | ❌ | ✅ (Med Punkt-i-polygon) |
| Sjö- och Havsobservationer | ❌ | ✅ |
| Isobservationer (`iceobs`) | ❌ | ✅ |
| Tydlig hantering av inaktiverade tillval | ❌ | ✅ (*"Ej aktiverad"*) |

## 📜 Ändringslogg

### 🟢 v1.5.0
- **Persistent last_good via Home Assistant Store:** Cachen sparats nu till disk och överlever omstarter av Home Assistant.
- Sparar komplett tillstånd: `timeSeries`, brandrisk, varningar, vatten, is samt molnbas/topp.
- Laddas automatiskt *före* `first_refresh` så att prognos och sensorer finns kvar omedelbart vid API-fel efter omstart.

### 🟢 v1.4.5
- **UI-förbättring:** Inaktiverade tillvalssensorer visar nu status **"Ej aktiverad"** istället för förvirrande *"Okänd"* / `unknown`.
- **Källkodsoptimering:** Städning i tillståndshantering för entiteter.

### 🟢 v1.4.3
- Tillagt stöd för **isobservationer (`iceobs`)** samt sjö-/havsdata med automatisk Haversine-stationssökning.

## 📄 Licens

Distribueras under **MIT-licensen**. Se `LICENSE` för mer information.

Prognos-, brandrisk-, varnings- och observationsdata ägs av **SMHI**. Integrationen är utvecklad fristående som **SMHI Open Data Powered by Rasmus**.
