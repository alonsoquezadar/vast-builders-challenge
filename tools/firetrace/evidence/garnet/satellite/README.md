# Garnet Fire: capa satelital y meteorológica

Datos de satélite, perímetro oficial y meteorología horaria del Garnet Fire (2025-CASNF-001684, Sierra National Forest), del 24/08 al 12/09/2025. Huellas SHA-256 de entradas, salidas y scripts en `manifest.json`. Las consultas exactas, con la clave sustituida por `{MAP_KEY}`, están en `raw/queries.json`.

## Reproducir

```sh
FIRMS_MAP_KEY=... python3 fetch_satellite.py   # descarga raw/ (la clave no se guarda)
python3 build_layers.py                         # genera las capas; requiere numpy, scipy, shapely
```

## Archivos

| Archivo | Estado | Contenido |
|---|---|---|
| `perimeter.geojson` | **Observado** | Perímetro final WFIGS: 60.022,86 acres, método "IR Image Interpretation". Incluye su fecha de polígono y la fecha de descubrimiento. |
| `hotspots.geojson` | **Observado** | 13.883 detecciones térmicas FIRMS (VIIRS S-NPP SP, NOAA-20 SP, NOAA-21 NRT y MODIS SP), a menos de ~1 km del perímetro final. Se excluyen VIIRS de confianza `l` y MODIS con confianza < 50. Propiedades: `t` (epoch UTC), `acquiredUtc`, `acquiredPdt`, `source`, `satellite`, `confidence`, `frpMW`, `daynight`, `pixelM`. |
| `overpasses.json` | **Observado** | 225 pasadas de satélite: hora, número de detecciones, FRP total y centroide. |
| `weather-hourly.json` | **Modelo meteorológico** | Viento a 10 m, ráfagas, humedad relativa y temperatura por hora en UTC, en **un punto** del reanálisis Open-Meteo (36.87, -118.89, 1862 m). `windFromDeg` es la dirección *desde* donde sopla y `windSpeedMps` está en m/s: es la misma convención que `simulation.py`. |
| `arrival-reconstructed.geojson` | **RECONSTRUIDO** | 6.073 celdas de 200 m dentro del perímetro final. `t` / `arrivalPdt` = primera detección VIIRS a ≤ 400 m (`kind: observed-support`, 5.836 celdas) o mediana de las 6 celdas vecinas con soporte (`kind: interpolated`, 237 celdas). |
| `daily-extent-reconstructed.geojson` | **RECONSTRUIDO** | Unión de celdas quemadas hasta el final de cada día local (PDT), con `reconstructedAcres` y `newDetections`. No son perímetros oficiales diarios. |
| `summary.json` | — | Conteos, parámetros y comparación con superficies publicadas. |
| `raw/` | Fuente | CSV de FIRMS, GeoJSON de WFIGS y JSON de Open-Meteo, sin modificar. |

## Comprobado

- La API de FIRMS devolvió datos de archivo para las 4 fuentes y 4 ventanas de 5 días. WFIGS devolvió un único perímetro del Garnet 2025 en California.
- Las primeras detecciones son del 24/08 a las 02:26 PDT. Esto coincide con la fecha de descubrimiento de WFIGS (24/08, 00:10 PDT). **La ficha de CAL FIRE indica 14:13 del mismo día: hay una discrepancia sin resolver**, y no se debe usar ninguna de las dos como hora de ignición exacta.
- **27/08, día de las cámaras.** El FRP total por pasada sube de ~1.160 MW (NOAA-21, 12:49 PDT) a ~7.068 MW (14:29) y ~6.863 MW (S-NPP, 14:57), y llega a ~17.901 MW en MODIS (16:00). Es coherente con el pirocúmulo que muestran las cámaras desde la tarde. **Es una coincidencia cualitativa: no verifica la zona horaria de las cámaras ni sincroniza los relojes.**
- **Viento del 27/08 por la tarde** (reanálisis): sopla desde el OSO (~245–255°) a 3–4 m/s, con ráfagas de 10–14 m/s y humedad relativa de 22–24 %.

## Reconstruido o interpolado, NO observado

- **FIRMS registra anomalías térmicas en el centro de un píxel** (~375 m en VIIRS, ~1 km en MODIS) en el momento de cada pasada. No mide frente, área ni velocidad.
- La hora de llegada queda acotada por la primera pasada que detecta calor. El fuego pudo llegar antes, entre dos pasadas, y las nubes o el humo denso pueden ocultar detecciones.
- **La reconstrucción no puede salir del perímetro final:** por construcción, cualquier crecimiento queda confinado a esa huella.
- Comparación con las superficies publicadas: el 25/08 da **6.721 frente a 4.400 acres (×1,53)** y el 31/08, **25.806 frente a 18.748 (×1,38)**. Sobrestima al principio porque cada detección "quema" un radio de 400 m. Para la cifra del 31/08 solo hay una fuente de prensa local. **No usar estas áreas como cifra oficial.**

## Cómo consumirlo

- **Mapa 3D:** mostrar `perimeter.geojson` como contorno. Para animar, filtrar `arrival-reconstructed.geojson` con `["<=", ["get", "t"], cursor]` y pintar `hotspots.geojson` en la ventana `[cursor − 12 h, cursor]` con radio según `frpMW`. Etiquetar la capa animada como **"reconstrucción a partir de detecciones satelitales"**, no como "frente".
- **Simulación:** tomar `windFromDeg` y `windSpeedMps` de `weather-hourly.json` para la hora del escenario. Para comparar con datos pasados, partir de la celda de `daily-extent-reconstructed.geojson` de un día y contrastar el resultado con las detecciones de las 12–24 h siguientes en `hotspots.geojson`, que es la referencia observada. La reconstrucción diaria también es interpolada y no debe usarse como "verdad".
- **Calibración de cámaras:** las pasadas del 27/08 a las 12:49, 13:16 y 13:38 PDT caen dentro de los tramos de pose fija G1 (Delilah 10:30–13:44) y G3b (Buck Rock 11:27–13:59) de `planning/video-selection-shared-r1.md`, **si** la hora impresa está en PDT. Los centroides de `overpasses.json` sirven como referencia independiente con error de ~375 m o más.

## Recomendaciones para los otros frentes (no implementadas aquí)

- **Calibración:** las crestas recortadas contra el cielo en Delilah y Buck Rock permiten estimar el desfase de giro y el campo de visión comparando el perfil de horizonte del DEM con el del fotograma, antes de usar las referencias manuales de `alignment.html`. Validar después contra los centroides FIRMS de ~13:16 PDT.
- **Propagación:** usar el viento horario en lugar de un valor fijo y medir el acierto frente a las detecciones FIRMS posteriores, no frente a esta reconstrucción. Declarar el combustible uniforme como supuesto.
- **Altura de la columna:** con una torre calibrada y la distancia al centroide FIRMS de la misma hora, el ángulo vertical de la cima del pirocúmulo da una altura aproximada. La deriva hacia el ENE debería coincidir con el viento de `weather-hourly.json`.

## Fuentes

- NASA FIRMS, API de área: https://firms.modaps.eosdis.nasa.gov/api/area/
- WFIGS Interagency Perimeters: https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters/FeatureServer/0
- Archivo histórico de Open-Meteo: https://open-meteo.com/en/docs/historical-weather-api
- USFS, actualización del 25/08/2025: https://www.fs.usda.gov/r05/sierra/newsroom/releases/garnet-fire-update-august-25-2025
- CAL FIRE, Garnet Fire: https://www.fire.ca.gov/incidents/2025/8/24/garnet-fire
