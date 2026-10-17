# Revisión de integración

El Sonnet B entregó el motor sin observaciones, con 25 pruebas. Root reprodujo las pruebas y encontró una dependencia indebida: la banda angular que consumiría la asimilación usaba el máximo error de las pasadas reservadas. La regresión cambió solo la observación reservada y produjo bandas de 18,58° y 32,58°, aunque el ajuste era idéntico.

Se eliminó esa influencia: la banda usa solo sector de ajuste, sensibilidad de posición y prior de FOV. Los errores reservados permanecen como diagnósticos; `validated` permanece false y `holdoutEvaluated` solo indica que existe una evaluación. La API de rumbo rechaza relojes/horas inciertos. El cargador exige imágenes con SHA coincidente en la carpeta de visión; los tests sintéticos que omiten imágenes lo declaran mediante una opción interna que el CLI no expone.

También se corrigió el conteo de compatibilidad en huecos entre grupos: estar dentro de la envolvente exterior no equivale a estar dentro de un grupo de detecciones.

28 pruebas pasan. No hay calibración medida todavía: el CLI se volvió a ejecutar y conserva `pending-observations`, con cero parámetros ajustados. La vista solo dibuja visuales cuando la calibración está ligada a la versión actual de las observaciones y las imágenes conservan su integridad.
