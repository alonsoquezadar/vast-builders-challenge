# Entrega local de FireTrace

La demo principal es Garnet Fire en `/incident.html`: dos cámaras, tres momentos, seis imágenes y seis respuestas reales de Cosmos. Plaskett sigue disponible en `/alignment.html` para marcar humo y recoger correspondencias imagen–terreno.

Orden de trabajo, siguiendo pstack:sharpen y unidades verificables:

1. Preparar fotogramas con cámara, hora impresa y SHA-256. Comprobarlos contra el original descargado por el otro hilo.
2. Analizar las seis imágenes con Cosmos y conservar entrada y respuesta. Retener el texto original y señalar errores conocidos de procedencia.
3. Conectar la selección de momento y cámara con imagen, secuencia, observación y mapa. Mostrar la diferencia de horas entre vistas.
4. Probar reproducción, cambio de cámara, mapa, exportación y respaldo sin GPU. Guardar los cambios en la rama exclusiva de FireTrace.

Para un pitch de tres minutos: presentar el problema; comparar las dos vistas de tarde; pasar al anochecer; abrir una observación de Cosmos y su video; mostrar las cámaras sobre el relieve; exportar la evidencia. Explicar que la georreferenciación del fuego sigue pendiente.

El marcador oficial sirve como contexto del incidente. No se usa para calibrar y después afirmar que valida la misma calibración. La triangulación requiere referencias independientes, poses calibradas, relojes comprobados y correspondencias del mismo rasgo. El humo elevado no se proyecta directamente sobre el suelo.

Después de esta entrega: identificar referencias geográficas reales, mejorar la posición de las cámaras, ajustar sus poses y medir el error con puntos independientes. La simulación de propagación es una etapa posterior con relieve, viento, combustible, humedad y estado inicial; no forma parte de la demo actual.
