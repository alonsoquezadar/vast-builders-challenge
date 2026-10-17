# Informe C — asimilación de cámaras (retrospectivo, Garnet 27/08/2025)

**Resultado: PAUSADO (`paused-next-phase`). No hay medición de cámaras.** `cameraUseCount = 0`; `corrected` está deshabilitado con motivo; ninguna corrección fabricada. Motivo: cambio de prioridad aprobado por el usuario y, según root/A, 8 de 8 bases Cosmos ocultas (no pude verificarlo: `vision/observations.json` no existía).

## Qué se construyó (rerunable)

- **Dominio y terreno:** malla de 200 m alineada a `arrival-reconstructed` (149×158, lon −119.245…−118.915, lat 36.815…37.095) con **DEM real** AWS Terrarium z12 (25 teselas, 3,2 MB con recibos y SHA en `dem/receipt.json`; elevación 291–3101 m). El DEM de 2 km del demo anterior no se usa. Se promedia a 200 m, lo que suaviza pendientes locales; precisión vertical no verificada.
- **Modelo:** ley de tasa de `simulation.py` (constantes importadas, sin editar) con viento horario del punto Open-Meteo (hora más cercana), combustible uniforme, 4 m/min base (valor por defecto del demo, sin ajustar). Heurístico, no validado.
- **Inicialización:** t0 = 27/08 10:00 PDT desde `arrival-reconstructed`, solo celdas `observed-support` con primera detección ≤ t0 (1056 celdas, 4224 ha de celdas). Alternativa con celdas interpoladas: 1193 (+137). **Fuga retrospectiva visible** en `initialization.leakage`: reconstrucción confinada al perímetro final, detecciones a <1 km de él, radio de 400 m que sobreestima el área temprana, actividad uniforme en todo el perímetro. No es pronóstico operacional. Las pasadas ≤ t0 son datos de inicialización y nunca se puntúan.
- **Asimilación (código listo, sin datos reales):** ensemble de 300 miembros (sesgo de viento, multiplicador global, 12 multiplicadores sectoriales). Una base visible es un **intervalo angular** (calibración + píxel + media celda); la verosimilitud mide qué tan cerca queda del conjunto de celdas de “cabeza” activa de cada miembro (set-valued, con piso de outliers). No se triangula ni se infiere alcance. Cada pose cuenta como una observación efectiva (atenuación 1/n). Solo se actualizan parámetros con test de permutación significativo; el resto vuelve al prior. La corrección solo se aplica dentro del sector de visión; fuera, igual al baseline. Puertas: σ, colapso de ESS, ganancia de información, identificabilidad.
- **Causalidad y reservas:** una fila entra a un ciclo solo si su hora ≤ issueTime del ciclo; la pasada verificada debe ser estrictamente posterior (aserción en `experiment.score`). FIRMS nunca se asimila. Modelo X impreso: ninguna pasada ajustada, todas las posteriores a t0 son validación. Modelo ajustado (contraste): pasadas de ajuste nunca puntuadas; ids de observación holdout de B reservados. σ se arma sin residuos holdout (`suggestedAngularHalfWidthDeg` de un modelo ajustado no se lee; el prior del modelo impreso se ignora si `holdoutEvaluated=true`). Se rechaza `observationsBound=false`.
- **Evaluación:** en la hora real de la pasada, con lead real (pasada − issue) y desfase respecto a 30/60 declarado (`deltaFromNominalMin`, `declaredLeadMismatch`). Baseline, ensemble neutro (aísla el efecto de la cámara) y corregido; métrica primaria: mediana de la distancia de cada detección a la banda activa (últimos 60 min) del modelo; veredicto con tolerancia de 100 m; sensibilidad de tolerancia ×0,6/×1/×2. Si empeora, queda como `worsened` y se lista en `worsenedDisclosure`. Sin significancia estadística (pocas pasadas no independientes).

## Medición real disponible: baseline sin cámaras vs FIRMS (no corregido)

Corrida `--paused-reason …` sobre capas reales. Tolerancias preregistradas: VIIRS 500 m, MODIS 1000 m. Lead = desde t0, no desde una cámara. Las 7 pasadas siguientes a t0 son validación elegible (ninguna se ajustó).

| Pasada | PDT (supuesto) | lead t0 (min) | det. | mediana dist. a banda activa (m) | recall banda activa | precisión banda activa | recall crecimiento (n) |
|---|---|---|---|---|---|---|---|
| MODIS 18:17Z | 11:17 | 77 | 2 | 438 | 1,00 | 0,09 | n/a (0) |
| NOAA21 19:49Z | 12:49 | 169 | 12 | 1131 | 0,08 | 0,00 | 1,00 (2) |
| SNPP 20:16Z | 13:16 | 196 | 8 | 1718 | 0,00 | 0,00 | 1,00 (1) |
| NOAA20 20:38Z | 13:38 | 218 | 1 | 1796 | 0,00 | 0,00 | n/a (0) |
| NOAA21 21:29Z | 14:29 | 269 | 72 | 1188 | 0,17 | 0,04 | 0,60 (30) |
| SNPP 21:57Z | 14:57 | 297 | 55 | 1334 | 0,18 | 0,06 | 0,37 (35) |
| MODIS 23:00Z | 16:00 | 360 | 10 | 1629 | 0,30 | 0,07 | 1,00 (2) |

Lectura: el baseline uniforme queda a ~1,1–1,8 km (≈ 2–4 tolerancias VIIRS) de la banda activa en la mayoría de pasadas, con recall de banda activa ≤ 0,3 salvo MODIS temprano. La precisión es baja por construcción (una pasada ve un subconjunto del frente; FIRMS no mide área ni frente). Estas cifras describen un modelo heurístico, no ajustado, con inicialización retrospectiva y combustible/actividad uniformes; no se afinó ningún parámetro con ellas. No dicen nada sobre la utilidad de las cámaras.

## Qué NO se demostró

- Ninguna corrección por cámara en datos reales (0 bases visibles utilizables, fase pausada). Nunca se ejecutó `completed` con observaciones reales; el camino completo (ciclos, verificación, geojson, sensibilidades) solo se ejercitó con filas **sintéticas** sobre capas reales, como prueba de humo, sin conservar ni presentar esos resultados.
- Las 19 pruebas sintéticas comprueban mecánica (la cámara mueve el posterior solo dentro del sector, base oculta no cambia nada, corte causal, puertas, reservas intactas, σ sin holdouts), no habilidad.
- Reloj PDT y X impreso como azimut siguen siendo hipótesis; DEM, viento de un punto y combustible uniforme limitan cualquier lectura.
