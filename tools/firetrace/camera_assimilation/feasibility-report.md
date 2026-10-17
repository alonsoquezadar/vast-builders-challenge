# Viabilidad temporal antes de delegar

Base: ceda01b, árbol limpio al comenzar. Reproducir con `python3 tools/firetrace/camera_assimilation/feasibility.py`.

Bajo la hipótesis PDT, las pasadas que caen dentro de cada pose del 27/08 son:

| Pose | Cámara | Pasadas en hora impresa supuesta | Ajuste / reserva temporal posible |
|---|---|---|---|
| G1 | Delilah | MODIS 11:17; VIIRS 12:49, 13:16, 13:38 | Sí |
| G2 | Delilah | Ninguna entre 16:11–20:16 | No |
| G3 | Buck Rock | Ninguna entre 10:32–10:41 | No |
| G3b | Buck Rock | VIIRS 12:49, 13:16, 13:38 | Sí |
| G4 | Buck Rock | VIIRS 14:29, 14:57; MODIS 16:00 | Sí |

G1/G3b permiten explorar ambas cámaras en el mismo periodo. Esto no prueba que identifiquen la misma base de humo ni que los relojes estén sincronizados. La validación reservará pasadas completas; los píxeles de una pasada no se separarán aleatoriamente entre ajuste y comprobación. Una detección NOAA-20 a las 13:38 no valida la extensión total del incendio.

No hay video de los días 26/28 en este archivo: esas pasadas son contexto temporal, no pares de calibración adicionales. El salto de FRP de las 16:00 precede en 11 min al principio de G2; no es una coincidencia exacta dentro de la pose. En Buck Rock G4 sí hay cobertura a las 16:00.

PDT queda como hipótesis. Se inspeccionó el fotograma del segundo 1 (Delilah, hora impresa 10:35:24.49), claramente diurno. Si la barra fuera UTC correspondería a las 03:35 del reloj de California en agosto, incompatible con esa luz. No se obtuvo una verificación histórica que distinga PDT de PST/reloj desfasado. La búsqueda en las páginas públicas ALERTCalifornia/ALERTWildfire no aportó un comprobante por cámara de agosto 2025. Los resultados bajo PST/UTC también se conservan en feasibility.json para sensibilidad; no son pruebas de reloj.

Puerta de decisión: PASA solo como experimento de correspondencia/calibración para G1/G3b/G4, con posición candidata y reloj supuesto. No pasa como calibración comprobada. Se autoriza el desarrollo paralelo, pero asimilación y UI deben desactivarse si el ajuste o las observaciones no tienen soporte.

Fuentes primarias consultadas para buscar reloj: https://alertcalifornia.org/faqs/ y https://cameras.alertcalifornia.org/ . Las poses proceden de planning/video-selection-shared-r1.md; cada fotograma nuevo debe verificar su barra. Las huellas de datos satelitales están en feasibility.json.
