# Modelo principal: X impreso histórico como azimut supuesto

Estado: **pending-observations** — pending-observations. `calibrationBasis = printed-x-unverified-historical`, `parameterOrigin = printed-X-prior-not-fitted`. Reproducir:

```sh
python3 tools/firetrace/camera_assimilation/calibration/printed_model.py \
  --observations tools/firetrace/camera_assimilation/vision/observations.json \
  --output tools/firetrace/camera_assimilation/calibration/printed_model.json \
  --report tools/firetrace/camera_assimilation/calibration/printed-model-report.md
```

`yaw0` es **solo** el X impreso de la pose; ninguna detección FIRMS entra en yaw0, FOV ni banda. FOV = 65.1° a zoom 1 (no verificado) con escalado focal. Banda predefinida ±3.0° (sensibilidad [0.3, 1.0, 3.0, 5.0, 10.0]°): **no** es intervalo de confianza ni error histórico medido.

Hoy (2026-10-17) X impreso y azimut de catálogo difieren menos de 0.3°; eso **no** prueba la pose, el reloj ni el FOV de 2025. Todas las pasadas FIRMS son solo comprobación (sin ajuste).

## Pendiente de observaciones

No existía `tools/firetrace/camera_assimilation/vision/observations.json` al generar este informe: los parámetros (supuestos) existen, pero no hay comprobación satelital ni resultados medidos.

## Parámetros por pose

| Pose | Método | Rol | X impreso (°) | yaw0 (°) | Zoom | FOV (°) | Estado satélite | Obs. evaluadas | Sesgo vs ajuste FIRMS (°) |
|---|---|---|---|---|---|---|---|---|---|
| G1 | cosmos | primary | 26.27 | 26.27 | 1.2 | 56.02 | pending-observations | 0 | pending-observations |
| G2 | cosmos | primary | 25.27 | 25.27 | 1.0 | 65.10 | not-observed-in-pose-window | 0 | pending-observations |
| G3 | cosmos | primary | -52.81 | 307.19 | 1.0 | 65.10 | not-observed-in-pose-window | 0 | pending-observations |
| G3b | cosmos | primary | -39.19 | 320.81 | 1.0 | 65.10 | pending-observations | 0 | pending-observations |
| G4 | cosmos | primary | -26.13 | 333.87 | 1.4 | 49.02 | pending-observations | 0 | pending-observations |

## Poses sin pasada en su ventana

G2 (X 25.27°), G3 (X -52.81°): parámetros disponibles como supuesto no validado; errores medidos vacíos.

## Contexto: fotogramas actuales (solo 2026-10-17)

- Axis-DelilahLookout2: X mod 360 = 308.01° vs azimut de catálogo 308.29° (residuo 0.28°)
- Axis-BuckRock1: X mod 360 = 301.74° vs azimut de catálogo 301.58° (residuo -0.16°)

## Límites

- Printed pan X is ASSUMED to be the true-north azimuth of the image centre in 2025. This is an assumption: it is not fitted to FIRMS and not verified for 2025.
- Printed X comes from agent-read frames and is not operator-reviewed; poses are never transferred (each pose uses only its own X).
- Today (2026-10-17) printed X mod 360 agreed with the public catalog azimuth within 0.28 and 0.16 deg and the printed clock matched PDT; this does not prove the 2025 pose, clock, zoom mapping or FOV.
- Horizontal FOV = 65.1 deg at zoom 1 (catalog value, unverified) scaled by focal length for the printed zoom (zoom reading unverified). Not fitted.
- Camera positions are candidates (same as fit.py); CAL FIRE incident point is not used. PDT is a hypothesis for frame/pass matching only.
- The angular band is a predefined prior (3.0 deg half-width) with sensitivity [0.3, 1.0, 3.0, 5.0, 10.0] deg; it is not a confidence interval and not a measured historical error. FIRMS never selects it.
- FIRMS passes are a compatibility check only: detections form several groups, the pass centroid is not an observed smoke base, and temporal agreement is not independent physical truth.
- Cross-track metres = satellite range x sin(angle): compatibility with a satellite direction, not 2D localization nor absolute geographic error.
- The azimuth is an assumption (historical printed X); no FIRMS fit or held-out validation supports it.
- Compatibility with FIRMS is angular / cross-track at satellite range, not geographic error; sectors can be many degrees wide.
- PDT is not verified; a 2026 clock/azimuth agreement does not carry to 2025.
- G2 and G3 have no FIRMS pass in their windows (not-observed-in-pose-window): their parameters are assumptions without any satellite check.
