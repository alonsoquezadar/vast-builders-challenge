# Vista operativa FireTrace (r6)

Página: `/firetrace.html` (MapLibre 5.6.1, sin dependencias nuevas). Archivos: `firetrace.html`, `firetrace.css`, `firetrace.js`, `firetrace_model.mjs` (lógica pura) y `firetrace_model.test.mjs`.

## Qué muestra
- Mapa 3D con terreno AWS Terrarium 1× e imagen Esri, pitch 60°, zoom ~11.
- Área acumulada = celdas de `arrival` con `t <= cursor` (oscuro). Actividad reciente RECONSTRUIDA = últimas 6/12/24 h (rojo/naranja), con contorno resplandeciente calculado como aristas entre celdas llegadas y no llegadas. No es un frente físico conocido.
- FIRMS: solo la última pasada con `t <= cursor`, filtrada por `t` y `source` exactos.
- Capas: reconstrucción, FIRMS, perímetro FINAL (apagado), pronóstico, conos de cámara (hipótesis). La leyenda rotula siempre observado / reconstruido / modelado.
- Línea de tiempo 24 ago – 12 sep: slider, play/pausa, velocidad, hitos (WFIGS 07:10 UTC, CAL FIRE 14:13 sin zona confirmada, FRP 27 ago 23:00 UTC, pirocúmulo ~16 PDT según supuesto), y gráficos SVG de área (con barras diarias y razones 1,53× / 1,38× frente a lo reportado), FRP por pasada y viento horario con cursor alineado.
- Meteo: última hora del modelo ≤ cursor; sin extrapolar fuera de rango. Dirección DESDE, m/s, temperatura, HR del aire (no del combustible).
- Cámaras: fotograma más cercano a cada cámara, hora impresa leída como PDT (supuesto), diferencia con el cursor, descripción guardada de Cosmos y notas de revisión. No llama a `/api/analyze`.
- Pronóstico: `POST /api/forecast-reconstruction` con `{timeUtc, horizonHours}`. Solo se pide al pulsar el botón. Mover el cursor o cambiar el horizonte oculta el pronóstico y aborta la petición; una respuesta obsoleta se descarta. La tarjeta muestra IoU total y de crecimiento (— si es null), sobre/subpredicción en ha, aviso de límite de dominio, "NO VALIDADO" y el hecho de que compara con la reconstrucción.

## Contrato de pronóstico validado en el cliente
Roles: `initial-extent`, `modeled-extent`, `reference-extent`, `overlap`, `overprediction`, `underprediction`. `dataClass`: `modeled` o `reconstructed`; los tres roles de comparación también aceptan `modeled-comparison`. Se rechaza cualquier otra clase, un `mode` distinto de `retrospective-forecast` y respuestas cuyo `timeUtc`/`horizonHours` no coincidan con lo pedido.

## Límites conocidos
- La hora de cámara en UTC depende del supuesto PDT.
- Los conos usan el azimut impreso (supuesto) y FOV 65,1° a zoom 1 escalado por focal; son hipótesis.
- El encuadre del pronóstico usa `MapLibre.fitBounds` sobre todas las geometrías. Root eliminó la aproximación manual, que usaba la escala de un mundo de 256 píxeles cuando el visor usa 512 y podía cortar la proyección. Cambiar entre 2D y 3D conserva el centro; Encuadrar considera el pronóstico vigente.
- La velocidad de reproducción se limita a 120 ms por fotograma; en equipos lentos avanza más despacio que lo indicado.

## Pruebas
`node --test tools/firetrace/firetrace_model.test.mjs` (22 casos: cronología sin futuro, FRP de la pasada exacta, área frente a acres diarios, contorno, meteo, cámaras, conos, contrato e invalidación de pronóstico, respuestas tardías).
