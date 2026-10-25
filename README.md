# 🌤️ SMHI Local

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-v1.4.5-blue.svg?style=for-the-badge)](https://github.com/razzietheman/smhi_local)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

> Den mest kompletta, robusta och lokaliserade **Home Assistant**-integrationen för **SMHI Open Data**. 

**SMHI Local** levererar inte bara en standard-weather-entitet – den ger dig full koll på allt från **snöbyar, vindbyar, åskrisk och brandrisk (FWI)** till **punkt-i-polygon-filtrerade varningar (IBWW)** samt **sjö-, hav- och isobservationer**.

---

### ✨ Vad gör SMHI Local unik?

* 🛡️ **`_last_good`-Cache:** Aldrig mer fula `unavailable`- eller `unknown`-tillstånd på dina dashboards vid tillfälliga API-glitchar från SMHI.
* 🎯 **Hyper-lokala Varningar (IBWW):** Äkta **punkt-i-polygon**-analys mot SMHI:s GeoJSON-zoner. Du får *bara* varningar som faktiskt berör din exakta position.
* 🧊 **Snygg Hantering av Tillval:** Valfria sensorer (som is- och havsobservationer) visas snyggt som **"Ej aktiverad"** i UI:t istället för det förvirrande statusvärdet *"Okänd"*.
* 🇸🇪 **Svenska Premium-sensorer:** Färdigberäknade fält för *"Nästa regn"*, *"Åskrisk 12h"*, *"Upplevd temperatur (Feels like)"* och mycket mer – redo för dina automationer utan krångliga mallar.

---

## 📑 Innehållsförteckning

1. [Funktioner i översikt](#-funktioner-i-översikt)
2. [Installation](#-installation)
3. [Konfiguration & Plats](#-konfiguration--plats)
4. [Teknisk Arkitektur & Cache](#-teknisk-arkitektur--cache)
5. [Sensorer & Entiteter](#-sensorer--entiteter)
6. [Hav-, Sjö- och Isdata](#-hav--sjö--och-isdata-valfritt)
7. [Jämförelse med Officiella SMHI](#-jämförelse-med-officiella-smhi)
8. [Ändringslogg](#-ändringslogg)

---

## ⚡ Funktioner i översikt

| Datakälla | Tjänst / API | Beskrivning & Vad du får |
| :--- | :--- | :--- |
| 🌦️ **Prognos** | `snow1g` | Weather-entitet + detaljerade tim- och dygnsprognoser för temp, vind, fukt, sikt och moln. |
| 🔮 **Härlett** | *Inbyggd logik* | Intelligent skanning: *"Nästa nederbördstyp"*, *"Regnsmängd nästa 12h"*, *"Åskrisk"*, etc. |
| 🔥 **Brandrisk** | `fwif1g` | FWI-index, gräsbrandrisk, potentiell spridningshastighet och bränsleupplag. |
| ⚠️ **Varningar** | `IBWW` | Aktuella vädervarningar & meddelanden med **punkt-i-polygon**-geofencing. |
| 🌊 **Vatten** | `hydroobs` / `ocobs` | Vattenstånd, vattentemperatur och våghöjd från närmaste station. |
| 🧊 **Is observations** | `iceobs` | Istjocklek, isbeskaffenhet och snötäcke på is under vinterhalvåret. |

---

## 📦 Installation

### Metod 1: HACS (Rekommenderas) 🚀

1. Öppna **HACS** i Home Assistant → Klicka på **Integrations**.
2. Klicka på de tre punkterna `⋮` i övre högra hörnet → Välj **Custom repositories**.
3. Klistra in repository-URL:en och välj **Integration** som kategori.
4. Klicka på **Installera** och starta om Home Assistant.
5. Gå till **Inställningar → Enheter och tjänster → Lägg till integration** och sök efter **SMHI Local**.

### Metod 2: Manuell Installation

1. Ladda ner källkoden.
2. Kopiera mappen `custom_components/smhi_local` till din Home Assistant-konfiguration (`/config/custom_components/`).
3. Starta om Home Assistant.

---

## 📍 Konfiguration & Plats

Vid konfiguration skapar integrationen en unik enhet baserad på dina koordinater:

* **Namn:** `SMHI` (kan anpassas)
* **Latitud / Longitud:** Hämtas automatiskt från din `zone.home` (kan ändras manuellt).
* **Unique ID:** `smhi_{lat:.3f}_{lon:.3f}` – gör det möjligt att lägga till flera platser samtidigt.

> **Obs:** Koordinaterna avrundas till 4 decimaler (~11 meters precision) när anropet görs mot SMHI:s grid-modell.

---

## 🏗️ Teknisk Arkitektur & Cache

Integrationen använder en central `DataUpdateCoordinator` som pollar SMHI med ett valbart intervall (default 300 sekunder).

```text
                  ┌─────────────────────────────────────────┐
                  │ SmhiLocalCoordinator (Poll 300s)        │
                  └────────────────────┬────────────────────┘
                                       │
      ┌──────────────────┬─────────────┼─────────────┬──────────────────┐
      ▼                  ▼             ▼             ▼                  ▼
  GET snow1g         GET fwif1g    GET IBWW      GET water          GET ice
 (Prognos)          (Brandrisk)   (Varningar)   (Hydro/Ocobs)      (Iceobs)
      │                  │             │             │                  │
      ├─► Lyckades? ────┼─────────────┼─────────────┼──────────────────┤
      │    ├── JA ──► Uppdatera cache (_last_good)  │                  │
      │    └── NEJ ─► Använd _last_good (Inget UI-flimmer)             │
      │                                                                 │
      ▼                                                                 ▼
┌──────────────┐                                            ┌──────────────────────┐
│ Weather &    │                                            │ Tillvalssensorer     │
│ Kärnsensorer │                                            │ (Inaktiva = "Ej     │
└──────────────┘                                            │  aktiverad")         │
                                                            └──────────────────────┘
```

---

## 📊 Sensorer & Entiteter

### 1. Kärnsensorer (`snow1g`)
* **Temperatur & Känsla:** Lufttemperatur, `Feels Like` (beräknad med fukt och vind).
* **Vind:** Hastighet, vindbyar, grader och svensk kompassriktning (ex: *Sydost*).
* **Nederbörd:** Aktuell mm/h, min/max/median (ensemble) samt risk för frusen nederbörd.
* **Moln & Sikt:** Molnmängd (%), molnbas, molntopp, molntyp och sikt i km.

### 2. Härledda sensorer (Smarta beräkningar)
* **Nästa nederbörd:** Tidsintervall för nästa regn/snö, mängd samt snöandel.
* **12h-översikt:** Total nederbördssumma kommande 12 timmar.
* **Åskrisk:** Max åskrisk i % samt textmeddelande (*"Liten åskrisk 4% i kväll klockan 23"*).

### 3. Varningar (IBWW med Punkt-i-Polygon)
Visar aktiva varningar från SMHI enbart om din valda position faktiskt ligger inuti varningens geografiska polygon.
* `sensor.smhi_varningar` (Innehåller varningstext och detaljer i attributen)
* `sensor.smhi_antal_varningar`

---

## 🌊 Hav-, Sjö- och Isdata (Valfritt)

Under **Konfigurera** i integrationen kan du aktivera mätstationer för vatten och is. Integrationen beräknar automatiskt den närmaste aktiva stationen med hjälp av **Haversine-formeln**.

| Sensor | Enhet | Status om ej aktiverad i inställningar |
| :--- | :--- | :--- |
| **Vattenstånd** | `cm` | Ej aktiverad |
| **Vattentemperatur** | `°C` | Ej aktiverad |
| **Våghöjd** | `m` | Ej aktiverad |
| **Istjocklek** | `cm` | Ej aktiverad |
| **Isbeskaffenhet** | — | Ej aktiverad |
| **Isobservationstid** | — | Ej aktiverad |

---

## ⚖️ Jämförelse med Officiella SMHI

| Funktion | Core SMHI | SMHI Local 🌤️ |
| :--- | :---: | :---: |
| Weather-entitet | ✅ | ✅ |
| Cache vid nätverksfel (`_last_good`) | ❌ | ✅ |
| Brandrisk (FWI) | ✅ | ✅ |
| Varningar (IBWW) | ❌ | ✅ (Med Punkt-i-polygon) |
| Sjö- och Havsobservationer | ❌ | ✅ |
| Isobservationer (`iceobs`) | ❌ | ✅ |
| Snygg hantering av avstängda sensorer | ❌ | ✅ (*"Ej aktiverad"*) |

---

## 📜 Ändringslogg

### 🟢 v1.4.5
* **UI-förbättring:** Sensorer som tillhör inaktiverade funktioner (t.ex. is- och vattenmätningar när tillvalet är avstängt) visar nu status **"Ej aktiverad"** istället för förvirrande **"Okänd"** / `unknown`.
* **Källkods-optimering:** Renodlad hantering av tillståndsändringar för valfria entiteter.

### 🟢 v1.4.3
* Tillagt stöd för **isobservationer (`iceobs`)**.
* Automatisk Haversine-sökning efter närmaste mätstation.

*Se hela historiken i [RELEASE_NOTES.md](RELEASE_NOTES.md).*

---

## 📄 Licens

Distribueras under **MIT-licensen**. Se `LICENSE` för mer information.  
Prognos-, brandrisk-, varnings- och observationsdata ägs av **SMHI**. Integrationen är utvecklad fristående som **SMHI Open Data Powered by Rasmus**.