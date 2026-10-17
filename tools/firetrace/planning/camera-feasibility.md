# FireTrace: viabilidad de cámara ALERTCalifornia y georreferenciación

Estado: **ISSUES**. El rumbo con incertidumbre se puede defender hoy. La proyección al DEM y la triangulación no. Falta una prueba positiva autorizada, así que no puede afirmarse ninguna ubicación de fuego a partir de cámara.

Solo lectura. Evidencia del 2026-10-17 a las 12:37Z: un GET al catálogo público de metadatos y dos teselas Terrarium. No se descargó ningún fotograma ni video, no se llamó a GPU/VAST/ingest y no se usaron credenciales.

## 1. Fuentes

- Catálogo: `https://cameras.alertcalifornia.org/public-camera-data/all_cameras-v3.json` (el de `main.py:15`). HTTP 200, 2 796 884 bytes, 2 283 registros, 1 316 con coordenadas numéricas (el resto trae `null`). El README dice 1 314: el recuento cambia.
- Visor: `https://cameras.alertcalifornia.org/?id=<id>` (`app.js:95`).
- Campos: `id, name, last_frame_ts, fov_lft, fov_rt, fov_center, fov, ProdNbr, az_current, tilt_current, zoom_current, is_patrol_mode, is_currently_patrolling, state, county, isp, sponsor, region`. Geometría `[lon, lat, elevación]`.
- La página principal no enlaza términos de uso ni licencia. **No verificado.**

## 2. Cámaras de referencia (valores públicos literales)

El centro por defecto del mapa es `[-121.97, 41.38]` (`app.js:10`). Es el centro del visor, no un fuego confirmado.

| id | posición | elev. | az / tilt / zoom | fov | dist. | rumbo al centro | ¿en campo? |
|---|---|---|---|---|---|---|---|
| `Axis-ShastaSkiPark` (Q6055-E) | -122.2, 41.33 | 1977 | 197.72° / -1.0° / 1.0 | 62.8° | 20.0 km | 73.8° | No (Δ -123.9°) |
| `Axis-BearMtnLookout1` (Q6075-E) | -121.72, 41.3 | 1774 | 92.11° / 0.0° / **2.0** | 65.1° | 22.7 km | 293.2° | No (Δ -158.9°) |
| `Axis-BearMtnLookout2` | -121.72, 41.3 | 1774 | 236.06° / 0.0° / 1.0 | 65.1° | 22.7 km | 293.2° | No (Δ 57.1°) |
| `Axis-GrizzlyPeakShasta1` | -121.98, 41.14 | 1901 | 342.58° / 0.0° / 1.0 | 65.1° | 26.7 km | 1.8° | **Sí** (Δ 19.2°) |
| `Axis-SodaRidge1` | -122.24, 41.22 | 1414 | 70.39° / -0.5° / 1.0 | 65.1° | 28.7 km | 51.6° | **Sí** (Δ -18.7°) |

Shasta Ski Park y Bear Mountain **no apuntan hacia el centro ahora**, y la cámara es PTZ que no podemos mover. La referencia útil es `Axis-GrizzlyPeakShasta1`. Con `Axis-SodaRidge1` cruza a 49,8°. Los valores son de la consulta y cambian si la cámara patrulla (13 de 1 316 tienen `is_patrol_mode=1`).

## 3. Precisión, altura, pose y FOV

**Posición.** Dos decimales (1 196 de 1 316) o uno (120). Con dos, el error máximo es ±556 m en latitud y ±418 m en longitud, unos **±0,7 km**. A 20 km son ~2° de rumbo solo por la cuadrícula.

**Elevación.** Entero en metros, no altura sobre el suelo. Contra el DEM Terrarium z12 (`https://s3.amazonaws.com/elevation-tiles-prod/terrarium/12/{x}/{y}.png`), en nueve muestras dentro de la caja de redondeo ±0,005°:

- Shasta Ski Park: publicado 1 977 m, DEM 1 733 a 2 086 m (**353 m** de dispersión).
- Bear Mountain: publicado 1 774 m, DEM 1 509 a 1 732 m. El publicado queda **42 m por encima** del máximo.

La altura del mástil no está publicada.

**Pose.** `az_current` tiene decimales de float y `tilt_current` uno. Es resolución numérica, no exactitud. No hay alabeo, referencia de norte ni error declarado. **Exactitud no validada.**

**FOV y zoom.** `fov` es constante por modelo (65,1° en 967 cámaras, 62,8° en 349) y no depende de `zoom_current`. `Axis-BearMtnLookout1` tiene zoom 2,0, pero su cuña `fov_lft`→`fov_rt` mide 64,8°: ignora el zoom. Con zoom ≠ 1 el FOV real es desconocido y menor. Los puntos `fov_lft/center/rt` están a 32,2 km fijos en las tres cámaras revisadas: es geometría de dibujo, no un alcance.

**Intrínsecos.** Resolución, distorsión y centro óptico no se publican. Hay que leerlos del fotograma. Las fichas del fabricante no se verificaron.

## 4. Correspondencia temporal de un fotograma

El único sello público es `last_frame_ts` (epoch s). Para Shasta Ski Park fue 1792240541 (12:35:41Z), 130 s antes de la consulta. `az/tilt/zoom` son los **actuales**, no los del instante del fotograma, y no hay histórico.

El código hoy no conserva nada de esto. `capture-frame` (`app.js:113`) toma un fotograma de un MP4 local sin vínculo con ninguna cámara. `state.camera` (`app.js:97`) queda congelada al hacer clic y no se refresca cuando `loadCameras` recarga el catálogo.

Protocolo mínimo:

1. Leer el catálogo justo **antes** y **después** de ver el fotograma. Guardar ambas instantáneas (`az, tilt, zoom, fov, last_frame_ts, is_patrol_mode`) y la hora de lectura.
2. Aceptar solo si ambas coinciden en `az/tilt/zoom` y `is_patrol_mode=0`. Si no, la pose es desconocida y se rechaza.
3. `observedAt = last_frame_ts` en ISO 8601 con zona (lo que exige `validateObservationCollection`); `metadataReadAt` aparte.
4. Un MP4 local no se puede atar a una pose pública. La cámara y la hora las declara el operador y queda `operator-supplied`.

## 5. Las tres rutas

**A. Rumbo con incertidumbre. Viable hoy.** Dibujar una **cuña de visibilidad**, no una línea de fuego: `az ± fov/2` más ~2° de colchón por posición. Etiqueta: "dirección de observación de la cámara; no es ubicación de fuego ni distancia". Con una columna elegida por el operador en el fotograma: `az_píxel = az + atan((2x/W − 1)·tan(fov/2))`, solo con zoom 1. Resultado: una semirrecta con ±2° a ±3° (≈±1 km a 20 km). Esfuerzo: 1 a 2 h sobre `geo.mjs` y `app.js:97`, sin dependencias.

**B. Proyección de la base visible al DEM. No hoy.** Con tilt cercano a -1° el rayo es rasante: la distancia al suelo es `h / tan(depresión)` y `h` es desconocida. Una variación de 350 m (dispersión DEM de la sección 3) mueve el impacto decenas de km. Además faltan alabeo, FOV efectivo con zoom ≠ 1 y distorsión, y la base de una columna lejana suele estar tapada por relieve. Haría falta calibrar con ≥3 puntos de control (cresta, torre, cruce) y validar contra una verdad conocida. Estimación: 1 a 2 días, con riesgo alto de no converger.

**C. Triangulación con 2 cámaras. No hoy.** `Axis-GrizzlyPeakShasta1` y `Axis-SodaRidge1` cruzan a ~50°, buena geometría. Pero ~2° por rayo a 27–29 km deja una intersección de **1 a 1,5 km** (orden de magnitud, no medido). Además ambas deben ver **la misma columna** a la **misma hora**, y la cadencia de `last_frame_ts` no se midió. Dos azimuts publicados no demuestran que ambas cámaras vean lo mismo.

## 6. Reglas del challenge sobre footage externo

`README.md:257-258`: "Don't ingest videos from the internet (e.g. YouTube). We picked the provided video sources specifically because their licensing allows this use." `README.md:266-276` lista el material provisto (dashcam, autopista multicámara, cámara de vecindario) y `ARCHITECTURE_REFERENCE.md:86-130` el corpus indexado. Ninguno muestra incendios.

- **No ingerir en VAST** video ni fotogramas de ALERTCalifornia, ni el video de referencia de Dilum Sanjaya. El README de FireTrace ya lo declara.
- Enviar un fotograma de ALERTCalifornia a Cosmos no es "ingest", pero tampoco está confirmado como permitido y los términos de uso no se verificaron. Preguntar a los organizadores antes de hacerlo en la demo, o mostrar solo metadatos y el enlace al visor.
- No hay positiva dentro del material permitido.

## 7. Mínimo defendible HOY y prueba necesaria

**Afirmación sostenible:** "Para la cámara X en el instante T, su dirección publicada cubre / no cubre el punto Y (detección FIRMS o perímetro WFIGS), con ±fov/2 más ~2° de posición. No se infiere distancia, ubicación del fuego ni perímetro." Implementación: cuña, instantáneas antes/después y bandera "pose incierta". Sin desplegar y sin tocar `pulse-corridor` en `/app`.

**Prueba negativa (reproducible ya, con datos públicos):**
- Con `Axis-ShastaSkiPark` (Δ -123,9°) y `Axis-BearMtnLookout1` (Δ -158,9°), el centro `[-121.97, 41.38]` **debe quedar fuera** de la cuña.
- Prueba unitaria en `geo.test.mjs`: cámara en A, objetivo en B a rumbo conocido dentro de la cuña; objetivo a ≥90° fuera. Un fotograma sin humo no debe producir marcador.

**Prueba positiva: BLOQUEADA.** Para afirmar una ubicación se necesita todo esto a la vez:
1. Un fotograma con humo o llama inequívoco y uso autorizado.
2. Pose y hora verificadas (sección 4).
3. Una verdad independiente (punto FIRMS o WFIGS cercano en hora) dentro de la cuña predicha y a distancia compatible con el relieve.
4. Resultado redactado como "consistente con", no como localización.

Una escena de cámara **sin fuego no sirve como positiva**: solo valida "no hay detección". Tampoco debe derivarse un perímetro desde un punto de humo: ninguna prueba disponible lo respalda.

## 8. Reproducir

```sh
curl -sS -A 'FireTrace-hackathon/0.1' -o cams.json https://cameras.alertcalifornia.org/public-camera-data/all_cameras-v3.json
# python3 -I: filtrar por id; rumbo/distancia al centro [-121.97,41.38]; comparar fov_center con az_current
# DEM: z = r*256 + g + b/256 - 32768 sobre la tesela Terrarium z12
node --test tools/firetrace/geo.test.mjs   # no se ejecutó en este slice
```

## 9. Limitaciones

- Exactitud de `az_current`, `tilt_current` y posición no validada contra verdad conocida.
- Hardware deducido de `ProdNbr`, no de fichas del fabricante.
- Cadencia de fotogramas no medida. Términos de ALERTCalifornia no localizados.
- Cálculos esféricos como `geo.mjs`; los errores de la sección 5 son órdenes de magnitud.
- No se ejecutó la suite del repositorio ni se comprobó el estado actual de incendios en la zona.
