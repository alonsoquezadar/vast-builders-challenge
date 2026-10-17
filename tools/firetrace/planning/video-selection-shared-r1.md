# FireTrace: selección de video (VIDEO_URLS.txt) · revisión compartida R1

**Autor:** hilo secundario (t3-d639e045), 2026-10-17. Solo escribe este archivo; el resto del worktree se leyó sin modificarlo.
**Alcance:** los 9 enlaces de Wikimedia Commons de `VIDEO_URLS.txt`. No se revisó el enlace de Zenodo (BurnedAreaUAV, 910 MB).
**Método:** metadatos de la API de Commons (licencia, autor, wikitext). Descarga del original (ALERTCalifornia, Monserrate, BLM) o del transcode 480p (Pomona, Wennington, Coffey Park, Hawaii). Hojas de 12 fotogramas por video. Lectura de la barra impresa cada 0,5 s, detectando cambios de pose, con verificación manual cada 4–6 s en los tramos dudosos. Cruce con el catálogo público `all_cameras-v3.json` (leído el 2026-10-17).
**No hecho:** ingestión en VAST, análisis con Cosmos de estos fotogramas (está autorizado, pero no se ejecutó en esta revisión), consulta FIRMS de archivo, descarga de fuentes originales en YouTube.

Leyenda: ✅ comprobado en esta revisión · ⏳ pendiente · ❌ descartado o no disponible.

---

## Ranking

| # | Video | Fuente · cámara · fecha impresa | Llamas / contacto con suelo | Continuidad de pose | Referencias geográficas | Veredicto |
|---|---|---|---|---|---|---|
| 1 | **Garnet Fire Afternoon Growth Compilation** | ALERTCalifornia / UCSD, crédito PG&E en imagen · `axis-delilahlookout2` + `axis-buckrock1` · 2025/08/27 | ✅ Bases de columnas sobre laderas de día. ✅ Línea de llamas nocturna (Delilah, ~20:16). Buck Rock: la base queda en parte tras una cresta | ✅ 2 tramos largos de pose fija, **simultáneos 16:11–20:16** | ✅ Posición pública de ambas torres (redondeada). ✅ Origen del incidente según CAL FIRE | **Mejor candidato para un caso de dos vistas** |
| 2 | **Palisades Fire Compilation** | ALERTCalifornia / UCSD (+ UCSD/HPWREN/SIO/SDSC, LADWP, CAL FIRE) · `wilshire2`, `hel69b-east`, `temescaltrailhead2`, `topangapeak2` · 2025/01/07–08 | ✅ Llamas sobre ladera con contacto con suelo (Temescal, Topanga de noche). Humo sobre crestas de día (Hel69B) | ✅ Topanga ~4 h, Temescal ~1 h. Wilshire2 cambia zoom y pan seguido | ✅ Posición pública de las 4 cámaras. Mucha infraestructura urbana reconocible | Alternativa fuerte para una sola vista con fuego visible |
| 3 | **Blue Ridge Fire** | ALERTWildfire / NV Seismo Lab, crédito CAL FIRE · `Axis-GypsumCanyon1` · 2020/10/27 | ✅ Frente nocturno muy cercano. ✅ De día, foco pequeño con humo en ladera (~06:16) | ✅ X:-71.99 Y:-17.75 Z:1.0 de 05:35 a ~07:49 (vídeo 79–151 s) | ✅ Posición pública. Carretera y tendido visibles. ⚠ La torre tapa parte del encuadre | Complemento de fuego cercano, una vista |
| 4 | Wildfire Near Monserrate | Peter Angritt · sin ID de cámara · 2015-10-31 | ✅ Llamas pequeñas en la base del humo (teleobjetivo) | ⏳ Aparentemente estable, sin metadatos | ❌ Sin posición ni orientación (Bogotá) | Solo referencia visual |
| 5 | BLM drone reconnaissance (North Umpqua) | BLM OR/WA, dron IR · sin pose · según descripción, incendio de 2017 | ✅ Firma térmica de fuego (paleta IR) | ❌ Dron en movimiento | ❌ Sin telemetría | Solo para ilustrar una vista IR |
| 6 | Drone footage of Fire in Pomona | Wes Kriesel · dron · 2022-09-08 | ❌ Columna lejana, sin base visible | ❌ Dron en movimiento | ❌ | Descartado |
| 7 | Wennington wildfire 2022 | Harri Healey · dron · 2022-07-19 | Humo residual y área quemada; sin frente activo | ❌ | ❌ | Descartado (posterior al incendio) |
| 8 | Coffey Park Aerial Reel | BAMM · dron · 2017-10-11/13 | ❌ Daños posteriores | ❌ | ❌ | Descartado |
| 9 | B-Roll of Hawaii Wildfire | FEMA · cámara de mano · 2023-08 | ❌ Daños y entrevistas | ❌ | ❌ | Descartado |

---

## 1. Garnet: detalle de tramos (comprobado de la barra impresa)

Fuente Commons: `File:Garnet_Fire_Afternoon_Growth_Compilation.ogg`. 640×360, 279,6 s, 26,9 MB, sha256 `2d54936d…4240`. Commons solo cita como fuente `https://www.youtube.com/c/ALERTCalifornia`, sin URL del video concreto (⏳ localizarla).

| Tramo | Segundos de vídeo | Cámara | Pose impresa (X / Y / Z) | Hora impresa | Contenido |
|---|---|---|---|---|---|
| G1 | 0–39,5 | delilahlookout2 (elev 5151′) | +26.27 / -0.70 / 1.2 | 10:30–13:44 | Columna naciente sobre ladera, base visible |
| — | 39,5–82 | delilahlookout2 | 4 poses distintas (operador FKU) | 13:49–~16:10 | No apto para calibrar |
| G2 | 82–~136 | delilahlookout2 | +25.27 / +7.34→+7.33 / 1.0 | 16:11–20:16 | Pirocúmulo, varias columnas con base en ladera; de noche, línea de llamas |
| G3 | 137–148 | buckrock1 (elev 8468′) | -52.81 / -8.41 / 1.0 | 10:32–10:41 | Paisaje previo |
| G3b | 149–~188 | buckrock1 | -39.19 / -0.94 / 1.0 | 11:27–13:59 | Columna lejana |
| G4 | ~188–279,6 | buckrock1 | -26.13 / +7.89 / 1.4 | 14:08–20:54 | Pirocúmulo; base en parte tras una cresta; resplandor de noche |

✅ **G2 y G4 coinciden 16:11–20:16 (hora impresa), con pose fija en ambas torres.** Es la única pareja simultánea de todo el lote.
⚠ Es un timelapse con muestreo irregular (~1 cuadro cada 2–5 min de hora real por cuadro de vídeo). La hora debe salir de la barra, no de la posición en el vídeo.
⏳ Zona horaria no verificada (igual criterio que en Plaskett). ⏳ Sincronía de reloj entre torres no verificada.

### Referencias geográficas

| Elemento | Valor | Estado |
|---|---|---|
| Axis-DelilahLookout2 | lon -119.12, lat 36.80, 1570 m (coincide con 5151′ impresos) | ✅ catálogo público, **redondeado a 0,01°** (≈ ±0,5 km) |
| Axis-BuckRock1 | lon -118.86, lat 36.74, 2578 m (coincide con 8468′) | ✅ catálogo, redondeado |
| Origen del Garnet Fire | 36.865, -119.028; inicio 2025-08-24 14:13; causa: rayo | ✅ ficha CAL FIRE |
| Rumbo Delilah → origen | 48,5°, 10,9 km | ✅ calculado (con la posición redondeada) |
| Rumbo Buck Rock → origen | 312,9°, 20,4 km | ✅ calculado |
| Ángulo entre las dos visuales | ~95° | ✅ buena geometría *si* hubiera calibración |
| Relación X impreso ↔ azimut verdadero | Delilah X≈+25–26 frente a 48,5° hacia el origen; Buck Rock X≈-26…-39 (334–321°) frente a 312,9° | ❌ **No consistente.** X no es un azimut geográfico usable sin calibrar, o el fuego del 27/08 ya no está en el origen (lo segundo es esperable: ~4.400 ac el 25/08 y ~18.700 ac el 31/08) |

**No se puede afirmar un incendio geolocalizado con este material.** Para triangular faltan:
1. Calibración de cada torre (offset de pan, campo de visión efectivo y tilt) con referencias del terreno identificadas en el fotograma y en el DEM, como en el flujo de `alignment.html`.
2. Posición de cámara mejor que 0,01°, o mantenerla fija y aceptar el error, como en Rocky Butte.
3. Sincronía y zona horaria.
4. **Correspondencias:** el mismo rasgo (base de una columna concreta) identificado en las dos vistas. Las columnas de G2 y G4 no son trivialmente el mismo punto; la base en G4 queda en parte oculta.

---

## 2. Palisades: detalle de tramos

Commons `File:Palisades_Fire_Compilation,_Los_Angeles_County,_CA_Jan._2025.ogg`. 640×360, 172,4 s, sha256 `71d7172c…cd1d`.

| Segundos | Cámara | Pose | Hora impresa | Contenido |
|---|---|---|---|---|
| 0–40 | wilshire2 (95′) | Cambia 5 veces (Z 13,1→1,0→3,4→2,0) | 01/07 10:44–11:55 | Columna sobre la ciudad. Tramo estable más largo: X-50.20 Z2.0, 11:33–11:55 |
| 40,5–~70 | hel69b-east (2454′) | +115.50 / -2.50 / 1.1→1.5 | 01/07 14:18–16:14 | Humo sobre crestas, base parcial |
| ~72–~84 | hel69b-east | +117.93 / -1.34 / 1.5 | 16:26–16:51 | |
| ~88–100 | hel69b-east | +123.87 / -0.51 / 1.0 | 16:56–17:38 | |
| 101,5–~120 | temescaltrailhead2 (1627′) | +156.83 / -1.89 / 1.0 | 01/07 22:32–23:42 | **Llamas con contacto con suelo**, de cerca, saturado |
| 121,5 | topangapeak2 (2569′) | +106.70 / -9.31 | 01/08 16:02 | |
| 139–172 | topangapeak2 | +107.09 / -9.29 / 1.0 | 01/08 17:57–21:52 | **Frente nocturno sobre ladera**, contacto con suelo, ~4 h estables |

Posiciones públicas: Wilshire2 (-118.50, 34.02), Hel69B (-118.63, 34.07), TemescalTrailhead2 (-118.55, 34.08), TopangaPeak2 (-118.64, 34.08), todas redondeadas. ⏳ No hay dos vistas estables simultáneas: los tramos de cada cámara no se solapan en hora impresa.

## 3. Blue Ridge: detalle

Commons `File:Blue_Ridge_Fire.ogg`. 150,8 s, sha256 `d1869937…e357`. Una sola cámara, `Axis-GypsumCanyon1` (catálogo: -117.75, 33.89, 288 m). Barra con crédito "NV Seismo Lab · ALERTWildfire.org" y hora impresa 2020/10/27 03:00–~07:49.
Poses: -8.92/+8.87 (03:00) → -9.06/+2.43 (03:51–04:02) → -68.54/-9.05 (04:25) → **-71.99/-17.75 Z1.0 (05:35–~07:49)**. En el último tramo hay foco pequeño y humo en ladera con luz de día. La estructura de la torre ocupa ~1/3 del encuadre.

---

## Derechos: pendiente, no resuelto

- ✅ Commons etiqueta los 3 videos de ALERTCalifornia como `{{PD-automated}}`, con autor "University of California, San Diego" y fecha `{{circa|2013-2015}}`. **Esa fecha es errónea:** las barras muestran 2020 y 2025. Es una plantilla de subida masiva (pattypan), no una declaración del titular.
- ✅ `footage-sources.md` de este worktree recoge que los términos de ALERTCalifornia indican **CC BY-NC-ND 4.0** y piden crédito "ALERTCalifornia | UC San Diego". La etiqueta PD de Commons **no prevalece** sobre eso para nuestro uso.
- ⏳ El autor no declara que cortar, transcodificar o anotar sea compatible con ND. Es el mismo caso que el clip de Plaskett ya en `evidence/`.
- ⏳ Sigue vigente la pregunta a la organización sobre analizar fotogramas sin ingerir en VAST. El usuario ya autorizó el análisis con Cosmos; la ingestión en VAST sigue fuera de alcance.
- Créditos visibles en imagen que deben conservarse: ALERTCalifornia, UC San Diego, PG&E (Garnet); CAL FIRE, LADWP, UCSD/HPWREN/SIO/SDSC (Palisades); CAL FIRE, NV Seismo Lab, ALERTWildfire (Blue Ridge).
- Drones: Pomona, Wennington y Coffey Park son CC BY 3.0 (atribución obligatoria). Monserrate es CC BY-SA 4.0. BLM y FEMA están en dominio público como obra federal (según Commons; ⏳ no verificado en origen).

## FIRMS

⏳ No consultado para 2025-08-27 (Garnet) ni 2025-01-07/08 (Palisades). El visor actual solo trae los últimos 7 días. Si se añade, son **puntos térmicos** (VIIRS ~375 m) con hora de paso del satélite: no son frente, área ni velocidad, y no validan por sí solos qué columna ve cada cámara.

---

## Recomendación para el hilo principal (sin tocar código)

1. **Mantener Plaskett/Rocky Butte** como caso de alineación de una vista en curso. No hace falta reemplazarlo.
2. Si se quiere demostrar **dos vistas**, el único material del lote que lo permite en principio es **Garnet G2 (Delilah) + G4 (Buck Rock), 16:11–20:16**. Requiere los 4 pendientes de calibración de arriba. Hasta resolverlos, presentarlo como "dos cámaras observan el mismo incidente", sin un punto triangulado.
3. Para una vista con **fuego en contacto con el suelo**, el mejor material es **Palisades Topanga (139–172 s)** o **Delilah nocturno (G2, ~130–136 s)**.
4. Antes de usar cualquiera: localizar la URL original en el canal de ALERTCalifornia y resolver la licencia ND.

## Artefactos locales (fuera del repo, no copiados aquí)

- Videos descargados: `/tmp/firevids/` (los sha256 completos están abajo).
- Hojas de fotogramas: `/tmp/firevids/grids/`, `/tmp/firevids/kf/garnet6.jpg`, `/tmp/firevids/kf/pb6.jpg`.
- Lectura de barras: `/tmp/firevids/ov/*-segs.png`, `g-tail.png`, `p-mid.png`.

```
2d54936d96ab5c3e6c8786282e1e86a4235d7504e84f8f76f132374f4ddf4240  garnet.ogg
71d7172c7e176d5457c3e9a5a8a50f49c605cd4b4587e403a1eedf5918d1cd1d  palisades.ogg
d18699373c4f9969c1802456a39fb064b52776906220ff55512b46d84803e357  blueridge.ogg
73c6d39e6a648343c215a5d3c5c4789c0d439bf868a8320e3c8e00b50ba1ddf2  monserrate.ogv
b5967fea4271b66e29c50033ca00dd4abec263a61f94716556a0c45e98867799  blm.webm
55b5df0257d949178bd0aa2225f51bc2dd2d47b872fd8762267f362b7356f6d4  pomona.webm (480p)
5bfc65487ce9c961d6ef64cc20590ad3060315333b5ccd6a75e22862500949f4  wennington.webm (480p)
cb079f84f9439e3710ab406dd981e15ee36a025b53a63a29b0a8c188ef1cf439  coffey.webm (480p)
78acda0a9987eb6319336440a44c9a75f652a0a09de81e31fea98566d9782417  hawaii.webm (480p)
```

## Fuentes

- Commons API (`imageinfo` + wikitext) de cada archivo listado en `VIDEO_URLS.txt`.
- Catálogo ALERTCalifornia: https://cameras.alertcalifornia.org/public-camera-data/all_cameras-v3.json
- CAL FIRE, Garnet Fire: https://www.fire.ca.gov/incidents/2025/8/24/garnet-fire
- USFS, Garnet Fire update del 25/08/2025: https://www.fs.usda.gov/r05/sierra/newsroom/releases/garnet-fire-update-august-25-2025
- Sierra News Online (crecimiento al 31/08): https://sierranewsonline.com/garnet-fire-update-3/
