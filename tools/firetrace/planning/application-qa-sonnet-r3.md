# QA de la aplicación (incident.html) — Sonnet r3

Base pedida: `f9ff0ac82db5ba7515bcb345dfeceda8aca4277a`. `git rev-parse HEAD` al terminar: `31750cbfff0d42c2fa8a09a068fad20cbf10eae5` (root confirmó otro commit durante la sesión; no toqué Git).
Demo: `http://localhost:5173/incident.html`, pestaña propia de T3 preview. `/api/status` → `cosmos: true, mode: replay`.
Se usó `POST /api/analyze` (autorizado) con fotogramas de la propia evidencia, sin VAST y sin exponer secretos. Los errores se simularon sustituyendo `fetch` solo para `/api/analyze` dentro de la página.

## Defectos reproducidos antes de corregir

| # | Reproducción | Resultado antes |
|---|---|---|
| 1 | Cambiar de cámara y, en el mismo tick (video aún sin metadatos), de momento (Buck Rock, 16 h → 20 h) | Texto/imagen en 20:09:08 pero el video quedó en 32 s (fotograma 222, 16:26). Esperado 77 s. |
| 2 | Fallo de inferencia con cuerpo `{}`, HTML 502 o red caída | Mensajes `No se completó la inferencia:  La respuesta…` (vacío), `Failed to execute 'json' on 'Response': Unexpected token '<'…`, `Failed to fetch`; sin punto entre frases. |
| 3 | Pedir inferencia en Delilah y pasar a Buck Rock antes de la respuesta con error | El error de Delilah aparecía bajo Buck Rock; la tarjeta de estado de otra cámara quedaba mintiendo. |
| 4 | Inferencia real en `delilah-110` | La corrección de procedencia (escrita para la respuesta guardada) seguía bajo el texto nuevo; el estado volvía a «Ubicación sin resolver» sin confirmar que llegó la respuesta. |
| 5 | Exportar tras una inferencia real | El JSON traía la nota de revisión pero ya no la respuesta guardada que corrige (`2026-10-17T13:47` ausente). |
| 6 | Marcador de cámara pulsado en móvil 390 | La selección solo cambiaba opacidad del marcador y contenido fuera de pantalla; sin texto visible de la cámara elegida junto al mapa. |
| 7 | Sin Cosmos en el servidor (`/api/status` falla/false) | Botón desactivado sin explicación (por lectura de código; no se pudo apagar el servidor en la sesión). |
| 8 | Botón «Recorrido» en marcha | `aria-label` fijo «Reproducir recorrido» aunque el texto decía «Pausar» (por lectura de código/DOM). |

## Sin defecto (comportamiento demostrado)

- 3 momentos × 2 cámaras resuelven el par correcto; diferencias impresas 10, 3 y 8 min; `synchronized:false`, sin afirmar sincronía ni zona horaria.
- Seek del video: los 6 tiempos (3, 27, 51 s en Delilah; 32, 54, 77 s en Buck Rock) caen dentro de las duraciones (52.0 s y 87.7 s). Comparación PSNR fotograma-vs-video ≥ 35 dB en 5 de 6; `buckrock-222` coincide mejor a ~31.5 s (diferencia < 1 s en una compilación acelerada). No se cambió.
- Exportación genera `firetrace-garnet-evidence.json` (14 KB) con `selectedMoment`, `selectedCamera`, par, `synchronized:false`, `geolocation:"unresolved"`, `propagationModel:null`, `firmsHistoricalData:null`.
- Móvil 390 y escritorio 1440: `scrollWidth == clientWidth`, ningún elemento fuera del viewport (salvo el canvas del mapa, recortado por su contenedor). Los enlaces de navegación miden 12 px de alto (táctil pequeño); no se tocó.
- Las 2 correcciones de procedencia (`delilah-110`, `delilah-134`) se muestran junto al texto original sin modificarlo.
- Marcador de referencia: etiqueta accesible genérica «Map marker» (de MapLibre); sin cambio.

## Cambios

- `incident_model.mjs`: `seekWhenReady`, `acceptLiveAnalysis` (conserva `savedAnalysis`), `requestAnalysis` (errores acotados y comprobación del SHA), `inferenceFailureNotice`, `reviewNotesFor`.
- `incident.js`: usa lo anterior; estado de inferencia por fotograma (pendiente/error/éxito no se cruza entre cámaras; botón desactivado solo para el fotograma en curso); texto «Cámara seleccionada: …, hora impresa …» junto al estado del mapa; mensaje cuando Cosmos no está disponible; `aria-label` del recorrido.
- `incident_model.test.mjs`: 4 pruebas nuevas (seek tardío, tiempos en clip, fallos sin errores crudos con respuesta guardada intacta, respuesta nueva que conserva el original y no hereda la nota).

## Después

- `node --test *.test.mjs`: 10/10 (incluye `geo.test.mjs`). `python3 -m unittest test_incident_bundle`: OK.
- En navegador: caso 1 → video en 77 s; caso 2 → «El servicio de análisis respondió HTTP 502.» / «No se pudo contactar con el servicio de análisis.» + «Se conserva la respuesta anterior.»; caso 3 → el error queda en Delilah, Buck Rock muestra su propio estado con botón activo; caso 4/5 → nota sustituida por «Esta respuesta nueva no está revisada…», exportación con `savedAnalysis` (13:47:38) y respuesta nueva (14:01:28), mismo SHA; 390 y 1440 sin overflow.
- No verificado: caso 7 con servidor sin Cosmos real; touch real en dispositivo.

## Comprobación del coordinador

Se inició una instancia local separada con `run_local.py --saved-only --port 5181`. El navegador confirmó `cosmos:false`, botón de nueva inferencia desactivado, explicación visible y observación guardada disponible. Las teselas siguen requiriendo red. La instancia de prueba se detuvo tras la comprobación.
