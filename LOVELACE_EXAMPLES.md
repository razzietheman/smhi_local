# Lovelace-exempel – SMHI Local

## Enkel weather-kort

```yaml
type: weather-forecast
entity: weather.smhi_skovde
show_forecast: true
forecast_type: hourly
```

## Sensor-rader (TTS / dashboard)

```yaml
type: entities
title: SMHI just nu
entities:
  - entity: sensor.smhi_temperatur
  - entity: sensor.smhi_kanns_som
  - entity: sensor.smhi_vindriktning
  - entity: sensor.smhi_sikt
  - entity: sensor.smhi_molntyp
  - entity: sensor.smhi_askrisk
  - entity: sensor.smhi_nasta_nederbordstyp
  - entity: sensor.smhi_nasta_nederbordstid
```

## Markdown med nästa nederbörd

```yaml
type: markdown
content: >
  **Nästa nederbörd:** {{ states('sensor.smhi_nasta_nederbordstyp') }}

  {{ states('sensor.smhi_nasta_nederbordstid') }}

  **Åska:** {{ states('sensor.smhi_askrisk') }}
```

> Entity-id beror på namnet du satte i config flow (t.ex. `SMHI` → `sensor.smhi_temperatur`).
