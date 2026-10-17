# Pronóstico retrospectivo desde el frente reconstruido (r6)

Estado: **retrospective-forecast, `validated: false`**. No es un pronóstico operativo ni una validación independiente.

## Qué hace

`reconstruction_forecast.forecast({'timeUtc': ISO con zona, 'horizonHours': 6|12|24})` devuelve un GeoJSON `FeatureCollection`.

1. **Estado inicial = máscara reconstruida.** Todas las celdas de 200 m de `arrival-reconstructed.geojson` con `t <= timeUtc` (1.657 celdas el 27/08 23:00Z). No hay semilla del operador ni centro de CAL FIRE. Si no hay ninguna celda (antes de 24/08 09:26Z) → `ValueError` pidiendo una hora con área inicial; no se crea una semilla falsa.
2. **Propagación** (extensión separada de `simulation.py`; los coeficientes se importan de ahí): tiempo mínimo multifuente, 8 vecinos, sobre el DEM real de 200 m.
   `tasa = 4 m/min · combustible 1 · W · S`, `W = exp(KW·v·cos(rumbo − (desde+180)))`, `S = clamp(exp(KS·dz/dist), S_MIN, S_MAX)`, con KW=0,06, KS=3, S_MIN=0,25, S_MAX=4.
   El viento es el **horario** de `weather-hourly.json` (modelo Open-Meteo, un punto): constante dentro de cada hora UTC e integrado tramo a tramo al cruzar cada hora (tiempos FIFO, Dijkstra exacto). Ráfagas, HR y temperatura no entran en la tasa.
3. **Referencia** = reconstrucción en `timeUtc + horizonte`, en la misma rejilla. Métricas: IoU total, **IoU de crecimiento** (solo lo que se añade al estado inicial), hectáreas coincidentes / exceso / defecto.
4. Sin referencia si `validUtc` pasa de la última llegada reconstruida (`2025-09-12T10:58Z`): `referenceAvailable=false`, métricas de comparación `null`, `growthIouReason` explica; el pronóstico sí se devuelve (no se asume fuego congelado).

## Contrato

`properties`: `mode`, `validated`, `timeUtc`, `validUtc`, `horizonHours`, `referenceAvailable`, `referenceThroughUtc`, `domainBoundaryReached`, `domainBoundaryReachedAtInitial`, `metrics`, `diagnostics`, `weather`, `assumptions`, `limitations`, `provenance`, `label`.
`features[].properties.role` ∈ `initial-extent` (reconstructed), `modeled-extent` (modeled), `reference-extent` (reconstructed), `overlap` / `overprediction` / `underprediction` (modeled-comparison); geometría `Polygon`/`MultiPolygon` disueltos (≈60 KB por respuesta). **Sin referencia solo se emiten `initial-extent` y `modeled-extent`**; con referencia siempre las seis (una geometría puede ser un `MultiPolygon` vacío).
`metrics` = lo pedido + `growthPredictedHa`, `growthReferenceHa`, `growthIntersectionHa`, `growthIouReason` (texto solo cuando `growthIou` es `null`).
`weather` = hora inicial (`windFromDeg`, `windToDeg`, `windSpeedMps`, `gustMps`, `rhPct`, `tempC`, `timeUtc`) + `hourly` con las horas usadas.
Errores: `ValueError` (400) para entrada inválida, sin área inicial o horizonte fuera del archivo meteorológico (termina `2025-09-13T23:00Z`); `ForecastDataError(RuntimeError)` si falta una fuente o falla un SHA-256 (no es error del cliente; sin sustituto plano).

## Fuentes y huellas

| Fuente | SHA-256 |
|---|---|
| `evidence/garnet/satellite/arrival-reconstructed.geojson` | `726dddb7…680cc` |
| `evidence/garnet/satellite/weather-hourly.json` | `7ccf9452…eb07` |
| `forecast_data/dem-extended-200m.npz` (222×228, 44,4×45,6 km) | `3f6a1879…52c6` |
| `forecast_data/dem-200m.npz` (149×158, copia de 7b9d731, solo comprobación) | `7175b104…95d2` |

Todo está fijado en `forecast_data/source-receipt.json` y se verifica al cargar.

**Dominio.** El DEM de 149×158 (≈5 km de margen) se agotaba: con él, 12 h y 24 h tocaban el borde (`domainBoundaryReached=true`) y el área de 24 h estaba truncada (42.972 ha frente a 46.928 ha). Se amplió con teselas reales AWS Terrarium z12: 11 teselas nuevas (`forecast_data/tiles-extra/`, 1,5 MB) + las 25 de 7b9d731 → ≈12 km de margen alrededor de la huella. `forecast_data/build_dem.py` reproduce el npz (mismo remuestreo 5×5, misma retícula); el nuevo DEM coincide **exactamente** con el base en la zona común (test). Desde el 27/08 23:00Z el modelo ya no toca el borde a 24 h; el indicador sigue activo para otras horas y, si se activa, las métricas son solo dentro del dominio y el resultado debe leerse como truncado.

## Resultado real (27/08/2025 23:00Z, 1 punto de viento de modelo)

Supuestos congelados antes de ejecutar (los de este documento y los de `simulation.py`); los primeros números los vi antes de escribir este documento y **no se cambió ningún parámetro después**.

| Horizonte | Inicial ha | Modelado ha | Referencia ha | Coincidente ha | Exceso ha | Defecto ha | IoU total | IoU crecimiento | Borde |
|---|---|---|---|---|---|---|---|---|---|
| 6 h | 6.628 | 17.416 | 6.628 | 6.628 | 10.788 | 0 | 0,381 | 0,000 | no |
| 12 h | 6.628 | 26.204 | 7.528 | 7.528 | 18.676 | 0 | 0,287 | 0,046 | no |
| 24 h | 6.628 | 46.928 | 8.020 | 8.020 | 38.908 | 0 | 0,171 | 0,035 | no |

Lectura: el modelo **sobrepredice con fuerza**: a 24 h el crecimiento modelado es 40.300 ha frente a 1.392 ha de la referencia (≈29× el crecimiento), y el área total modelada es 46.928 ha frente a 8.020 ha (≈5,9× el área total). **No tiene defecto**: toda la reconstrucción entra en lo modelado. A 6 h la referencia no crece nada (0 celdas nuevas) y el IoU total 0,38 es solo el área inicial; por eso se muestra el IoU de crecimiento junto al total.

## Limitaciones que hay que mostrar

- **Todo el borde de la máscara inicial se trata como frente activo** (488 celdas de borde el 27/08 23:00Z; solo 178 llegaron en las 12 h previas según la reconstrucción). Eso **reaviva bordes antiguos** que ya no ardían: no es un frente observado y explica en parte la sobrepredicción. No se usó la referencia para elegir qué bordes están activos. Está en `limitations` y en `diagnostics.initialFront*`.
- 4 m/min y combustible 1 uniforme son supuestos del brief (`simulation.py`), no ajustados; sin Rothermel/FARSITE, sin spotting ni supresión, sin humedad del combustible.
- Viento: reanálisis de un punto (1.862 m), igual en todo el dominio. HR/temperatura son contexto.
- La referencia está sesgada: sobrestima el área publicada ×1,53 (25/08) y ×1,38 (31/08); primera detección ≠ llegada exacta; la huella final se usó retrospectivamente y la reconstrucción no puede crecer fuera de ella, así que toda expansión modelada fuera cuenta como exceso (`diagnostics.modeledOutsideFinalFootprintHa`: 30.232 ha a 24 h). El pronóstico no se recorta a esa huella.
- DEM 200 m: subestima pendientes; precisión vertical no verificada.
- Un solo caso real evaluado: no hay base estadística.

## Cómo ejecutar / probar

```sh
cd tools/firetrace
/opt/anaconda3/bin/python3 -c "import reconstruction_forecast as r, json; print(json.dumps(r.forecast({'timeUtc':'2025-08-27T23:00:00Z','horizonHours':24})['properties']['metrics']))"
/opt/anaconda3/bin/python3 -m pytest test_reconstruction_forecast.py -q      # 38 tests
/opt/anaconda3/bin/python3 forecast_data/build_dem.py --tiles-dir camera_assimilation/assimilation/dem/tiles --offline   # reconstruir el DEM
```

Dependencias en `requirements-forecast.txt` (numpy, shapely; Pillow solo para reconstruir el DEM). Sin GPU ni red en ejecución.
