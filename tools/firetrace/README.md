# FireTrace

Demo de reconstrucción y modelación de incendios sobre relieve real, con un gateway Python y MapLibre GL JS 5.6.1. Tiene una versión local y una exportación pública en GitHub Pages. La entrada principal es `/firetrace.html`; `/` redirige a esa vista.

Todas las pantallas usan inglés británico (`en-GB`), con reloj de 24 horas, punto decimal y coma de millares. Los textos del servidor se traducen para su presentación mediante `localisation.py` y `locales/en-GB.json`. Las traducciones de respuestas guardadas de Cosmos llevan un aviso y la huella del texto original. Los archivos de evidencia, sus huellas y los datos numéricos permanecen intactos. Las claves de esquema y los identificadores internos conservan su formato original.

## Tour guiado y GitHub Pages

Pulsa **Take a tour** para recorrer las 17 explicaciones de la vista principal. Usa **Next**, **Back**, las flechas del teclado o **Escape** para salir. El tour pausa la reproducción y resalta el control o panel correspondiente.

Pulsa **Real footage** para abrir el vídeo de una cámara en la esquina derecha del mapa. **Start synced sequence** reproduce el tramo con horas conocidas y mueve el timeline con el vídeo. Arrastrar el timeline busca el momento correspondiente del vídeo y lo pausa. El reproductor permite cambiar entre Delilah y Buck Rock. **Watch synced clip**, en la ficha de una cámara, abre el mismo reproductor en la hora del fotograma.

La sincronización interpola entre las tres horas impresas revisadas de cada cámara, con PDT asumido. Fuera de ese tramo muestra un aviso y no extrapola. La comparación no convierte el vídeo en una reconstrucción automática ni valida la sincronía de los relojes.

**Play video + model**, en el panel **Video-linked growth**, reproduce la cámara y activa una capa magenta que crece con la misma hora del vídeo. La capa naranja conserva la reconstrucción satelital. La nueva capa calcula la propagación desde las 23:00 UTC del 27 de agosto hasta las 07:00 UTC del día siguiente, con relieve real y viento histórico horario. Usa 178 celdas recientes del borde como puntos de propagación y mantiene el combustible uniforme como supuesto.

El escenario es experimental. No está ajustado al vídeo y sobreestima la reconstrucción posterior. **Sources and comparison** muestra el resultado a las 05:19 UTC, hora exacta de la siguiente pasada satelital. La referencia no añade celdas nuevas en esa pasada, de modo que la comparación no permite validar el crecimiento real. Las limitaciones de la reconstrucción inicial, recortada con el perímetro final, siguen vigentes.

Para regenerar el escenario y comprobarlo:

```sh
python3 tools/firetrace/video_scenario.py
python3 -m unittest discover -s tools/firetrace -p test_video_scenario.py
node --test tools/firetrace/video-scenario.test.mjs
```

El archivo `evidence/garnet/video-scenario.json` guarda las horas de llegada por celda y las huellas de las entradas. La investigación de GOES confirmó archivos de NOAA en las horas consultadas, pero no extrajo detecciones sobre Garnet. GOES no participa en este escenario.

La web pública está en https://alonsoquezadar.github.io/vast-builders-challenge/. GitHub Pages sirve el contenido de la rama `gh-pages`. El código de esta entrega está en `firetrace/guided-tour-pages`.

Para regenerar la web, instala las dependencias de `requirements-forecast.txt` en tu entorno Python y ejecuta desde la raíz del repositorio:

```sh
python3 tools/firetrace/build_pages.py --output /tmp/firetrace-pages
python3 -m http.server 5184 --bind 127.0.0.1 --directory /tmp/firetrace-pages
```

El directorio de salida debe estar vacío. En otra terminal, comprueba la exportación:

```sh
node tools/firetrace/verify_pages.mjs http://localhost:5184/
```

Si solo cambian la interfaz o el escenario del vídeo, puedes actualizar una exportación existente con `python3 tools/firetrace/build_pages.py --output /tmp/firetrace-pages --refresh-assets`. Esta opción verifica y conserva las proyecciones horarias ya generadas. No la uses si cambian sus entradas o el comportamiento del motor de pronóstico.

El servidor estático de Python permite comprobar la exportación, pero no admite solicitudes HTTP Range para buscar dentro del vídeo. Comprueba la sincronización con `run_local.py --saved-only` o con la web de GitHub Pages, que sí admiten esas solicitudes.

Publica los archivos generados en la raíz de `gh-pages`. En **Settings → Pages**, selecciona **Deploy from a branch**, **gh-pages** y **/(root)**. Cada nuevo commit en esa rama actualiza la web.

La exportación copia una lista explícita de archivos públicos, verifica las huellas de las fuentes y guarda las proyecciones de 6, 12 y 24 horas para cada hora disponible. Al solicitar una proyección en la web, el cursor se mueve a la hora guardada más cercana. La interfaz la identifica como **Saved**. El servidor local conserva los cálculos para cualquier minuto.

La web incluye los fotogramas, vídeos y análisis guardados de las dos cámaras. No consulta Cosmos ni necesita credenciales del laboratorio. El mapa y las imágenes del relieve siguen necesitando internet. `build-manifest.json` registra las huellas SHA-256 de la exportación.

## Abrir la demo local

Desde la raíz del repositorio:

```sh
python3 tools/firetrace/run_local.py
```

Abre **http://localhost:5173/**. El script carga las observaciones guardadas y abre una conexión privada por SSH al gateway del laboratorio para solicitar inferencias a Cosmos. Las credenciales permanecen en el laboratorio. No cambia Ingress ni el botón App.

La nueva vista principal es **http://localhost:5173/firetrace.html**: crecimiento reconstruido a partir de detecciones satelitales del Garnet Fire (24 agosto–12 septiembre de 2025), línea de tiempo, meteorología histórica y cámaras de referencia. La proyección a 6/12/24 horas se inicializa desde la superficie reconstruida seleccionada; es una modelación heurística y su comparación posterior usa otra reconstrucción, sin validación independiente.

Para ejecutar el pronóstico en otro entorno, instala `python3 -m pip install -r tools/firetrace/requirements-forecast.txt`. Los datos de llegada, viento y elevación están guardados y se comprueban mediante SHA-256. El cálculo no necesita GPU ni consultas externas; las imágenes satelitales y las teselas del visor sí requieren conexión.

Recorrido de la vista principal:

1. Reproduce la línea de tiempo o arrastra el cursor para ver el área acumulada, la actividad reconstruida reciente y la última pasada FIRMS.
2. Pausa en un instante, elige 6, 12 o 24 horas y pulsa **Proyectar desde este frente**. Compara la extensión modelada con la reconstrucción posterior y consulta el IoU total y el del crecimiento.
3. Abre una cámara para consultar la imagen más cercana, su diferencia temporal con el cursor y la respuesta guardada de Cosmos. Los conos representan una hipótesis de orientación.
4. Consulta **Procedencia y límites** para revisar el sesgo de superficie, las horas de descubrimiento incompatibles y los supuestos del modelo.

El modelo trata todo el borde de la superficie inicial como activo y puede reactivar bordes antiguos. En el caso evaluado sobrepredice considerablemente el crecimiento. La comparación permite medir ese fallo; no acredita capacidad de predicción operativa.

Con el servidor abierto, `node tools/firetrace/verify_operations.mjs http://localhost:5173` comprueba la entrada principal y el contrato real entre la página y el servicio: horizontes 6/12/24 h, inicialización desde la reconstrucción, métricas, ausencia de referencia posterior y solicitudes inválidas. La interacción visual se comprueba aparte en el navegador.

La asimilación de cámaras queda pausada como fase siguiente: las 11 observaciones estructuradas de Cosmos tienen la base oculta y no producen correcciones. Los artefactos y el motivo se conservan en `camera_assimilation/vision/` y `camera_assimilation/assimilation/`.

## Herramientas de investigación anteriores

La demo de dos cámaras está en **http://localhost:5173/incident.html**. Selecciona uno de tres momentos de Garnet Fire y pulsa una cámara para consultar su fotograma, respuesta real guardada de Cosmos y posición pública sobre el relieve. **Ver secuencia** abre el tramo de video de esa cámara. **Analizar este fotograma ahora** solicita una inferencia nueva. **Exportar evidencia** descarga fuentes, horas impresas, huellas y respuestas.

Las dos imágenes de cada momento tienen horas cercanas, no idénticas; la interfaz muestra la diferencia. No se ha verificado la sincronía de relojes ni la zona horaria. El marcador de CAL FIRE es una referencia del incidente, no una detección extraída del video. Las seis observaciones guardadas se muestran únicamente si corresponden a los bytes de su imagen. Las correcciones de procedencia se presentan junto al texto original del modelo.

### Explorar un escenario de propagación

Abre **http://localhost:5173/simulation.html**. Pulsa **Ejemplo Garnet · DEM guardado**, revisa los supuestos y pulsa **Ejecutar escenario**. La línea de tiempo muestra las celdas alcanzadas según el modelo ilustrativo. **Exportar GeoJSON** conserva los supuestos, la semilla y la procedencia del terreno.

El relieve guardado contiene 41 × 41 muestras de elevación Terrarium, separadas 50 m, alrededor de la referencia del incidente Garnet. No describe el estado del incendio. Para otra semilla, el servidor consulta teselas reales de elevación. Si faltan, no inventa un plano. La carga de nuevas teselas requiere Pillow: `python3 -m pip install -r tools/firetrace/requirements-terrain.txt`.

La semilla es hipotética y la elige el operador. El viento, la tasa base y el factor uniforme de combustible son supuestos. El modelo usa tiempos mínimos entre ocho vecinos, con factores heurísticos de viento y pendiente. No está ajustado ni validado contra incendios reales. Si alcanza el borde de la rejilla, la interfaz indica que termina el dominio de cálculo. Cambiar un supuesto invalida el resultado, incluso si hay una petición en curso.

Este módulo de investigación mantiene una semilla hipotética. Admite viento histórico de un punto de modelo cerca de Garnet; la humedad relativa solo se muestra como contexto. La vista principal usa otro flujo, inicializado desde la reconstrucción satelital.

Para ensayar sin conectar con Cosmos:

```sh
python3 tools/firetrace/run_local.py --saved-only
```

Las teselas del mapa y del relieve siguen necesitando red. Este modo evita consultar FIRMS, el catálogo de cámaras y el modelo, pero no convierte el mapa en un visor completamente offline.

Recorrido propuesto:

1. En **Capas**, comparar dos fechas con el timeline. El rótulo **REPRODUCCIÓN** identifica los datos guardados.
2. Abrir **Análisis** y pulsar **Cargar imagen de referencia · Gann Fire**.
3. Pulsar **Analizar con Cosmos** para una inferencia nueva, o **Ver respuesta de una ejecución anterior** para el ensayo con respaldo.
4. Comparar con **cámara nocturna · Shasta**. La falta de fuego visible en una imagen oscura no demuestra ausencia de fuego.
5. Pulsar **Guardar observación y procedencia** para exportar modelo, hora, fuente, huella de imagen y modo de presentación.

El Gann Fire es una miniatura de la publicación oficial, con llamas y humo visibles. No es el caso geográfico de Shasta ni una secuencia calibrada. Sus fechas no coinciden con las detecciones satelitales del respaldo. La interfaz conserva esa distinción y no crea un marcador geográfico a partir del texto del modelo.

El usuario confirmó que se permite analizar un fotograma con Cosmos. No se ha ingerido este material en el índice VAST.

## Estado de la primera versión

### Caso Plaskett: humo y alineación

Abre **http://localhost:5173/alignment.html** con el servidor local en ejecución. Incluye los segundos 55–75 del video oficial de Rocky Butte y tres fotogramas del 30 de agosto de 2026. Las regiones de humo están marcadas manualmente en píxeles. No representan superficie quemada ni resultados de segmentación automática.

Selecciona una referencia reconocible en el fotograma y después el mismo punto en el mapa. El mapa consulta su altura en el DEM. Añade seis referencias de ajuste y dos de comprobación, separadas por la imagen. Cada fotograma conserva sus propias referencias. **Guardar sesión** exporta las marcas, coordenadas, fuentes y ajuste actual.

El ajuste experimental requiere NumPy y SciPy, disponibles en el entorno de desarrollo. En otro entorno, instálalos con `python3 -m pip install -r tools/firetrace/requirements-calibration.txt`. El resto del gateway sigue usando la biblioteca estándar.

La posición pública de Rocky Butte está redondeada. El ajuste mantiene fija esa posición, estima orientación y campo de visión, y muestra errores de reproyección. No incorpora distorsión óptica ni refracción. El error de comprobación no certifica precisión geográfica. Las referencias reales aún no están identificadas: la alineación sigue pendiente. El humo oculta el frente en los fotogramas revisados, por lo que no se proyecta sobre el suelo. Las horas impresas se conservan sin atribuirles una zona horaria no verificada.

Procedencia y huellas de los archivos: `evidence/plaskett/source.json`. Créditos conservados: ALERTCalifornia | UC San Diego y PG&E. No se ha ingerido la secuencia en VAST.

### Visor general

- Terreno real Terrarium, escala vertical inicial 1×, imagen satelital de Esri y controles de perspectiva.
- Detecciones NASA FIRMS S-NPP VIIRS de los últimos siete días, filtradas al entorno de California. El cursor muestra las 24 horas anteriores.
- Perímetros WFIGS publicados, con su fecha original. Las geometrías posteriores al cursor quedan ocultas. No se reconstruyen perímetros históricos a partir del catálogo actual.
- Catálogo público ALERTCalifornia, cámaras cercanas, rumbo publicado y enlace al visor original. La posición y la orientación públicas requieren comprobar su precisión antes de usarse como calibración.
- Imágenes o videos del operador. El video permanece en el navegador; solo se envía a Cosmos el fotograma que se captura y analiza.
- Análisis visual real con el modelo que devuelve `/v1/models` de NVIDIA Cosmos. La respuesta se presenta como observación pendiente de revisión, sin coordenadas inferidas.
- Búsqueda en el índice VAST del equipo, importación GeoJSON y exportación de observaciones con procedencia y fechas.

No incluye segmentación validada de fuego, triangulación entre cámaras, calibración óptica, predicción de propagación ni recomendaciones de evacuación. Las detecciones térmicas no se convierten en perímetros. No se calculan temperaturas a partir de imágenes RGB.

## Ejecutar en el laboratorio

Desde esta carpeta, en la VM del equipo:

```sh
python3 deploy.py --config /config/team-23.config --vss-url http://video-backend-service:8000
```

`deploy.py` crea o actualiza únicamente el Deployment, Service, ConfigMap y Secret de `firetrace`. Las credenciales se leen del archivo del equipo y se envían a Kubernetes por stdin. No se imprimen ni se escriben en el repositorio.

El script no cambia Ingress. En el entorno revisado, `/app` pertenece a `pulse-corridor`; activar FireTrace en ese destino requiere decidir qué aplicación debe ocuparlo. No se ha sustituido.

Para revisar el servicio sin cambiar ese destino:

```sh
KUBECONFIG=/config/team-23-k8s.yaml kubectl -n team-23 port-forward svc/firetrace 18731:80
```

El túnel de revisión debe reiniciarse después de un rollout porque queda conectado al pod anterior. La entrega pública de la hackathon corresponde al Ingress `/app` y al botón **App** del workshop.

## Verificar

Desde la raíz del repositorio:

```sh
node --test tools/firetrace/geo.test.mjs tools/firetrace/incident_model.test.mjs
python3 -B -m unittest discover -s tools/firetrace -p 'test_*.py'
python3 -m py_compile tools/firetrace/main.py tools/firetrace/deploy.py
node --check tools/firetrace/app.js
node --check tools/firetrace/incident.js
```

Las pruebas comprueban distancias y rumbos geográficos, exclusión de observaciones futuras y validación de importaciones. La comprobación visual cubre el visor, las capas, los controles temporales, las cámaras y el diseño móvil. Una respuesta de Cosmos demuestra conectividad, no precisión de detección de incendios.

## Importar observaciones

Usa un GeoJSON `FeatureCollection`. Cada elemento necesita `properties.observedAt` con fecha ISO 8601 y zona horaria. `properties.source` identifica su procedencia. Se admiten `Point`, `LineString`, `Polygon` y `MultiPolygon`, con anillos cerrados.

`example-observations.geojson` es un ejemplo sintético de formato. No se carga automáticamente. Las importaciones permanecen en memoria durante la sesión; **Exportar** descarga las observaciones, no el estado completo del mapa.

## Fuentes

- [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/): puntos térmicos, no superficie quemada.
- [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/): elevación Terrarium.
- [ALERTCalifornia](https://cameras.alertcalifornia.org/): metadatos públicos y visor. No se descarga ni se ingiere su video en VAST.
- [WFIGS Interagency Perimeters](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_YearToDate/FeatureServer/0): perímetros publicados.
- [FireTrace de Dilum Sanjaya](https://x.com/DilumSanjaya/status/2108241054298415258): referencia visual.
- [World Wildfire Locator](https://github.com/nagix/world-wildfire-locator) y [fire-progression-NRTDV](https://github.com/J-mazz/fire-progression-NRTDV): referencias consultadas; no se ha copiado su implementación.

El siguiente paso es elegir una cámara y una secuencia autorizada, asociar cada fotograma a su pose y hora, y validar la proyección sobre el DEM frente a posiciones conocidas. Una columna de humo con una sola vista no determina la distancia al foco.
