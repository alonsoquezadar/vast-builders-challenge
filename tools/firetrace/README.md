# FireTrace

Visor de observaciones de incendios sobre relieve real, con un gateway Python sin dependencias y MapLibre GL JS 5.6.1. La demo actual se mantiene local por decisión del usuario.

## Abrir la demo local

Desde la raíz del repositorio:

```sh
python3 tools/firetrace/run_local.py
```

Abre **http://localhost:5173/**. El script carga las observaciones guardadas y abre una conexión privada por SSH al gateway del laboratorio para solicitar inferencias a Cosmos. Las credenciales permanecen en el laboratorio. No cambia Ingress ni el botón App.

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
node --test tools/firetrace/geo.test.mjs
python3 -B -m unittest discover -s tools/firetrace -p 'test_*.py'
python3 -m py_compile tools/firetrace/main.py tools/firetrace/deploy.py
node --check tools/firetrace/app.js
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
