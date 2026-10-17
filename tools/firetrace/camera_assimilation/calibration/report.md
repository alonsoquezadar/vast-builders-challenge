# Calibración horizontal experimental (1 GDL) por cámara/pose

Generado por `fit.py` a partir de `calibration.json` (estado: **no-calibration** — pending-observations). Reproducir:

```sh
python3 tools/firetrace/camera_assimilation/calibration/fit.py \
  --observations tools/firetrace/camera_assimilation/vision/observations.json \
  --output tools/firetrace/camera_assimilation/calibration/calibration.json \
  --report tools/firetrace/camera_assimilation/calibration/report.md
```

Split congelado antes de leer observaciones (SHA-256 `c08b34094debb8b4…`). Reloj PDT = hipótesis. FOV = 65.1° a zoom 1 (supuesto no verificado), escalado focal para zoom 1.2/1.4. Solo se ajusta `yaw0`.

## Estado: pending-observations

No existía `tools/firetrace/camera_assimilation/vision/observations.json` al generar este informe. Ninguna pose está calibrada; no hay resultados medidos. El CLI está listo y las funciones están probadas con datos sintéticos (que no son medición real).

Contexto (solo fotogramas actuales, 2026-10-17; no verifica reloj ni pose de 2025): Axis-DelilahLookout2 X mod 360 = 308.01° vs azimut de catálogo 308.29° (residuo 0.28°); Axis-BuckRock1 X mod 360 = 301.74° vs azimut de catálogo 301.58° (residuo -0.16°)

## Geometría FIRMS medida desde la torre candidata

Con posición candidata; rangos y sectores incluyen el semiancho del píxel. Las columnas x son una predicción comprobable **si** X impreso fuera el azimut (fuera de [0,1] = fuera de cuadro); no son un resultado.

| Pose | Rol | Pasada | Det. | Azimut centroide (°) | Rango (km) | Sector (°) | Ancho (°) | Grupos | x centroide (si yaw0=X) | x sector |
|---|---|---|---|---|---|---|---|---|---|---|
| G1 | fit | NOAA21@2025-08-27T19:49:00Z | 12 | 18.31 | 13.22 | 9.1–25.5 | 16.4 | 3 | 0.37 | 0.21–0.49 |
| G1 | heldOut | SNPP@2025-08-27T20:16:00Z | 8 | 21.36 | 13.36 | 17.5–25.6 | 8.1 | 2 | 0.42 | 0.36–0.49 |
| G1 | heldOut | NOAA20@2025-08-27T20:38:00Z | 1 | 23.91 | 11.79 | 23.0–24.8 | 1.8 | 1 | 0.46 | 0.45–0.48 |
| G1 | extraCheck | MODIS@2025-08-27T18:17:00Z | 2 | 21.69 | 13.68 | 17.9–26.0 | 8.1 | 2 | 0.42 | 0.36–0.50 |
| G3b | fit | NOAA21@2025-08-27T19:49:00Z | 12 | 316.98 | 27.38 | 313.0–321.8 | 8.8 | 3 | 0.45 | 0.39–0.51 |
| G3b | heldOut | SNPP@2025-08-27T20:16:00Z | 8 | 317.92 | 26.81 | 314.5–321.2 | 6.7 | 1 | 0.46 | 0.41–0.51 |
| G3b | heldOut | NOAA20@2025-08-27T20:38:00Z | 1 | 315.28 | 25.67 | 314.9–315.7 | 0.8 | 1 | 0.42 | 0.42–0.43 |
| G3b | extraCheck | MODIS@2025-08-27T18:17:00Z | 2 | 318.61 | 26.88 | 316.4–320.7 | 4.2 | 2 | 0.47 | 0.44–0.50 |
| G4 | fit | NOAA21@2025-08-27T21:29:00Z | 72 | 319.27 | 26.56 | 312.2–328.7 | 16.5 | 1 | 0.21 | 0.06–0.40 |
| G4 | heldOut | SNPP@2025-08-27T21:57:00Z | 55 | 322.69 | 26.19 | 314.1–331.9 | 17.8 | 1 | 0.28 | 0.11–0.46 |
| G4 | heldOut | MODIS@2025-08-27T23:00:00Z | 10 | 314.26 | 26.34 | 303.2–324.4 | 21.2 | 4 | 0.11 | -0.15–0.32 |

## delilah / G1

- Sin parámetros: observations file missing (pending-observations)
- Excluidas: 0


## delilah / G2

- Sin parámetros: no FIRMS pass inside this pose window under the PDT hypothesis; poses are not transferred (printed pan X is not a validated azimuth)
- Excluidas: 0


## buckrock / G3

- Sin parámetros: no FIRMS pass inside this pose window under the PDT hypothesis; poses are not transferred (printed pan X is not a validated azimuth)
- Excluidas: 0


## buckrock / G3b

- Sin parámetros: observations file missing (pending-observations)
- Excluidas: 0


## buckrock / G4

- Sin parámetros: observations file missing (pending-observations)
- Excluidas: 0


## Límites

- Clock: printed time is read as PDT (UTC = print + 7 h). This is a hypothesis; PST and UTC are shown for sensitivity only and the error minimum is never used to choose a clock.
- Camera positions are candidates (tower coordinates from public lookout sources), not surveyed; CAL FIRE incident point is not used anywhere.
- Horizontal FOV = 65.1 deg at zoom 1 (catalog value, unverified) scaled by focal length for zoom 1.2/1.4 (printed Z read as zoom: unverified). FOV is never fitted.
- Pinhole model, zero roll, tilt neglected (bound in uncertainty.neglectedTiltBoundDeg); lens distortion ignored.
- yaw0Deg = true azimuth of the image centre. Printed pan X is never an input of the fit; it is compared afterwards as an external check (externalCheck). Poses are never transferred (G1 is not G2).
- FIRMS time is the overpass time; the per-pixel scan time inside a granule can differ by minutes.
- FIRMS detections of a pass are several pixels in several groups: the pass centroid is not an observed smoke base. Centroid residual and nearest-group distance are reported separately.
- Cross-track metres = satellite range x sin(angular error): compatibility with an independent satellite direction, not 2D fire localization and not absolute geographic error.
- Temporal holdout (other overpasses of the same fire) is not independent physical truth: the fire front moves, and the detections may not include the visible base.
- One-degree-of-freedom experiment with a prior; it is not equivalent to calibration.py with verified pixel-to-world pairs.
- Not an operational or absolute geolocation product; errors are angular / cross-track at FIRMS range.
- PDT is not verified; clock sensitivity does not prove any clock.
- G2 and G3 have no FIRMS pass in their windows: null parameters by design.
- vision/observations.json not available when this file was generated: every pose is uncalibrated.
