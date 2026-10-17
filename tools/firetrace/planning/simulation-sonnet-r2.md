# Escenario de propagación ilustrativo (r2)

Base: `f9ff0ac82db5ba7515bcb345dfeceda8aca4277a`. Archivos: `simulation.py`, `test_simulation.py`, `simulation.html|js|css`.

## Estado
Ilustrativo y no validado. No es predicción, ni Rothermel/FARSITE, ni perímetro observado. Viento y combustible son supuestos del operador; no hay mediciones. La semilla la elige el operador (mapa, referencia CAL FIRE de Plaskett o punto con DEM guardado), nunca se deriva de Cosmos.

## Contrato (fijo)
`simulate(data) -> dict`, solo stdlib; `ValueError` si el dato es inválido.
`data = {origin:[lon,lat], grid:{origin, cellSizeM(10..200; root usa 50), elevations[[m]]}, windFromDeg 0..360 (meteorológico DESDE), windSpeedMps 0..30, baseSpreadMMin 0.1..30, fuelFactor 0.1..2, durationMin 1..60, terrain?:{terrainSource,terrainFetchedAt,terrainStatus}}`.
Rejilla cuadrada impar 21..61, filas norte→sur, columnas oeste→este, centro = origen; `origin` y `grid.origin` deben coincidir (1e-6°). Se rechazan None, NaN, inf, bool, texto, filas irregulares y altitudes fuera de −500..9000 m. No se inventa relieve.

## Modelo (coeficientes heurísticos, sin validar)
`tasa = base·combustible·W·S`; `W = exp(0,06·v·cos(rumbo − haciaDondeSopla))`; `S = clamp(exp(3·pendiente), 0,25, 4)`; `tiempo = distancia/tasa`; llegada = camino mínimo (Dijkstra, 8 vecinos) cortado en `durationMin`. Sesgo de rejilla hasta ~8 %. Sin humedad, pavesas, supresión, mapa de combustible ni meteorología.

## Salida
FeatureCollection de celdas Polygon (escala métrica local, `properties.arrivalMin`, `row`, `col`, `elevationM`) y `properties`: `mode:'illustrative-scenario'`, `validated:false`, `label`, `assumptions`, `limitations`, `seedSource`. Solo celdas con llegada ≤ duración. Peor caso 61×61 medido <3 s en pruebas.

## Integración en root (lo hace el coordinador)
- `GET /api/scenario-terrain?lon=&lat=` → rejilla 41×41, 50 m, `terrainSource:'AWS Terrarium'`, `terrainStatus:'real-dem'`, `terrainFetchedAt`.
- `POST /api/simulate` {origin, 5 supuestos}: root añade la rejilla y llama `simulate`. La UI no envía rejilla.
- Enlazar `simulation.html` desde root; no se tocó `incident.*`.

## Verificación hecha
`python3 -B -m unittest test_simulation`: 9 pruebas sintéticas (isotropía plana y calma, más alcance a favor del viento, viento DESDE, cuesta arriba más rápida, nada tras el horizonte, contrato/geometría, determinismo, rechazos, peor caso). Smoke manual: instancia propia en puerto 5199 con el `main.py` del árbol de trabajo (GET DEM guardado + POST → 123 celdas; viento 999 → error 'falta…'/rango) y UI en navegador (semilla → DEM → ejecutar → timeline; cambiar un supuesto borra el resultado).

## No validado
Ninguna exactitud contra incendios reales ni campo; coeficientes sin ajuste; DEM recuperado en tiempo de ejecución (fecha ≠ adquisición); posición CAL FIRE y punto guardado solo son semillas hipotéticas; exportación GeoJSON con procedencia no revisada por terceros.
