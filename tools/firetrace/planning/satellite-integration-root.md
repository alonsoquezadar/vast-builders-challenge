# Integración local de Garnet

Integrado en `/incident.html`: imágenes y respuestas Cosmos guardadas, DEM real, 13.883 detecciones FIRMS, 6.073 celdas reconstruidas y perímetro final WFIGS opcional. Cursor UTC independiente de cámaras; la relación PDT exige un supuesto explícito. El perímetro final es posterior y no inicializa la simulación.

`/simulation.html` admite cargar viento histórico de Open-Meteo cerca de Garnet. El servidor selecciona la hora y sustituye el viento enviado por el cliente. Semilla, combustible y tasa base siguen siendo hipotéticos. La humedad relativa se muestra como contexto; no representa humedad del combustible. No existe validación física ni comparación independiente de propagación.

La consulta histórica no fijó un modelo concreto: se sirve como Best Match, sin atribuirla exclusivamente a ERA5. Los datos originales y sus huellas permanecen intactos.

Verificado con el servidor real en localhost:5173: carga de focos y reconstrucción sobre relieve 1×, activación del supuesto PDT, conteos temporales, meteorología y simulación con viento histórico. A 390 px, ancho del documento 390 px y panel de 354 px. Las pruebas de servidor cubren viento no falsificable, fechas fuera de rango y rechazo de semillas a más de 50 km del punto meteorológico.

No se estableció georreferenciación del humo. La investigación de calibración produjo cero referencias imagen-mundo aptas; las posiciones refinadas son candidatas. El escenario sigue iniciándose con una semilla hipotética y no con un frente contemporáneo observado.

## Revisión de entrega y datos originales

Se conserva `raw/` (2.119.949 bytes) para reproducir las capas sin una nueva descarga ni clave NASA. Las huellas de las 18 entradas, siete salidas y dos scripts se comprobaron; los URL guardados usan variables de sustitución. No se modifica el paquete original.

La UI muestra explícitamente la sobrestimación ×1,53 del 25/08 y ×1,38 del 31/08, con la salvedad de que esta última comparación usa prensa local. También distingue WFIGS 07:10 UTC, FIRMS 09:26 UTC y CAL FIRE 14:13 con zona no verificada aquí. La detección del paquete es posterior a WFIGS; ninguna de estas horas prueba la ignición.
