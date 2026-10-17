# Vision A — estado: **paused-next-phase** (resultado ISSUES: 0 de 11 bases localizables)

Pausado por decisión del operador tras 8/8 pilotos Cosmos con `base_visible=false`; no se hicieron llamadas ni ampliaciones adicionales. SHA inicial `52b8b99`; HEAD al cerrar `7a5f33a` (commits de root; este pipeline no hizo operaciones git). Retrospectivo, solo investigación: no es pronóstico ni validación.

## Resultado medido (reales, no sintéticos)

| Medida | Valor |
|---|---|
| Observaciones Cosmos en `observations.json` | 11 (10 de este pipeline + 1 ejecutada por root sobre `evidence/garnet/delilah-134.jpg`) |
| `base_visible=true` | **0** · `false`: **11** · `smoke=true`: 11 · coordenadas: todas `null` |
| Hora impresa `verified-by-agent` / `uncertain` | 11 / 0 (segundos enteros; centésimas **no** verificadas) |
| Por pose | G1 3 · G2 3 · G3b 2 · G4 3 |
| Llamadas GPU del pipeline | 10/30 (8 pilotos de pasada + 2 G2 nocturno), 0 fallos, ~1–1,6 s cada una (`cosmos/ledger.json`); +1 de root (`externalAttempts`) = 11/30 |
| Respuestas “eco de plantilla” (conf 0.0, razón literal del prompt) | 6/11: `delilah-G1-f00963`, `delilah-G1-f01098`, `delilah-G2-f04020`, `buckrock-G3b-f05256`, `buckrock-G4-f06057`, `buckrock-G4-f06444` |
| Modelo | `nvidia/cosmos3-nano-reasoner`, task `smoke-base-v1`, vía `localhost:5173/api/analyze` |
| Vídeo original | `/tmp/firevids/garnet.ogg`, SHA256 `2d54936d…4240` (coincide con `evidence/garnet/manifest.json`) |

Pasadas cubiertas (hora impresa ↔ pasada, hipótesis PDT; gaps medidos en `data/candidates.json`, todos < 70 s ≤ 5 min): G1 11:17 (−68 s, candidato sin llamada), 12:49 (+12 s), 13:16 (−3 s), 13:38 (+43 s); G3b 12:49 (−4 s), 13:16 (+13 s), 13:38 (+42 s, sin llamada); G4 14:29 (+4 s), 14:57 (−19 s), 16:00 (+14 s). G2 sin pasadas (nocturno: 20:16:58, 20:21:44, 20:29:43).

## Hallazgos

1. **Cosmos se abstiene en el 100 %**, también en G2 nocturno, donde a ojo (revisión de agente, no humana) hay líneas de llama brillantes sobre la ladera, y en G1 13:15/13:38 donde parecen verse pies de columna parciales. No se forzó ninguna base: abstención ≠ ausencia, pero con 0 bases no hay correspondencias para B ni cámaras para C (`cameraUse = 0`).
2. Cosmos devuelve la plantilla en 6/11 llamadas (conf 0.0): salida de baja calidad incluso como abstención. Confianza no calibrada.
3. **El vídeo no es cronológicamente lineal ni uniforme**: ~2–3 min de hora impresa por cada 0,5 s de vídeo, con saltos de hasta 13–27 min y lecturas fuera de orden. La hora sale solo de la barra.
4. La cadencia real de la barra no sustenta “corrección cada minuto”: ~1 imagen fuente cada 0,8–13 min impresos dentro de poses (mediana ≈ 2,3–2,6 min).
5. OCR (macOS Vision) falla por dígitos borrosos: dos lecturas pueden coincidir en el mismo dígito erróneo (`13:39` por `13:59`, `14:12` por `14:17`). Por eso se exige monotonía cronológica dentro de la pose (subsecuencia no decreciente más larga) y revisión visual de las barras usadas.
6. En las ventanas 126–134 s (G2) la hora no se pudo leer del decodificado; el fotograma `delilah-134.jpg` de root se transcribió visualmente (20:16:58.11, X+25.27 Y+7.33 Z1.0 → G2) y coincide en píxeles con el decodificado en ~133,97 s (dif. media 2,3).
7. Nota de reloj: hoy impreso = UTC−7 (root, `clock-check/`, residuos 0,54/0,43 s). Eso no verifica el reloj de agosto 2025; `clockStatus` sigue `assumed-PDT`.

## Método (rerunable, orden)

```
python3 -I camera_assimilation/vision/scripts/scan_frames.py      # 8260 fotogramas decodificados, 4307 runs de imagen distinta, pts de ffprobe (data/frame_scan.json)
python3 -I .../ocr_timeline.py 15                                  # OCR de la barra cada 15 fotogramas (~0,5 s): 552 filas (data/timeline_ocr.json)
python3 -I .../densify.py 5                                        # cada 3.er fotograma ±5 min de cada pasada (data/timeline_dense.json)
python3 -I .../reread_unreadable.py                                # re-lectura solo de filas ilegibles
python3 -I .../timeline_clean.py                                   # monotonía + estados -> data/timeline.json
python3 -I .../make_candidates.py 4                                # JPEG originales (frames/), 65 candidatos: 10 de pasada, ~53 muestreo ~4 s, G2 nocturnos
python3 -I .../bar_sheets.py [--answered]                          # hojas de barras ampliadas para verificación visual
python3 -I .../cosmos_calls.py <ids>                               # secuencial, presupuesto 30 (ledger), crudos en cosmos/raw/
python3 -I .../build_observations.py && python3 -I .../contact_sheet.py
```
Requiere `ffmpeg/ffprobe`, `swiftc` (macOS Vision; `tesseract` no está en PATH), numpy, Pillow. Intermedios en `/tmp/firetrace_vision_scratch` (no versionados). Se reutiliza la OCR guardada; las llamadas Cosmos solo se repiten si falta el crudo. La elección de fotogramas usa solo la hora impresa y las horas de pasada: ninguna geografía FIRMS eligió píxeles.

## Archivos

`observations.json` (contrato v1; filas exactas, `method=cosmos` únicamente; recibos en `receipts`), `frames/*.jpg` (originales con créditos, SHA en cada fila), `cosmos/raw/*.json` (crudos), `cosmos/ledger.json`, `cosmos/night-receipt-root.json`, `contact/answered-frames.jpg` (marcas de base solo si visibles: ninguna), `contact/bars-*.jpg`, `data/visual_bar_checks.json` (lectura de agente, segundos enteros), `data/*.json`, `scripts/`.

## Límites

- Revisión por agente ≠ revisión humana: todo `reviewStatus=pending-operator-review`.
- 11 fotogramas elegidos cerca de pasadas no son muestra estadística; no se afirma precisión.
- **No se produjo comparación con detector heurístico** (pausa): no hay filas `simple-detector`; método separado pendiente, nunca sustituirá una abstención de Cosmos.
- No se ampliaron muestras N=4–8 s a Cosmos (solo existen como JPEG/candidatos y filas OCR); no hay G2 con pasadas, ni verificación histórica de reloj o pose.
- Eco de plantilla en 6/11 y confianza no calibrada.

## Estado y propuestas concretas (si se retoma)

Estado **ISSUES** (0 bases, `paused-next-phase`). Propuestas sin fabricar calibración: (1) vídeo con frente de llama cercano y pose estable (Blue Ridge Gypsum Canyon, 05:35–07:49, Palisades Topanga nocturno) donde Cosmos pueda ver contacto con suelo; (2) recorte/zoom del tercio inferior del encuadre o prompt de dos pasos (primero describir, luego decidir base) para reducir ecos de plantilla; (3) anotación de operador de 10–20 fotogramas con base visible como referencia de comparación y verificación de la barra; (4) heurística de máscaras color/luminancia solo como método separado con abstención, validada contra esa anotación antes de uso; (5) pedir a ALERTCalifornia constancia de reloj/pose histórica de ambas cámaras.
