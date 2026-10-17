# Plan de entrega de FireTrace

**Actualización del usuario:** la demo se mantiene local; no se necesita publicar ni tocar el botón App. El usuario confirmó que se puede analizar un fotograma con Cosmos. La búsqueda de publicación deja de ser un bloqueo. El plan de abajo conserva el contexto original, pero las tareas de publicación se sustituyen por comprobar el arranque local y el respaldo.

Plazo confirmado por el usuario: dos horas desde las 13:38 de Londres del 17 de octubre de 2026. Objetivo de entrega aproximado: **15:38 de Londres, 14:38 UTC**. El pitch empieza después. Se presupone una presentación de tres minutos porque su duración todavía no está confirmada.

## Resultado que presentaremos

Una sola zona de California, con relieve real, observaciones fechadas y una cámara identificada. El operador reproduce la evolución observada, consulta una imagen y ve qué información respalda cada capa.

La primera versión no localiza automáticamente el fuego desde el video ni predice su avance. Para hoy la dirección de una cámara es una observación angular, no una posición de incendio. El producto completo conserva como objetivo localizar y seguir incendios desde cámaras calibradas.

## Trabajo delegado y comprobaciones

Se ejecutaron tres tareas con **Claude Sonnet 5.5, esfuerzo alto**, mediante pstack/swarm y la orquestación T3. Compartieron checkout con archivos de salida distintos.

- Alcance: `scope-review.md`. Detectó la separación entre descripción visual y geolocalización, y propuso el guion mínimo.
- Reproducción: `../demo_bundle.py` y `../test_demo_bundle.py`. La raíz volvió a ejecutar las 27 pruebas con resultado correcto y capturó datos reales del gateway.
- Cámara: `camera-feasibility.md`. Consultó metadatos públicos y relieve. Las cámaras cercanas no necesariamente apuntan hacia la zona. Las cotas de redondeo y los errores angulares de ese informe son estimaciones, no precisión medida del sistema.

La raíz verificó `/health`, la configuración de integraciones y el visor en navegador. No se ha modificado `pulse-corridor` ni su Ingress.

El respaldo `../demo-data.json` contiene **89 detecciones FIRMS, 14 cámaras y ningún perímetro publicado en el recorte consultado**. Se capturó a las 12:40 UTC. Las detecciones son del 13 al 16 de octubre y los metadatos de cámara son del 17 de octubre. **No corresponde afirmar que esas cámaras observaron esos focos en aquellas fechas.** El respaldo de datos está capturado y validado; su integración como modo de reproducción visible sigue pendiente.

## Las dos horas

Los tiempos son presupuestos de trabajo, no garantías. Cada bloque termina con una comprobación.

| Minutos desde el inicio | Responsable | Entregable | Comprobación y corte |
|---|---|---|---|
| 0–15 | Integración + usuario/organizador para permisos | Caso único, cámara e imagen autorizada. Resolver destino de publicación sin sustituir `/app`. | Si no hay imagen autorizada y correspondencia temporal, se corta la afirmación de fusión de fuentes. No gastar el resto del plazo buscando footage. |
| 15–40 | Integración, con herramienta de Sonnet | Modo de reproducción con datos reales guardados, fecha visible y fuentes ausentes explícitas. | Recargar y reproducir el mismo caso sin llamar a FIRMS ni al catálogo de cámaras. Esto no hace offline el mapa: DEM e imagen satelital siguen usando red. |
| 40–60 | Integración | Una cámara con hora de lectura de metadatos, rumbo y estado de incertidumbre. Un fotograma y respuesta de Cosmos si su uso está autorizado. | Mostrar un caso negativo y, si existe, un positivo. Son pruebas de comportamiento, no una evaluación estadística de precisión. Sin positivo autorizado, mostrar visión como módulo todavía no validado para fuego. |
| 60–75 | Integración | Demo publicada con un acceso propio y `pulse-corridor` preservado. | Abrir el enlace desde otra sesión/dispositivo. Un pod sano o un enlace localhost no bastan. El host interno del clúster no resuelve desde este portátil; el acceso externo es un bloqueo pendiente. |
| 75–100 | Presentador + integración | Dos ensayos de tres minutos y una grabación de respaldo. | Un ensayo normal y otro sin una fuente. No cambiar funciones después del minuto 75 salvo que bloqueen la demo. |
| 100–120 | Presentador | Enlace enviado, video de respaldo disponible y pitch ensayado. | Revisar acceso del destinatario y confirmar que los enlaces y fechas del material son correctos. El envío externo lo realiza el usuario, salvo autorización explícita. |

## Condiciones para llamar a la demo lista

1. Un enlace accesible fuera del túnel local y una recarga completa en el dispositivo del presentador.
2. Relieve real y un caso temporal reproducible. La interfaz distingue dato publicado, reproducción y fuente ausente.
3. Cámara identificada, con hora y rumbo. Ningún marcador de fuego generado solo desde su azimut central.
4. Si mostramos inferencia, conservar imagen autorizada, respuesta, modelo y hora. El fotograma de la interfaz de Dilum solo demuestra conectividad, no detección positiva de fuego.
5. Si cámara y satélite no coinciden en fecha y lugar, se presentan como módulos separados.
6. Dos ensayos completos y respaldo de video. No depender de esperar una inferencia larga durante el pitch.

## Qué queda fuera hoy

Segmentación propia, reconstrucción del perímetro desde humo, ray casting sin calibración, triangulación operativa, seguimiento automático de múltiples incendios, predicción de propagación, rutas de evacuación, flota 3D de drones, cuentas y refactor general.

El índice VAST documentado es de tráfico, calles e interiores. Las búsquedas realizadas no encontraron evidencia útil de fuego. Eso no demuestra exhaustivamente que ningún clip lo contenga. No presentaremos coincidencias de niebla como evidencia de incendio. La restricción del challenge impide ingerir videos externos; cualquier excepción requiere confirmación de la organización.

## Guion propuesto de tres minutos

- **0:00–0:25.** Problema y objetivo: convertir observaciones dispersas en una perspectiva territorial útil para un operador.
- **0:25–1:05.** Relieve real y reproducción de observaciones NASA. Mostrar dos momentos y explicar sus fechas.
- **1:05–1:40.** Cámara seleccionada y rumbo publicado. Aclarar qué parte del terreno cubre y qué todavía no sabemos de la ubicación del foco.
- **1:40–2:15.** Fotograma autorizado y análisis Cosmos. Iniciar la llamada antes y tener una respuesta previa etiquetada como respaldo. Si no hay material autorizado, presentar el módulo como integración técnica pendiente de validación.
- **2:15–2:40.** Procedencia, hora, incertidumbre y exportación. Explicar cómo VAST almacenaría y recuperaría evidencia autorizada.
- **2:40–3:00.** Próxima prueba del proyecto: cámara calibrada, correspondencia temporal y error geográfico medido con referencias independientes. Cerrar con el valor que esa prueba permitiría demostrar.

## Envergadura del proyecto real

La interfaz es una parte pequeña del sistema que usarían autoridades. El trabajo principal se divide en seis frentes con dependencias.

1. **Datos y derechos de uso.** Archivo autorizado, poses históricas y relojes sincronizados. Es una dependencia externa, no una tarea de maquetación.
2. **Geometría.** Posición precisa de cámara, intrínsecos, zoom, orientación y calibración contra puntos de control. Los metadatos públicos actuales no bastan para garantizar precisión.
3. **Visión.** Datos etiquetados, segmentación o detección apropiada, negativos difíciles como niebla y nubes, y evaluación por condiciones y cámaras. Cosmos describiendo una imagen no sustituye este trabajo.
4. **Fusión temporal y espacial.** Relacionar observaciones del mismo evento entre sensores y mantener incertidumbre y antigüedad. FIRMS es una fuente de contraste con su propia resolución y error, no una verdad geográfica exacta para calibrar cámaras.
5. **Operación.** Disponibilidad, fallos de sensores, auditoría, revisión humana, control de acceso y pruebas con usuarios de emergencias.
6. **Predicción.** Añadir meteorología, combustibles y un modelo físico o estadístico validado. Es otro subsistema y debe empezar después de validar la observación geográfica.

La demo cabe en el plazo si limitamos las afirmaciones y estabilizamos el caso existente. Un piloto geográfico requiere trabajo de calibración y validación sobre datos concretos. El producto operativo requiere un equipo y pruebas de campo; no es defendible darle una fecha cerrada antes de conocer acceso, calidad de pose y tolerancia de error exigida.

## Primera decisión después de la demo

Elegir una cámara con acceso autorizado y varias referencias geográficas independientes. Medir el error sobre referencias reservadas para prueba y decidir una tolerancia antes de añadir una segunda cámara o predicción. Si la calibración falla, no escalar el número de cámaras.
