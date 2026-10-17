# Asimilación de cámaras (fase C) — estado: `paused-next-phase`

**Motivo:** prioridad cambiada por el usuario; además, según root/agente A, 8 de 8 llamadas Cosmos devolvieron `base_visible=false`. Esta carpeta no vio `vision/observations.json` (no existía al cerrar), así que ese recuento **no está verificado aquí**. Sin bases visibles, `cameraUseCount = 0` y no se fabrica ninguna corrección. No hay desarrollo adicional.

## Qué hay

| Archivo | Contenido |
|---|---|
| `run.py` | CLI. Escribe `scenario.json` y `scenario.geojson` (mismo nombre, extensión `.geojson`). |
| `scenario.json` / `scenario.geojson` | Salida real ya generada: baseline sin cámaras contra FIRMS, estado `paused-next-phase`. |
| `model.py`, `grid.py`, `dem.py` | Propagación de tiempo mínimo en malla de 200 m con DEM real (AWS Terrarium z12, `dem/`), viento horario Open-Meteo. Constantes de `simulation.py` (importadas, sin editarlo). |
| `assimilate.py`, `experiment.py`, `metrics.py`, `data.py`, `config.py` | Verosimilitud angular set-valued, ciclos causales, métricas, puertas, configuración congelada. |
| `preregistration.json` | Configuración congelada + SHA-256 (`4ee3c516…`). Un hash en un archivo no es sello externo: hay que commitearlo antes de correr datos reales. |
| `test_assimilation.py` | 19 pruebas sobre fixtures **sintéticos** (y 1 humo con capas Garnet reales sin cámara). No son resultados reales. |
| `report.md` | Informe. |

## Reproducir

```sh
cd tools/firetrace/camera_assimilation/assimilation
python3 -m unittest test_assimilation          # 19 pruebas, ~8 s
python3 run.py --observations ../vision/observations.json \
               --calibration ../calibration/printed_model.json \
               --output scenario.json \
               --paused-reason "<motivo>"        # fase pausada: baseline, cámaras = 0
# Reanudar (cuando haya bases visibles): quitar --paused-reason; añadir --sensitivity para las variantes.
# Contraste ajustado: --calibration ../calibration/calibration.json --allow-experimental --output scenario-fitted.json
```

Sin `--paused-reason`: archivo de observaciones/calibración ausente → `pending-inputs`; ninguna fila supera las puertas → `disabled`; si hay filas → `completed`.
Requisitos: Python 3.11, numpy, scipy, shapely, Pillow (solo para reconstruir el DEM). `python3 dem.py --offline` reconstruye el DEM desde `dem/tiles`.

## Esquema de `scenario.json` (`firetrace-camera-assimilation-scenario-v1`)

`schema, status (completed|disabled|pending-inputs|paused-next-phase), statusReason, outcome, retrospective:true, operationalForecast:false, dataClasses[], initialization{t0,t0Utc,mode,cells,retrospectiveLeakage:true,leakage[],alternativeWithInterpolatedCells,passesAtOrBeforeT0}, cameraModel{calibrationBasis,parameterOrigin,calibrationStatus,poses[],angularSigmaDegByRow,clock{status,sigmaMin,verified:false},historicalXStatus,fittedToFirms,bearingFormula}, cameraUseCount, cameraEffectiveCount, idList{t0Id,configSha256,assimilatedObservationIds,effectiveObservationIds,excludedObservations[],reservedByCalibrationSplit,observationsUsedInCalibrationFit,cycles[],passRoles{},validationPassIds,diagnosticPassIds,unmatchedNominalLeads}, preregistration, model, baseline{passes[]}, corrected{status,reason | cycles[]}, forecasts[], metrics{primaryMetric,toleranceM,definitions,verifications[],aggregate,worsenedDisclosure}, sensitivity, excludedObservations, limitations, geojson`.

- `baseline.passes[]`: `{passId, role, source, passUtc, leadFromT0Min, toleranceM, metrics{detections, growthDetections, activeBandCells, newBurnedCells, medianNearestActiveBandM, recallAnyFootprint, recallGrowth, recallActive, precisionActive, f1Active, p90NearestActiveBandM}}`. Se puntúa en el **tiempo real de cada pasada**.
- `forecasts[]` (solo con ciclos): `{cycleId, issueUtc, validUtc (=issue+lead), leadMin (30|60), baseline{featureId,newBurnedCells}, corrected{featureId,newBurnedCells,identicalToBaseline,cellsChanged}, cycleStatus}`.
- `metrics.verifications[]` (solo con ciclos): `{passId, cycleId, issueUtc, latestObservationUtc, actualLeadMin, nominalLeadsMin, deltaFromNominalMin{"30":x}, declaredLeadMismatch, causalCheck, metrics{baseline,neutralEnsemble,corrected}, tolerancesSensitivity[], verdictCorrectedVsBaseline (improved|worsened|identical|unchanged-within-tolerance|not-evaluable), deltaPrimaryM}`.

## Esquema de `scenario.geojson` (`firetrace-camera-assimilation-map-v1`)

`FeatureCollection` con `properties{schema,status,retrospective,operationalForecast,featureKinds,note}`. Cada feature tiene `properties.kind`, `dataClass`, `featureId`:

| `kind` | geometría | propiedades clave |
|---|---|---|
| `initialization-footprint` | MultiPolygon/Polygon | `dataClass:"reconstructed"`, `t0Utc` |
| `forecast-footprint` | (Multi)Polygon | `product: baseline\|corrected`, `cycleId, issueUtc, validUtc, leadMin, cells`. Celdas que arden **después de t0** (unir con la inicial). Si corrected = baseline solo se emite `baseline` y `forecasts[].corrected.featureId` apunta a él. |
| `forecast-delta` | (Multi)Polygon | `product: corrected-added\|corrected-removed` |
| `verification-footprint` | (Multi)Polygon | `product, passId, validUtc` (hora real de la pasada), `cycleId` o `null` (baseline desde t0, `leadFromT0Min`) |
| `validation-detection` | Point | `passId, role, source, passUtc, frpMW, pixelM` (`dataClass:"observed"`) |
| `camera`, `camera-bearing-wedge`, `camera-bearing-ray` | Point / Polygon / LineString | solo con cámaras usadas; el rayo/sector es compatibilidad angular, **no** localiza distancia |

Con `paused-next-phase`/`disabled`/`pending-inputs` solo aparecen `initialization-footprint`, `verification-footprint` (baseline) y `validation-detection`.
