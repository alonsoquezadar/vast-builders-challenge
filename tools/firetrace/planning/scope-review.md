# FireTrace: revisión de alcance y prioridades (demo en vivo hoy)

Base de la revisión: archivos actuales sin commit en `tools/firetrace` (538 líneas: `main.py` 202, `app.js` 119, `geo.mjs` 38, `index.html` 79). HEAD `a770d20` no los contiene.
Yo solo ejecuté `node --test geo.test.mjs` (3/3 pasan), `py_compile` y `node --check` (ok). Las llamadas a FIRMS, ALERTCalifornia, WFIGS, Cosmos y VAST **no las reproduje aquí**. Esas filas figuran como "reportado" y hay que reverificarlas con el comando de la última sección.

## 1. Comprobado vs. falta

| Tema | Estado | Evidencia |
|---|---|---|
| Gateway stdlib, `/health`, `/api/{status,firms,cameras,perimeters,analyze,search}` | Código leído | `main.py:143-185` |
| Pruebas geo (rumbo, destino, cursor sin futuro, validación GeoJSON) | **Verificado hoy** | `node --test`: 3 pass, 0 fail |
| DEM Terrarium, Esri, MapLibre 5.6.1 | Reportado | Reverificar visualmente |
| FIRMS 7d, filtro California | Código leído; datos vivos reportados | `main.py:50-64` |
| WFIGS con filtro temporal | Reportado | `app.js:62-63,91` |
| 1314 cámaras públicas con `az_current`, `tilt_current`, `fov` | Reportado; el código las transporta | `main.py:66-78` |
| MP4 local → fotograma → Cosmos → texto "requiere revisión" | Código leído; llamada real reportada | `main.py:93-122` |
| Búsqueda VAST | Funciona técnicamente (login + `/api/v1/search`) | `main.py:81-90` |
| Import/export GeoJSON con procedencia | Código + prueba de validación | `geo.test.mjs` |
| Deployment/Service en team-23, sin Ingress | Reportado | `/app` sigue siendo `pulse-corridor` (no tocar) |

**Falta**, y nada de esto existe en el código:
- calibración de pose (`fov`, `az`, `tilt` publicados sin validar);
- segmentación de fuego o humo;
- triangulación entre cámaras;
- proyección del píxel al DEM (ray-casting);
- asociación formal fotograma → cámara → hora (el fotograma queda "ubicación sin resolver");
- predicción de propagación;
- verdad terreno para evaluar.

**Hallazgo clave sobre VAST:** el índice del equipo contiene tráfico, almacén, calles y conducción (ver `ARCHITECTURE_REFERENCE.md`, corpus). No contiene fuego. Una búsqueda "humo" devolverá coincidencias irrelevantes o vacías. Además, el reglamento prohíbe ingerir video de internet. Por eso el README de FireTrace dice que no ingiere ALERTCalifornia. En la demo, VAST es "infraestructura conectada", no evidencia de incendios.

## 2. ¿Podemos afirmar video → ubicación?

**No.** Hoy lo defendible es: "un fotograma se describe con Cosmos y, por separado, se muestra la cámara con su rumbo publicado". La línea de 12 km (`app.js:97`) es solo un rumbo, sin distancia.
Una vista con una columna de humo no fija la distancia al foco. El propio README lo dice.

Evidencia que falta para afirmar una ubicación, de menor a mayor esfuerzo:
1. Una cámara y una secuencia **autorizada** con hora y pose conocidas. Hoy hay que obtenerla del visor (captura manual); no hay ingesta autorizada.
2. Un incendio con **posición de referencia** (perímetro WFIGS o punto FIRMS cercano en el mismo intervalo).
3. Validación de pose: ¿el horizonte o un hito conocido coincide al proyectar el DEM con `az/tilt/fov`?
4. Error angular medido en ≥3 casos. Con una sola cámara solo hay un rayo; con dos, una intersección.
5. Documentar el desacuerdo cuando falle.

**Afirmación honesta permitida:** "rayo desde cámara pública hacia el sector donde Cosmos describe humo; distancia desconocida; coincidencia a verificar contra FIRMS/WFIGS". Sin eso no se llama "ubicación".

## 3. MVP P0 para hoy (criterios verificables)

Meta: un recorrido de 3 min con datos reales y límites explícitos. No es un detector de incendios.

| # | Entregable | Criterio de aceptación |
|---|---|---|
| P0-1 | Visor estable en pantalla de demo (`port-forward` o pod) | `curl /health` = 200 y mapa con relieve tras recarga fría en ≤10 s. Hay un túnel de respaldo funcionando. |
| P0-2 | FIRMS + cursor temporal | Mover el cursor cambia el conteo y el FRP de la vista. El export no incluye puntos posteriores al cursor. |
| P0-3 | Cámara elegida → rayo + enlace al visor | Un clic en una cámara cercana a un punto FIRMS recibe línea de rumbo y enlace a `cameras.alertcalifornia.org/?id=…`. |
| P0-4 | Un fotograma real → Cosmos | Un MP4/PNG de prueba, de fuente autorizada o capturada del visor, devuelve texto en español en <60 s, con la leyenda "requiere revisión · ubicación sin resolver". |
| P0-5 | Pantalla de límites | Visible que no hay triangulación, predicción ni evacuación. |
| P0-6 | Ensayo | Las tres rutas reales (P0-2/3/4) se ejecutan una vez completas, con evidencia guardada (captura o log). |

**Condicionales, solo si hay tiempo:** (a) un caso de estudio con cámara cercana a un perímetro WFIGS conocido, donde la línea de rumbo se compara visualmente con el perímetro (sin llamarlo validación); (b) una búsqueda VAST con un prompt de ejemplo del corpus real (ej. "dense traffic") para mostrar el pipeline, sin presentarla como búsqueda de fuego.

## 4. Cortar explícitamente

- Segmentación de fuego/humo propia, triangulación, calibración óptica, predicción, evacuación y temperatura desde RGB.
- Ingesta de video ALERTCalifornia a VAST (prohibida por regla de "no internet").
- Reemplazar `pulse-corridor` en `/app` (orden del usuario; **no cambiar**).
- Refactor general, persistencia de importaciones, cuentas, alertas.
- Réplicas de `world-wildfire-locator` o `fire-progression-NRTDV`: solo referencia.
- Afirmar que el video de Dilum Sanjaya es footage validado.

## 5. Cronograma relativo (estimaciones condicionadas, no promesas)

**Con 2 h:**
- 0:00–0:20 Reverificar los 5 puntos "reportados" (comandos de la sección 8). Elegir cámara y fotograma.
- 0:20–0:50 Corregir lo que falle del P0; preparar el túnel de respaldo.
- 0:50–1:20 Preparar el caso demo (cámara + punto FIRMS/WFIGS cercano) y capturar la evidencia.
- 1:20–1:45 Ensayo completo ×2 con el guion; congelar el binario/archivos.
- 1:45–2:00 Colchón. *Si algún externo cae, activar el plan B.*

**Con 4 h:** lo anterior en el mismo orden, más:
- +1 h: un caso de estudio donde se superpone el rayo de la cámara sobre un perímetro WFIGS y se anota el desfase angular a ojo. Esto es una comparación, no calibración.
- +45 min: pulir el texto del panel de límites y el export (incluir cámara/hora asociadas al fotograma en un GeoJSON de observación).
- +45 min: segundo ensayo, con otro compañero cronometrando.
- Todo lo que supere esto (ray-casting al DEM, segunda cámara) **no entra hoy**; moverlo a "siguiente paso" en la presentación.

## 6. Guion de 3 minutos

1. **0:00–0:20 Problema.** Las cámaras y los satélites ven el fuego, pero ver no es ubicar. Aquí mostramos qué datos reales existen y dónde se detiene la evidencia.
2. **0:20–1:00 Mapa.** Relieve real, FIRMS últimos 7 días; el cursor muestra las 24 h previas; perímetros WFIGS con su fecha original.
3. **1:00–1:40 Cámara.** Se elige una de las 1314 cámaras públicas; línea de rumbo; enlace al visor. "Es rumbo, no distancia."
4. **1:40–2:20 Video → Cosmos.** Un clip local; se captura el fotograma; Cosmos describe en español, con estado "requiere revisión".
5. **2:20–2:45 VAST + export.** Conectamos el índice del equipo; exportamos las observaciones con procedencia y fecha.
6. **2:45–3:00 Límites y siguiente paso.** No hay triangulación, predicción ni evacuación. Falta calibrar la pose contra un horizonte conocido y medir el error en ≥3 casos.

## 7. Mayor riesgo y plan B

**Riesgo principal:** que la demo parezca prometer "video → ubicación" sin evidencia, o que una dependencia externa (FIRMS, ALERTCalifornia, WFIGS, Cosmos, VAST) falle en vivo. Con una audiencia técnica, la primera es peor.
Riesgos secundarios: la rotación de pods deja caído el `port-forward`; no hay un clip de incendio autorizado a mano; VAST no devuelve nada relevante a "humo".

**Plan B honesto:**
- Grabar de antemano pantalla + respuestas reales de cada llamada (con fecha y hora) y proyectarlas si algo falla, **diciéndolo**.
- Guardar un JSON de FIRMS y de cámaras en el momento del ensayo para no presentar datos inventados.
- Mantener un fotograma estático y su respuesta Cosmos ya obtenida, etiquetada como "ejecución previa".
- Si Cosmos falla: mostrar solo el mapa + cámara + límites. Valida menos, pero es honesto.

## 8. Esfuerzo de producción por frente (con incertidumbre)

Sin calendario inventado: tamaño relativo y qué lo mueve.

| Frente | Tamaño | Incertidumbre principal |
|---|---|---|
| Endurecer demo (reverificación, respaldos, ensayo) | S | Disponibilidad de fuentes externas |
| Asociar fotograma ↔ cámara ↔ hora en el export | S–M | Hay que decidir el esquema y qué hora usar (la del clip no es la del incendio) |
| Obtener footage autorizado con pose conocida | M, bloqueo externo | Términos de ALERTCalifornia; no se sabe si hay descarga permitida |
| Proyección al DEM (ray-casting) | M | Precisión de `az/tilt/fov` publicada; sin validar |
| Validación con verdad terreno (≥3 casos) | M–L | Conseguir referencias y definir la métrica |
| Segmentación de humo/fuego | L | Requiere datos etiquetados; Cosmos no da píxeles |
| Triangulación (≥2 cámaras sincronizadas) | L | Cobertura simultánea + sincronía de relojes |
| Predicción de propagación | XL, no hoy | Meteorología, combustible y validación operativa |
| Despliegue en `/app` | Decisión del usuario | `pulse-corridor` ocupa `/app`; no tocar |

**Comandos de reverificación (sin secretos en la salida):**
```sh
node --test tools/firetrace/geo.test.mjs
python3 -m py_compile tools/firetrace/main.py tools/firetrace/deploy.py && node --check tools/firetrace/app.js
KUBECONFIG=/config/team-23-k8s.yaml kubectl -n team-23 get deploy,svc firetrace
KUBECONFIG=/config/team-23-k8s.yaml kubectl -n team-23 port-forward svc/firetrace 18731:80 &
curl -s localhost:18731/health; curl -s localhost:18731/api/status
curl -s localhost:18731/api/firms | python3 -c 'import sys,json;d=json.load(sys.stdin);print(len(d["features"]))'
curl -s localhost:18731/api/cameras | python3 -c 'import sys,json;d=json.load(sys.stdin);print(len(d["features"]))'
```
