# Módulo de UI satelital/meteorológico (Sonnet r4)

Base al empezar: `5ccdd79`. HEAD al terminar: `03ca88f` (otros chats avanzaron la rama; no hice commits).
Archivos propios: `satellite-view.mjs`, `satellite-view.test.mjs`, `satellite-view.css`, este documento.

## Integración (root)

```html
<link rel="stylesheet" href="./satellite-view.css">   <!-- opcional: el módulo lo añade si falta -->
<div id="satellite-panel"></div>
```
```js
import {mountSatellite} from './satellite-view.mjs';
// después de initMap():
const satellite = await mountSatellite(map, document.getElementById('satellite-panel'));
// desde render():
satellite?.onMomentChanged(pair.frames);
```

- `mountSatellite` es `async` solo por contrato: construye el panel y resuelve de inmediato, sin esperar datos ni el mapa.
  `createSatellite(map, container, {fetchFn, maplibre})` es la misma función síncrona (devuelve el controller sin promesa).
- Si `render()` corre antes de que resuelva el await, el controller aún es `undefined`: usar `satellite?.onMomentChanged(...)`
  y llamarlo una vez más tras el await con los últimos `pair.frames`.
- Controller: `onMomentChanged(frames)`, `ready` (promesa: datos cargados y mapa listo, nunca rechaza), `getCursor()`,
  `setCursor(sec)`, `destroy()`.
- Requiere `maplibregl` global para los popups (si falta, las capas funcionan sin popups).
- Datos: `GET ./api/satellite?layer=hotspots|arrival|perimeter|weather|summary` (JSON original; `_provenance` opcional,
  se muestra `dataClass` y los 12 primeros caracteres del campo con hash si existen).
  Carga: `summary`, `weather` y `hotspots` al montar; `arrival` y `perimeter` al activar su casilla (arrival ≈ 1,9 MB).

## Comportamiento

- Casillas: focos OBSERVADOS (ON), llegada RECONSTRUIDA (OFF), perímetro FINAL con fecha (OFF). Estado por fuente
  (cargando → deshabilitada; error → mensaje propio y casilla desmarcada; marcarla reintenta).
- Cursor UTC 24 ago 00:00 – 12 sep 23:59, paso 1 min, play/pausa (+1 h cada 150 ms). Cursor inicial arbitrario: 27 ago 00:00 UTC.
- Focos: ventana `[cursor − 12 h, cursor]`. Celdas reconstruidas: `t <= cursor`. Nada posterior al cursor.
- Meteorología: hora del reanálisis más cercana a ≤ 1 h (empate: la anterior); fuera de eso, "sin hora"; nunca la última fila.
  Viento DESDE grados + m/s, HR, temperatura, hora y punto; rotulado como MODELO, no estación.
- Supuesto PDT (OFF): con ON usa la hora impresa del **primer** fotograma + 7 h, rotulado SUPUESTO; no afirma sincronía.
  Se guardan los últimos `frames`; al activar se aplica el cursor. Cambiar de momento con la opción OFF no mueve el cursor.
  Mover el slider a mano quita el rótulo SUPUESTO hasta el siguiente cambio de momento.
- Texto fijo: reconstrucción recortada por el perímetro FINAL (publicado 2025-12-19, fecha tomada de los datos cuando cargan),
  todas RECONSTRUIDAS, sin inferir perímetro, área ni velocidad. Popups con `textContent`.
- IDs de mapa con prefijo `firetrace-sat-` (no chocan con la capa raster `satellite` de `incident.js`). Clases CSS `satellite-*`.

## Verificación

- `node --test tools/firetrace/satellite-view.test.mjs`: 18/18 (lee los GeoJSON reales solo para invariantes; no imprime datos).
  Cubre rango, conteos vs `summary.json`, ventana sin futuro, filtros de llegada, hora meteorológica, supuesto PDT, errores por
  fuente y reintento, orden/filtros de capas con un mapa simulado, `whenMapReady` y popups.
- Prueba de humo en navegador (T3, arnés temporal en `/tmp` en otro puerto, ya eliminado; endpoint simulado con los archivos
  reales + `_provenance` inventado): panel, 3 capas, contadores, supuesto PDT (16:16:57 → 23:17 UTC), error por fuente con
  reintento y popup de foco funcionaron. **No se probó contra el servidor ni `incident.html` reales** ni con las rutas root reales
  ni con el formato real de `_provenance`.

## Límites

- Sin `incident.html` real: el CSS se probó solo en el arnés (mapa de fondo liso, sin teselas ni terreno 3D).
- Con terreno 3D los círculos/rellenos no se verificaron.
- La zona horaria de las cámaras sigue sin confirmar; el supuesto es una opción del usuario, no una conversión.
