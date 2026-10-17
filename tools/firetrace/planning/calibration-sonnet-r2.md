# FireTrace: calibración Garnet · investigación R2 (Sonnet)

**Fecha:** 2026-10-17. **Base:** `f9ff0ac`. **Escribe solo:** este archivo y `calibration/garnet-references-sonnet-r2.json`. No toca `calibration.py`, `main.py` ni la UI.
**Veredicto: ISSUES.** Hay posiciones de cámara refinadas con justificación, pero **0 pares píxel-mundo** (se necesitan 6 de ajuste + 2 de comprobación por cámara). No hay calibración ni validación geográfica.

## 1. Posiciones refinadas (candidatas)

| Cámara | Manifiesto (redondeado) | Candidata | Desplazamiento | Elevación |
|---|---|---|---|---|
| Delilah Lookout 2 | -119.12, 36.80, 1570 | **-119.1175, 36.80417**, 1570 | 514 m, rumbo 25,6° | impresa 5151 ft = 1570 m. DEM 3DEP (1 m) en el punto: 1572,1 m (cima local). En el punto redondeado el DEM da 1511,6 m |
| Buck Rock 1 | -118.86, 36.74, 2578 | **-118.86067, 36.73727**, 2578 | 309 m, rumbo 191,1° | impresa 8468 ft = 2581,0 m. Cima DEM cerca de (-118.8608, 36.7370): 2582,9 m. En el punto redondeado el DEM da 2440,4 m |

**Por qué se justifican**
- Delilah: la página del USFS (36.80416667, -119.1175, es decir 36°48'15" N 119°07'03" O, resolución de segundo de arco ≈ 30 m) y la base de datos de atalayas `firelookout.org` (NHLR US 379: 36.80418, -119.11758) coinciden. Además el punto es la cima local del DEM y su cota casi iguala la impresa.
- Buck Rock: `firelookout.org` (NHLR US 284: 36.73727, -118.86067) coincide a ~25 m con la cima que encontré en un barrido independiente del DEM de 1 m. Su cota (2582,9 m) casi iguala la impresa (2581,0 m).
- El punto redondeado deja la cámara 58 m (Delilah) y 138 m (Buck Rock) por encima del terreno, lo que sesga cualquier proyección sobre el DEM.

**Lo que NO está demostrado**
- Que la cámara esté montada **en** la atalaya (el nombre y la cota lo sugieren; ninguna fuente lo afirma). Es una suposición explícita en el JSON.
- Buck Rock: no leí una fuente oficial (la página del USFS dio 403; NRHP no se localizó). La coordenada es secundaria. El texto de prensa solo da 8.502 ft (2591 m), unos 10 m por encima de la cota de la cámara.
- Delilah: la cifra de 5176 ft de Living New Deal (con coordenadas 36.802862, -119.11872) discrepa; en ese punto el DEM da 1530 m, 40 m por debajo de la impresa. La rechacé como posición de cámara.
- Datum: USGS declara NAD83/NAVD88; no apliqué conversión a WGS84/elipsoide. Las bases de atalayas no declaran datum ni exactitud. Altura de la torre sobre el suelo: desconocida.
- Con la posición refinada, el rumbo a la ubicación CAL FIRE pasa de 48,5° a 49,6° (Delilah, 10,5 km) y de 313,0° a 313,7° (Buck Rock, 20,6 km). Es solo geometría de referencia, no un fuego localizado.

## 2. Referencias del paisaje: no se encontró ninguna utilizable

Método: inspección de `delilah-86`, `buckrock-222` y `buckrock-267`, más perfil de horizonte desde el DEM (OpenTopoData `ned10m`, azimutes 0–110° para Delilah y 255–345° para Buck Rock, rayos de 1–40 km cada 500 m, refracción k=0,13).

- **Delilah:** el horizonte del DEM se mantiene entre +1,5° y +3,3° de elevación en todo el sector, sin una forma única que permita anclar guiñada y cabeceo a ojo. En el fotograma, la columna de humo tapa la ladera y no hay estructuras reconocibles.
- **Buck Rock:** hay un pico oscuro puntiagudo abajo a la izquierda (≈ [150, 293]) visible en los tres fotogramas. Lo asocié a un máximo local del horizonte a azimut ≈ 273–275°, 7,5 km, cota 2340 m, (-118.9447, 36.7408). La comprobación de escala falla: con el FOV del catálogo (65,1° a zoom 1) la diferencia de altura con el macizo derecho sale 1,5–3°, y la imagen muestra ≈ 4,9° (48 px). Z 1,4 impreso puede cambiar el FOV y no está verificado. Queda como **hipótesis rechazada, no apta para ajuste** (en `hypothesesNotForFitting`).
- No uso el punto CAL FIRE del incendio para ajustar ni validar. El incendio del 27/08 no es control de verdad terreno.

## 3. Overlay X/Y/Z y metadatos del catálogo

- `all_cameras-v3.json` (instantánea en vivo): ambas cámaras son Axis Q6075-E con `fov` 65,1 (horizontal a zoom 1, sin verificar). `az_current`: Delilah 308,29°, Buck Rock 301,58°; `tilt_current`: 0,0 y -0,69. **Son la pose actual, no la del Garnet**, y su referencia (norte verdadero/magnético) no está documentada.
- Impreso en Garnet: Delilah X +25,27, Y +7,33, Z 1,0; Buck Rock X -26,13, Y +7,89, Z 1,4.
- **X no es azimut verdadero** sin sustento: usando el rumbo al origen como sustituto salen desfases incompatibles entre cámaras (y el fuego del 27/08 ya no está en el origen). **Y no se comporta como cabeceo geométrico** (con +7,3° hacia arriba y un horizonte de +3° la cresta quedaría hacia y≈217 o más abajo; la cresta del fotograma está sobre y≈195–250). Z podría ser zoom; sin verificar.
- Prueba propuesta, no hecha por no descargar imágenes en vivo: leer X/Y/Z impresos de un fotograma actual de cada cámara y compararlo con `az_current`/`tilt_current` del mismo instante. Con dos poses por cámara se obtendrían desfase y escala.

## 4. Qué falta para una calibración real

1. Por cámara: ≥ 6 referencias de ajuste y 2 de comprobación **independientes** (hoy 0 de 8).
2. Referencias fiables en el DEM: cumbres con perfil distintivo, torres o infraestructura medible. Las laderas lisas bajo humo no sirven. Mejor un fotograma de día sin humo de otra fecha, de la misma torre y misma pose (posible solo con X/Y/Z impresos idénticos).
3. Relación pose impresa ↔ azimut/cabeceo/zoom (prueba de la sección 3).
4. Modelo de `calibration.py`: asume posición fija; con 300–500 m de incertidumbre en torres a 10–24 km, el error angular por posición es de ≈ 0,7–3° (300 m a 24 km; 500 m a 10 km), unos 7–29 px a 9,8 px/° (zoom 1, FOV del catálogo sin verificar).
5. Zona horaria y sincronía de reloj, sin verificar.

## 5. Fuentes y límite de lectura

- ALERTCalifornia, catálogo: https://cameras.alertcalifornia.org/public-camera-data/all_cameras-v3.json
- USFS Delilah Lookout: https://www.fs.usda.gov/r05/sequoia/recreation/delilah-lookout (coordenadas leídas por resumen de búsqueda; acceso directo 403)
- Fire Lookout database (NHLR/FFLOS): https://firelookout.org/lookouts/us/ca/
- USGS 3DEP EPQS (punto 1 m): https://epqs.nationalmap.gov/v1/json
- OpenTopoData ned10m: https://api.opentopodata.org/v1/ned10m
- Living New Deal (Delilah, rechazada para posición): https://livingnewdeal.org/projects/delilah-forest-ccc-fire-lookout-dunlap-ca/
- Buck Rock, 8.502 ft y estado: https://abc30.com/post/buck-rock-fire-lookout-sequoia-national-forest-now/15089633/
- Scripts y datos temporales en `/tmp/fts-r2/` (fuera del repo). No se descargaron videos ni imágenes externas; no se llamó a `/api/analyze`.
