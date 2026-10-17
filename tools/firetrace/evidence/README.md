# Evidencia de la prueba visual

Las imágenes se descargaron sin edición para una prueba local de inferencia autorizada por el usuario. No se ingirieron en VAST. Cada respuesta conserva el SHA-256 de los bytes enviados, el modelo y la hora de análisis. Son dos ejemplos de comportamiento; no constituyen una evaluación de precisión de detección.

- `gann-official-thumbnail.jpg`: miniatura de **Gann Fire Compilation**, enlazada desde la página oficial de ALERTCalifornia. Tiene llamas y humo visibles. El texto de la imagen sitúa la compilación en Calaveras County del 3 al 5 de agosto de 2026. La fecha y cámara exactas de este fotograma no están verificadas. Cosmos describió llamas y una columna de humo; no devolvió una posición geográfica.
- `grizzly-camera.jpg`: captura de **Axis-GrizzlyPeakShasta1**, nocturna y con visibilidad limitada. Se guardaron metadatos públicos antes y después de obtenerla. La pose numérica coincidía entre lecturas, pero no se ha calibrado contra el relieve. Cosmos describió la oscuridad y no señaló fuego visible. No se etiqueta como prueba de ausencia de incendio.
- Los archivos `*-source.json` contienen procedencia y metadatos. Los archivos `*-analysis.json` contienen las respuestas reales. El servidor solo presenta una respuesta guardada si su huella coincide con la imagen actual.

Crédito de imágenes: **ALERTCalifornia | UC San Diego**. La imagen de Grizzly conserva además el crédito a PG&E que aparece en el original.

Fuentes:

- https://alertcalifornia.org/images-and-video/
- https://alertcalifornia.org/terms/
- https://www.youtube.com/watch?v=N_C9qivAWfA
- https://cameras.alertcalifornia.org/?id=Axis-GrizzlyPeakShasta1

Las fechas de estas imágenes y de los puntos satelitales del mapa no coinciden. No se presentan como una reconstrucción del mismo evento.
