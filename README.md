# 🚀 SMHI Local 1.5.1

> [!TIP]
> Den här releasen handlar om **tillförlitlighet**. Prognosen får rätt natt/dag, cachen får en ärlig åldersgräns och du kan se exakt hur färsk datan är – direkt i Home Assistant.

**Släppdatum:** 23 november 2026  
**Minsta Home Assistant:** 2024.8.0  
**Kvalitetsnivå:** Bronze  
**Typ:** Stabilitets- och kvalitetsrelease · inga icke-bakåtkompatibla ändringar

---

## ✨ Höjdpunkter

| | Nyhet | Varför det spelar roll |
|---|---|---|
| 🛡️ | **Datastatus** | Du ser direkt om prognosen är `Aktuell`, `Gammal data` eller `Ingen data`. |
| ⏳ | **6 timmars cache-TTL** | Gammal data visas aldrig som aktuell. |
| 🌙 | **Rätt natt/dag** | `clear-night` och `sunny` stämmer även för prognospunkter i morgon. |
| 🧩 | **Per-lager last-good** | EttAPI-fel för brandrisk påverkar inte varningar, vatten eller is. |
| ☁️ | **Molnhöjd med källa** | Du ser när en höjd är uppskattad och varifrån den kommer. |
| ⚡ | **Snabbare uppdateringar** | Alla värden beräknas en gång per poll i stället för 61 gånger. |

---

## 🛡️ Datastatus – full koll på datans ålder

En ny sensor **`Datastatus`** visar:

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

Varje datalager har nu egen "last good":

- ❌ Brandrisk fallerar → föregående FWI-värde behålls
- ❌ Varningar fallerar → föregående varningar behålls
- ❌ Vatten/is fallerar → föregående observationer behålls
- ❌ Prognosen fallerar → hela senaste giltiga prognosen används, men `last_success_at` står kvar

Cachen sparas med Home Assistant `Store` i `.storage/smhi_local.<entry_id>` och **överlever omstart**. Cache från 1.5.0 läses in automatiskt.

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
- Varningsfiltret följer nu dokumenterad semantik: **polygonträff ELLER namnmatchning**.
- Felaktigt manuellt stations-ID loggas och ersätts inte längre tyst av närmaste station.
- Optionsflödet fungerar både på **HA 2024.8–2024.10** och nyare versioner.
- Dubblerad kod och oanvända imports är borttagna.

---

## 📦 Uppgradering

> [!NOTE]
> Inga breaking changes. Uppgradera via HACS eller ersätt `custom_components/smhi_local` och starta om Home Assistant.

Om cachen från 1.5.0 är äldre än 6 timmar visas `Gammal data` tills en ny lyckad prognoshämtning sker. Det är avsiktligt – ingen gammal prognos ska smyga sig in som aktuell.

---

## ✅ Verifierat för releasen

- `python3 -m py_compile custom_components/smhi_local/*.py` → OK
- `python3 -m pytest -q` → **31 tester passerar**
- Manifest, `strings.json`, translations och `hacs.json` → validerade
- 61 sensorer + weather-entitet → oförändrat entitetsutbud, plus den nya Datastatus-sensorn

Testerna täcker normalisering, symbol→condition, soltid, molnhöjdsfönster, TTL, per-lager-cache, varningsfilter, stations-ID, prognosfönster, tillgänglighet och config/options-flow.

---

## 🙏 Attribution

Data från **SMHI Open Data**.  
Integrationen är märkt **SMHI Open Data Powered by Rasmus**.

MIT-licens – se [LICENSE](LICENSE).
