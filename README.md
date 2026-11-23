# 🚀 SMHI Local 1.5.2

> [!TIP]
> Den här releasen rättar två textfel i de svenska text-sensorerna: klockslag som kallades "förmiddag" fast det var morgon, och en nederbördsperiod som kunde sträcka sig över fem dygn på bara ett par procents sannolikhet.

**Släppdatum:** 23 november 2026  
**Minsta Home Assistant:** 2024.8.0  
**Kvalitetsnivå:** Bronze  
**Typ:** Bugfix-release · inga icke-bakåtkompatibla ändringar

---

## 🐛 Nytt i 1.5.2

| Sensor | Före | Efter |
|---|---|---|
| `sensor.smhi_askrisk` | `Liten åskrisk 3% i morgon förmiddag klockan 06` | `Liten åskrisk 3% i morgon bitti klockan 06` |
| `sensor.smhi_nasta_nederbordstid` | `07:00 söndag 29 november - 01:00 fredag 4 december` | `13:00 måndag 30 november - 01:00 onsdag 2 december` |

**Dagsdelar** delas nu in som `natt 00–06`, `bitti/morgonen 06–09`, `förmiddag 09–12`, `eftermiddag 12–18` och `kväll 18–24`. Samma textgenerator används av åskrisk, nästa nederbörd och nästa dåliga sikt.

**Nederbörd** räknas bara som en faktisk händelse när SMHI:s deterministiska värde eller median är minst 0,1 mm – eller när ensemble-medlet är minst 0,1 mm **och** sannolikheten minst 50 %. Tidigare räckte medlet ensamt, vilket kunde ge ett sammanhängande femdygnsintervall av 4–6 %-diss. `next_precip_time`, `next_precip_type` och `next_precip_amount` använder nu samma filter och visar alltså samma händelse.

> [!NOTE]
> Ett intervall på flera dygn kan fortfarande vara korrekt – SMHI:s långsiktsprognos har 12-timmarssteg och kan visa sammanhängande nederbörd. Skillnaden är att intervallet nu bygger på faktisk prognoserad nederbörd, inte på lågsannolikhetsrisk.

---

## ✨ Från 1.5.1 (oförändrat)

| | Nyhet | Varför det spelar roll |
|---|---|---|
| 🛡️ | **Datastatus** | Du ser direkt om prognosen är `Aktuell`, `Gammal data` eller `Ingen data`. |
| ⏳ | **6 timmars cache-TTL** | Gammal data visas aldrig som aktuell. |
| 🌙 | **Rätt natt/dag** | `clear-night` och `sunny` stämmer även för prognospunkter i morgon. |
| 🧩 | **Per-lager last-good** | Ett API-fel för brandrisk påverkar inte varningar, vatten eller is. |
| ☁️ | **Molnhöjd med källa** | Du ser när en höjd är uppskattad och varifrån den kommer. |
| ⚡ | **Snabbare uppdateringar** | Alla värden beräknas en gång per poll i stället för 61 gånger. |

---

## 🛡️ Datastatus – full koll på datans ålder

En sensor **`Datastatus`** visar:

| Tillstånd | Betydelse |
|---|---|
| `Aktuell` | Prognosen är färsk och används av alla entiteter. |
| `Gammal data` | Senaste lyckade hämtning är äldre än 6 timmar. |
| `Ingen data` | Ingen giltig prognos finns alls. |

Attribut: `last_success_at`, `fetched_at`, `age_minutes` och `ttl_minutes`.  
Weather-entiteten har samma information under `data_status`, `last_success_at` och `fetched_at`.

> [!IMPORTANT]
> När datan blir för gammal blir vanliga sensorer och weather-entiteten **`unavailable`** – men **Datastatus förblir tillgänglig** så att du förstår varför.

`fetched_at` uppdateras vid varje poll, men `last_success_at` flyttas bara när prognosen faktiskt hämtas. En lyckad brandriskpoll kan alltså inte få en gammal prognos att se färsk ut.

---

## 🌙 Prognosen vet skillnad på dag och natt

Tidigare användes nuvarande `sun.sun`-state för alla framtida timmar. Nu beräknas solens elevation **för varje prognostidpunkt**.

- Kväll/natt i morgon visas som `clear-night`, inte `sunny`.
- Dagsprognosen hoppar över förflutna dagar.
- Hourly-prognosen hoppar över förflutna timmar.

---

## 🧩 Ett fel tar inte ner allt

Varje datalager har egen "last good":

- ❌ Brandrisk fallerar → föregående FWI-värde behålls
- ❌ Varningar fallerar → föregående varningar behålls
- ❌ Vatten/is fallerar → föregående observationer behålls
- ❌ Prognosen fallerar → hela senaste giltiga prognosen används, men `last_success_at` står kvar

Cachen sparas med Home Assistant `Store` i `.storage/smhi_local.<entry_id>` och **överlever omstart**. Cache från 1.5.0/1.5.1 läses in automatiskt.

---

## ☁️ Molnhöjd utan gissningar långt fram i tiden

SMHI använder `9999` när molnhöjd saknas. Nu gäller:

1. Leta bland prognospunkter inom **±3 timmar** (`CLOUD_LOOKAHEAD_MINUTES = 180`).
2. Annars använd senast sparade giltiga värde.
3. Märk resultatet med `estimated: true` och `source: series | cache`.

`source: current` betyder att värdet kommer direkt från aktuell prognospunkt.

---

## ⚡ Under huven

- Alla bundlar – `current`, `derived`, `meta`, `fire`, `warnings`, `water`, `ice` och `status` – beräknas **en gång per coordinator-uppdatering**.
- Varningsfiltret följer dokumenterad semantik: **polygonträff ELLER namnmatchning**.
- Felaktigt manuellt stations-ID loggas och ersätts inte längre tyst av närmaste station.
- Optionsflödet fungerar både på **HA 2024.8–2024.10** och nyare versioner.
- Ny konstant `PRECIP_PROBABILITY_THRESHOLD_PCT = 50` styr när ensemble-medlet får räknas som nederbörd.
- Dubblerad kod och oanvända imports är borttagna.

---

## 📦 Uppgradering

> [!NOTE]
> Inga breaking changes. Uppgradera via HACS eller ersätt `custom_components/smhi_local` och starta om Home Assistant.

Från 1.5.1 behövs inget annat än en omstart. Är cachen äldre än 6 timmar visas `Gammal data` tills en ny lyckad prognoshämtning sker – det är avsiktligt.

---

## ✅ Verifierat för releasen

- `python3 -m py_compile custom_components/smhi_local/*.py` → OK
- `python3 -m pytest -q` → **35 tester passerar**
- Manifest, `strings.json`, translations och `hacs.json` → validerade
- 61 sensorer + weather-entitet → oförändrat entitetsutbud

Testerna täcker normalisering, symbol→condition, soltid, dagsdelar, nederbördsfilter, molnhöjdsfönster, TTL, per-lager-cache, varningsfilter, stations-ID, prognosfönster, tillgänglighet och config/options-flow.

---

## 🙏 Attribution

Data från **SMHI Open Data**.  
Integrationen är märkt **SMHI Open Data Powered by Rasmus**.

MIT-licens – se [LICENSE](LICENSE).
