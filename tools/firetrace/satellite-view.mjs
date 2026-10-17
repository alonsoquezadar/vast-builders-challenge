// Capa satelital y meteorológica del Garnet Fire para el visor FireTrace.
// Contrato con incident.js:
//   const satellite = await mountSatellite(map, document.getElementById('satellite-panel'));
//   satellite.onMomentChanged(pair.frames);          // desde render()
// `mountSatellite` es async solo por contrato: construye el panel y resuelve de inmediato; los datos
// y las capas del mapa se cargan después (controller.ready). `createSatellite` es la misma función
// síncrona, por si el root prefiere recibir el controller sin await.
// Las capas y el cursor temporal no dependen de las parejas de cámaras, salvo con la opción de supuesto PDT.

export const RANGE_START_SEC = Date.UTC(2025, 7, 24, 0, 0) / 1000;
export const RANGE_END_SEC = Date.UTC(2025, 8, 12, 23, 59) / 1000;
export const CURSOR_STEP_SEC = 60;
// Cursor inicial arbitrario (inicio del 27/08 UTC); no corresponde a ninguna hora de cámara.
export const DEFAULT_CURSOR_SEC = Date.UTC(2025, 7, 27, 0, 0) / 1000;
export const HOTSPOT_WINDOW_HOURS = 12;
export const WEATHER_MAX_GAP_SEC = 3600;
export const PDT_OFFSET_HOURS = 7;
export const PERIMETER_PUBLISHED_FALLBACK = '2025-12-19';

export const LAYERS = {
  hotspots: {label: 'Focos térmicos OBSERVADOS (NASA FIRMS)', expected: 'observed', defaultOn: true},
  arrival: {label: 'Llegada RECONSTRUIDA (celdas de 200 m)', expected: 'reconstructed', defaultOn: false},
  perimeter: {label: 'Perímetro FINAL (WFIGS)', expected: 'observed', defaultOn: false},
  weather: {label: 'Meteorología histórica (modelo)', expected: 'historical-model'},
  summary: {label: 'Resumen', expected: null}
};
const MAP_LAYER_NAMES = ['arrival', 'perimeter', 'hotspots']; // de abajo hacia arriba
const UI_ORDER = ['hotspots', 'arrival', 'perimeter'];

export class SatelliteError extends Error {}

// ---------- tiempo ----------

export function clampCursor(sec) {
  if (!Number.isFinite(sec)) throw new SatelliteError('Fecha del cursor inválida.');
  const snapped = Math.round((sec - RANGE_START_SEC) / CURSOR_STEP_SEC) * CURSOR_STEP_SEC + RANGE_START_SEC;
  return Math.min(RANGE_END_SEC, Math.max(RANGE_START_SEC, snapped));
}

export function formatUtc(sec) {
  return new Date(sec * 1000).toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
}

export function formatCount(n) {
  return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}

// Ventana de focos: [cursor − 12 h, cursor]; nunca incluye detecciones posteriores al cursor.
export function hotspotWindow(cursorSec, hours = HOTSPOT_WINDOW_HOURS) {
  return {fromSec: cursorSec - hours * 3600, toSec: cursorSec};
}
export function hotspotFilter(cursorSec) {
  const {fromSec, toSec} = hotspotWindow(cursorSec);
  return ['all', ['>=', ['get', 't'], fromSec], ['<=', ['get', 't'], toSec]];
}
export function arrivalFilter(cursorSec) {
  return ['<=', ['get', 't'], cursorSec];
}

export function sortedTimes(features, predicate = () => true) {
  const times = [];
  for (const f of features) if (Number.isFinite(f?.properties?.t) && predicate(f.properties)) times.push(f.properties.t);
  return Float64Array.from(times).sort();
}
// Primer índice cuyo valor no cumple `before(value)`.
function partition(sorted, before) {
  let lo = 0, hi = sorted.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (before(sorted[mid])) lo = mid + 1; else hi = mid; }
  return lo;
}
// Elementos con lo <= t <= hi.
export function countInRange(sorted, lo, hi) {
  if (hi < lo) return 0;
  return partition(sorted, v => v <= hi) - partition(sorted, v => v < lo);
}

// ---------- supuesto PDT para relacionar la hora impresa de las cámaras ----------

export function parsePrintedClockAsUtcSeconds(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?$/.exec(String(value));
  if (!m) throw new SatelliteError('Hora impresa inválida.');
  const [y, mo, d, h, mi, s] = m.slice(1).map(Number);
  const date = new Date(Date.UTC(y, mo - 1, d, h, mi, s));
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== mo - 1 || date.getUTCDate() !== d || h > 23 || mi > 59 || s > 59) throw new SatelliteError('Hora impresa inválida.');
  return date.getTime() / 1000;
}

// La zona horaria de las cámaras no está confirmada: esto es una HIPÓTESIS, no una conversión verificada.
export function assumedUtcFromPrinted(printedTime, offsetHours = PDT_OFFSET_HOURS) {
  return parsePrintedClockAsUtcSeconds(printedTime) + offsetHours * 3600;
}

export function cursorFromFrames(frames) {
  const first = Array.isArray(frames) ? frames[0] : null;
  if (!first || typeof first.printedTime !== 'string') return {ok: false, reason: 'sin-fotogramas'};
  let assumedSec;
  try { assumedSec = assumedUtcFromPrinted(first.printedTime); } catch { return {ok: false, reason: 'hora-invalida'}; }
  const printed = first.printedTime.replace('T', ' ').replace(/\.\d+$/, '');
  if (assumedSec < RANGE_START_SEC - CURSOR_STEP_SEC / 2 || assumedSec > RANGE_END_SEC + CURSOR_STEP_SEC / 2) return {ok: false, reason: 'fuera-de-rango', assumedSec, printed};
  return {ok: true, sec: clampCursor(assumedSec), assumedSec, printed};
}

export function assumptionNote(result) {
  if (!result) return 'Aún no hay fotogramas seleccionados; se aplicará al elegir un momento.';
  if (result.ok) return `SUPUESTO, no verificado: hora impresa del primer fotograma (${result.printed}, zona horaria sin confirmar) + ${PDT_OFFSET_HOURS} h = ${formatUtc(result.sec)}. No afirma sincronía entre cámaras ni con los satélites.`;
  if (result.reason === 'fuera-de-rango') return `El supuesto PDT daría ${formatUtc(result.assumedSec)}, fuera del rango 24 ago–12 sep. Cursor sin cambios.`;
  if (result.reason === 'hora-invalida') return 'La hora impresa del primer fotograma no se pudo interpretar. Cursor sin cambios.';
  return 'Aún no hay fotogramas seleccionados; se aplicará al elegir un momento.';
}

// ---------- meteorología ----------

const CARDINALS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSO', 'SO', 'OSO', 'O', 'ONO', 'NO', 'NNO'];
export function cardinal(deg) {
  return CARDINALS[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16];
}

export function prepareWeather(raw) {
  if (!Array.isArray(raw?.hours) || !raw.hours.length) throw new SatelliteError('Datos de meteorología con formato inesperado.');
  const rows = [];
  for (const h of raw.hours) {
    const sec = Date.parse(h?.timeUtc) / 1000;
    if (Number.isFinite(sec)) rows.push({...h, sec});
  }
  if (!rows.length) throw new SatelliteError('Datos de meteorología con formato inesperado.');
  return rows.sort((a, b) => a.sec - b.sec);
}

// Hora del reanálisis más cercana al cursor y a no más de 1 h; fuera de eso devuelve null (nunca la última fila).
export function nearestWeatherHour(rows, cursorSec, maxGapSec = WEATHER_MAX_GAP_SEC) {
  if (!Array.isArray(rows) || !Number.isFinite(cursorSec)) return null;
  let best = null;
  for (const row of rows) {
    const gap = Math.abs(row.sec - cursorSec);
    if (!best || gap < best.gap || (gap === best.gap && row.sec < best.row.sec)) best = {row, gap};
  }
  return best && best.gap <= maxGapSec ? {hour: best.row, gapSec: best.gap} : null;
}

export function weatherLines(match, point) {
  if (!match) return ['Sin hora del modelo histórico a ≤ 1 h del cursor.'];
  const h = match.hour;
  const num = (v, unit, digits = 0) => (Number.isFinite(v) ? `${Number(v).toFixed(digits)} ${unit}` : 'sin dato');
  const wind = Number.isFinite(h.windFromDeg) ? `desde ${Math.round(h.windFromDeg)}° (${cardinal(h.windFromDeg)}) a ${num(h.windSpeedMps, 'm/s', 1)}` : 'sin dato';
  const lines = [
    `Hora del modelo histórico: ${formatUtc(h.sec)}${match.gapSec ? ` (${Math.round(match.gapSec / 60)} min de diferencia con el cursor)` : ''}`,
    `Viento a 10 m: ${wind}`,
    `Humedad relativa: ${num(h.rhPct, '%')}`,
    `Temperatura: ${num(h.tempC, '°C', 1)}`
  ];
  if (Number.isFinite(h.gustMps)) lines.splice(2, 0, `Ráfagas: ${num(h.gustMps, 'm/s', 1)}`);
  if (point && Number.isFinite(point.lat) && Number.isFinite(point.lon)) lines.push(`Punto del modelo histórico: ${point.lat}, ${point.lon}${Number.isFinite(point.elevationM) ? ` · ${Math.round(point.elevationM)} m` : ''}`);
  return lines;
}

// ---------- carga de capas ----------

export function validateLayer(name, data) {
  const bad = () => new SatelliteError(`Datos de «${LAYERS[name]?.label || name}» con formato inesperado.`);
  if (!LAYERS[name] || !data || typeof data !== 'object') throw bad();
  if (name === 'weather') { prepareWeather(data); return; }
  if (name === 'summary') { if (!data.counts || typeof data.counts !== 'object') throw bad(); return; }
  if (data.type !== 'FeatureCollection' || !Array.isArray(data.features) || (name === 'perimeter' && !data.features.length)) throw bad();
}

export async function fetchLayer(name, fetchFn) {
  let response, data = null;
  try { response = await fetchFn(`./api/satellite?layer=${encodeURIComponent(name)}`); } catch { throw new SatelliteError('No se pudo contactar con el servicio de datos satelitales.'); }
  try { data = await response.json(); } catch { /* cuerpo no JSON */ }
  if (!response.ok) throw new SatelliteError(typeof data?.error === 'string' && data.error && data.error.length < 200 ? data.error : `El servicio respondió HTTP ${response.status}.`);
  validateLayer(name, data);
  return data;
}

// Estado por fuente: idle | loading | ready | error. Una carga en curso se comparte; un error permite reintentar.
export function createLayerStore(fetchFn, onChange = () => {}) {
  const entries = {};
  for (const name of Object.keys(LAYERS)) entries[name] = {state: 'idle', data: null, error: null, promise: null};
  return {
    get: name => entries[name],
    load(name) {
      const entry = entries[name];
      if (!entry) return Promise.reject(new SatelliteError('Capa desconocida.'));
      if (entry.state === 'ready') return Promise.resolve(entry.data);
      if (entry.state === 'loading') return entry.promise;
      entry.state = 'loading'; entry.error = null; onChange(name);
      entry.promise = fetchLayer(name, fetchFn).then(data => {
        entry.state = 'ready'; entry.data = data; onChange(name); return data;
      }, error => {
        entry.state = 'error'; entry.error = error instanceof SatelliteError ? error.message : 'Error inesperado al cargar la capa.'; onChange(name); throw error;
      });
      return entry.promise;
    }
  };
}

export function provenanceText(data) {
  const p = data?._provenance;
  if (!p || typeof p !== 'object') return 'procedencia no declarada';
  const parts = [];
  if (typeof p.dataClass === 'string') parts.push(p.dataClass);
  const hashKey = Object.keys(p).find(k => /hash|sha/i.test(k) && typeof p[k] === 'string');
  if (hashKey) parts.push(`sha256 ${p[hashKey].slice(0, 12)}…`);
  return parts.length ? parts.join(' · ') : 'procedencia no declarada';
}

export function classificationWarning(name, data) {
  const expected = LAYERS[name]?.expected;
  return expected && typeof data?.status === 'string' && data.status !== expected ? `clasificación inesperada «${data.status}»` : '';
}

// ---------- capas del mapa ----------

const ids = name => ({source: `firetrace-sat-${name}`, layer: `firetrace-sat-${name}-${{hotspots: 'circle', arrival: 'fill', perimeter: 'line'}[name]}`});
export const mapLayerId = name => ids(name).layer;

function layerSpec(name) {
  const {source, layer} = ids(name);
  if (name === 'hotspots') return {id: layer, type: 'circle', source, filter: hotspotFilter(DEFAULT_CURSOR_SEC), paint: {
    'circle-radius': ['interpolate', ['linear'], ['coalesce', ['get', 'frpMW'], 0], 0, 3, 20, 5, 100, 9, 500, 14],
    'circle-color': '#e8741c', 'circle-opacity': 0.8, 'circle-stroke-color': '#fff1d6', 'circle-stroke-width': 0.6}};
  if (name === 'arrival') return {id: layer, type: 'fill', source, filter: arrivalFilter(DEFAULT_CURSOR_SEC), paint: {
    'fill-color': ['match', ['get', 'kind'], 'interpolated', '#b79ad6', '#6b46a3'], 'fill-opacity': 0.42}};
  return {id: layer, type: 'line', source, layout: {'line-join': 'round'}, paint: {'line-color': '#ffe9a8', 'line-width': 2.2, 'line-dasharray': [2, 1.5]}};
}

export function createMapLayers(map) {
  const present = new Set();
  let cursorSec = DEFAULT_CURSOR_SEC;
  const filterFor = {hotspots: hotspotFilter, arrival: arrivalFilter};
  const beforeIdFor = name => {
    for (const later of MAP_LAYER_NAMES.slice(MAP_LAYER_NAMES.indexOf(name) + 1)) if (present.has(later)) return ids(later).layer;
    return undefined;
  };
  return {
    has: name => present.has(name),
    show(name, data) {
      const {source, layer} = ids(name);
      if (!present.has(name)) {
        if (!map.getSource(source)) map.addSource(source, {type: 'geojson', data});
        const spec = layerSpec(name);
        if (filterFor[name]) spec.filter = filterFor[name](cursorSec);
        map.addLayer(spec, beforeIdFor(name));
        present.add(name);
      }
      map.setLayoutProperty(layer, 'visibility', 'visible');
    },
    hide(name) { if (present.has(name)) map.setLayoutProperty(ids(name).layer, 'visibility', 'none'); },
    setCursor(sec) {
      cursorSec = sec;
      for (const name of present) if (filterFor[name]) map.setFilter(ids(name).layer, filterFor[name](sec));
    },
    layerIds: () => [...present].map(n => ids(n).layer)
  };
}

export function whenMapReady(map) {
  const ready = () => { try { return Boolean(map.getStyle()); } catch { return false; } };
  return new Promise(resolve => {
    if (ready()) return resolve();
    const check = () => { if (ready()) { map.off('styledata', check); map.off('load', check); resolve(); } };
    map.on('styledata', check);
    map.on('load', check);
  });
}

export function popupLines(name, props = {}) {
  if (name === 'hotspots') return [
    'Foco térmico OBSERVADO',
    `Fecha: ${props.acquiredUtc ?? 'sin dato'} (UTC)`,
    `Fuente: ${props.source ?? 'sin dato'}${props.satellite ? ` · ${props.satellite}` : ''}`,
    `Confianza: ${props.confidence ?? 'sin dato'} · FRP ${Number.isFinite(props.frpMW) ? props.frpMW + ' MW' : 'sin dato'}`,
    `Centro de un píxel de ~${props.pixelM ?? '?'} m: no mide frente, área ni velocidad.`
  ];
  if (name === 'arrival') return [
    'Celda RECONSTRUIDA (200 m), no frente observado',
    `Fecha estimada de llegada: ${props.arrivalUtc ?? 'sin dato'} (UTC)`,
    `Tipo: ${props.kind === 'interpolated' ? 'interpolada (mediana de 6 celdas vecinas con soporte)' : props.kind === 'observed-support' ? 'primera detección VIIRS a ≤ 400 m' : props.kind ?? 'sin dato'}`,
    'Fuente: detecciones FIRMS; recortada por el perímetro final.'
  ];
  return [
    'Perímetro FINAL WFIGS',
    `Polígono publicado: ${props.polygonDateTime ?? 'sin dato'} (UTC)`,
    `Método: ${props.mapMethod ?? 'sin dato'}`,
    'Estado final del incendio; no es el perímetro de una fecha intermedia.'
  ];
}

// ---------- panel ----------

const LEGEND = [
  ['satellite-chip-hotspot', 'Foco térmico observado; el radio crece con la FRP'],
  ['satellite-chip-arrival', 'Celda reconstruida con soporte de detección (≤ 400 m)'],
  ['satellite-chip-interpolated', 'Celda reconstruida interpolada'],
  ['satellite-chip-perimeter', 'Perímetro FINAL WFIGS']
];

function el(doc, tag, attrs = {}, ...children) {
  const node = doc.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) { if (k === 'class') node.className = v; else node.setAttribute(k, v); }
  node.append(...children);
  return node;
}

export function createSatellite(map, container, options = {}) {
  const doc = container.ownerDocument;
  const fetchFn = options.fetchFn || ((...args) => fetch(...args));
  const maplibre = options.maplibre || globalThis.maplibregl;
  const raf = options.requestAnimationFrame || globalThis.requestAnimationFrame?.bind(globalThis) || (fn => setTimeout(fn, 0));
  if (!doc.querySelector('link[href*="satellite-view.css"]')) doc.head.append(el(doc, 'link', {rel: 'stylesheet', href: new URL('./satellite-view.css', import.meta.url).href}));

  let cursorSec = DEFAULT_CURSOR_SEC, cursorFromAssumption = false, assumeOn = false, lastFrames = null, playTimer = null, destroyed = false, renderPending = false;
  let mapLayers = null, weatherRows = null, weatherPoint = null, summary = null, popup = null, clickHandler = null;
  const times = {};
  const refs = {};

  const store = createLayerStore(fetchFn, name => { if (!destroyed) renderLayerStatus(name); });

  // --- DOM ---
  const panel = el(doc, 'section', {class: 'satellite-panel', 'aria-label': 'Capa satelital y meteorológica'});
  panel.append(el(doc, 'h3', {class: 'satellite-title'}, 'Satélite y meteorología'));
  panel.append(el(doc, 'p', {class: 'satellite-scope'}, 'Detecciones térmicas de NASA FIRMS (24 ago–12 sep 2025) y modelo meteorológico histórico. Los focos son anomalías térmicas en el centro de un píxel: no miden frente, área ni velocidad.'));

  const fieldset = el(doc, 'fieldset', {class: 'satellite-layers'}, el(doc, 'legend', {}, 'Capas'));
  for (const name of UI_ORDER) {
    const input = el(doc, 'input', {type: 'checkbox', id: `satellite-toggle-${name}`});
    const text = el(doc, 'span', {class: 'satellite-layer-name'}, LAYERS[name].label);
    const status = el(doc, 'span', {class: 'satellite-layer-status', role: 'status', 'aria-live': 'polite'});
    refs[name] = {input, text, status};
    fieldset.append(el(doc, 'div', {class: `satellite-layer satellite-layer-${name}`}, el(doc, 'label', {for: input.id}, input, text), status));
  }
  panel.append(fieldset);

  const slider = el(doc, 'input', {type: 'range', id: 'satellite-cursor', min: RANGE_START_SEC, max: RANGE_END_SEC, step: CURSOR_STEP_SEC, value: DEFAULT_CURSOR_SEC});
  const dateOut = el(doc, 'output', {class: 'satellite-date', for: 'satellite-cursor'});
  const badge = el(doc, 'span', {class: 'satellite-badge', hidden: ''}, 'SUPUESTO PDT');
  const playButton = el(doc, 'button', {type: 'button', class: 'satellite-play'}, '▶ Reproducir');
  const assumeInput = el(doc, 'input', {type: 'checkbox', id: 'satellite-assume-pdt'});
  const assumeNote = el(doc, 'p', {class: 'satellite-assume-note', role: 'status', 'aria-live': 'polite'});
  panel.append(el(doc, 'div', {class: 'satellite-time'},
    el(doc, 'label', {for: 'satellite-cursor', class: 'satellite-time-label'}, 'Cursor cronológico (UTC)'),
    el(doc, 'div', {class: 'satellite-time-row'}, slider),
    el(doc, 'div', {class: 'satellite-time-row'}, dateOut, badge, playButton),
    el(doc, 'label', {class: 'satellite-assume', for: 'satellite-assume-pdt'}, assumeInput, el(doc, 'span', {}, 'Asumir PDT (UTC−7) para relacionar horas de cámara')),
    assumeNote));

  const countersList = el(doc, 'ul', {class: 'satellite-counters'});
  const weatherList = el(doc, 'ul', {class: 'satellite-weather-list'});
  const weatherHead = el(doc, 'p', {class: 'satellite-weather-note'}, 'Meteorología MODELADA (Open-Meteo Historical · Best Match), un único punto; no es una estación observada.');
  const legendList = el(doc, 'ul', {class: 'satellite-legend-list'});
  for (const [cls, text] of LEGEND) legendList.append(el(doc, 'li', {}, el(doc, 'i', {class: `satellite-chip ${cls}`}), text));
  const dependency = el(doc, 'p', {class: 'satellite-dependency'});
  panel.append(
    el(doc, 'div', {class: 'satellite-block'}, el(doc, 'h4', {}, 'En el cursor'), countersList),
    el(doc, 'div', {class: 'satellite-block'}, el(doc, 'h4', {}, 'Meteorología en el cursor'), weatherHead, weatherList),
    el(doc, 'div', {class: 'satellite-block'}, el(doc, 'h4', {}, 'Leyenda'), legendList),
    dependency);
  container.replaceChildren(panel);

  const setList = (list, lines) => list.replaceChildren(...lines.map(l => el(doc, 'li', {}, l)));

  function perimeterDate() {
    const props = store.get('perimeter').data?.features?.[0]?.properties;
    return typeof props?.polygonDateTime === 'string' ? props.polygonDateTime.slice(0, 10) : PERIMETER_PUBLISHED_FALLBACK;
  }

  function renderStatic() {
    refs.perimeter.text.textContent = `${LAYERS.perimeter.label}, publicado ${perimeterDate()}`;
    const c = summary?.counts;
    const scope = Number.isFinite(c?.arrivalCells) && Number.isFinite(c?.cellsWithDetectionSupport) ? `${formatCount(c.arrivalCells)} celdas de 200 m, ${formatCount(c.cellsWithDetectionSupport)} con una detección cercana (≤ 400 m) y ${formatCount(c.arrivalCells - c.cellsWithDetectionSupport)} interpoladas; ` : 'Celdas de 200 m con detección cercana o interpoladas; ';
    dependency.textContent = `Reconstrucción retrospectiva (${scope}todas RECONSTRUIDAS, no un frente observado). Depende del perímetro FINAL publicado el ${perimeterDate()}: queda recortada por él y no representa el estado de ningún día intermedio. No se infiere perímetro, área ni velocidad.`;
  }

  function renderLayerStatus(name) {
    const entry = store.get(name);
    if (!refs[name]) {
      if (name === 'weather' || name === 'summary') {
        if (name === 'summary' && entry.state === 'ready') summary = entry.data;
        if (name === 'weather' && entry.state === 'ready') { weatherRows = prepareWeather(entry.data); weatherPoint = entry.data.point || null; }
        renderStatic(); renderCursor();
      }
      return;
    }
    const {input, status} = refs[name];
    input.disabled = entry.state === 'loading';
    const warn = entry.state === 'ready' ? classificationWarning(name, entry.data) : '';
    status.textContent = entry.state === 'loading' ? 'Cargando…'
      : entry.state === 'error' ? `Error: ${entry.error} Marca la casilla para reintentar.`
      : entry.state === 'ready' ? `${provenanceText(entry.data)}${warn ? ` · ⚠ ${warn}` : ''}`
      : '';
    status.classList.toggle('satellite-error', entry.state === 'error');
    if (entry.state === 'error') input.checked = false;
    if (name === 'perimeter' && entry.state === 'ready') renderStatic();
  }

  function indexLayer(name, data) {
    if (name === 'hotspots' && !times.hotspots) times.hotspots = sortedTimes(data.features);
    if (name === 'arrival' && !times.arrivalSupported) {
      times.arrivalSupported = sortedTimes(data.features, p => p.kind === 'observed-support');
      times.arrivalInterpolated = sortedTimes(data.features, p => p.kind === 'interpolated');
    }
  }

  function renderCursor() {
    slider.value = cursorSec;
    slider.setAttribute('aria-valuetext', formatUtc(cursorSec));
    dateOut.textContent = formatUtc(cursorSec);
    badge.hidden = !(assumeOn && cursorFromAssumption);
    const {fromSec, toSec} = hotspotWindow(cursorSec);
    const lines = [];
    if (!refs.hotspots.input.checked || !times.hotspots) lines.push(`Focos observados (ventana de ${HOTSPOT_WINDOW_HOURS} h): ${store.get('hotspots').state === 'ready' ? 'capa desactivada' : '—'}`);
    else lines.push(`Focos térmicos observados en las ${HOTSPOT_WINDOW_HOURS} h previas: ${formatCount(countInRange(times.hotspots, fromSec, toSec))} de ${formatCount(times.hotspots.length)} en total`);
    if (!refs.arrival.input.checked || !times.arrivalSupported) lines.push(`Celdas reconstruidas hasta el cursor: ${store.get('arrival').state === 'ready' ? 'capa desactivada' : 'capa desactivada o sin cargar'}`);
    else {
      const a = countInRange(times.arrivalSupported, -Infinity, cursorSec), b = countInRange(times.arrivalInterpolated, -Infinity, cursorSec);
      lines.push(`Celdas RECONSTRUIDAS hasta el cursor: ${formatCount(a + b)} de ${formatCount(times.arrivalSupported.length + times.arrivalInterpolated.length)} (${formatCount(a)} con soporte de detección, ${formatCount(b)} interpoladas)`);
    }
    setList(countersList, lines);
    if (!weatherRows) setList(weatherList, [store.get('weather').state === 'error' ? `Meteorología no disponible: ${store.get('weather').error}` : 'Cargando meteorología…']);
    else setList(weatherList, weatherLines(nearestWeatherHour(weatherRows, cursorSec), weatherPoint));
    if (mapLayers) mapLayers.setCursor(cursorSec);
  }

  function scheduleRender() {
    if (renderPending || destroyed) return;
    renderPending = true;
    raf(() => { renderPending = false; if (!destroyed) renderCursor(); });
  }

  function setCursor(sec, fromAssumption = false) {
    cursorSec = clampCursor(sec);
    cursorFromAssumption = fromAssumption;
    renderCursor();
    return cursorSec;
  }

  function applyAssumption() {
    const result = lastFrames ? cursorFromFrames(lastFrames) : null;
    assumeNote.textContent = assumptionNote(result);
    if (result?.ok) setCursor(result.sec, true);
  }

  // --- capas ---
  function mapReadyLayers() { return mapReady.then(() => mapLayers); }

  async function activate(name) {
    const entry = store.get(name);
    if (entry.state === 'loading') return;
    try {
      const data = await store.load(name);
      if (destroyed) return;
      indexLayer(name, data);
      refs[name].input.disabled = false;
      if (refs[name].input.checked) {
        const layers = await mapReadyLayers();
        if (destroyed) return;
        if (refs[name].input.checked) layers.show(name, data);
      }
    } catch (error) {
      if (destroyed) return;
      const entryNow = store.get(name);
      if (entryNow.state !== 'error') { refs[name].status.textContent = 'Error: no se pudo añadir la capa al mapa.'; refs[name].status.classList.add('satellite-error'); refs[name].input.checked = false; refs[name].input.disabled = false; }
    }
    renderCursor();
  }

  for (const name of MAP_LAYER_NAMES) {
    const {input} = refs[name];
    input.checked = LAYERS[name].defaultOn === true;
    input.addEventListener('change', () => {
      if (input.checked) activate(name);
      else { mapLayers?.hide(name); renderCursor(); }
    });
  }

  // --- tiempo ---
  slider.addEventListener('input', () => { stopPlayback(); cursorSec = clampCursor(Number(slider.value)); cursorFromAssumption = false; scheduleRender(); });
  assumeInput.addEventListener('change', () => {
    assumeOn = assumeInput.checked;
    if (assumeOn) applyAssumption(); else { assumeNote.textContent = ''; cursorFromAssumption = false; renderCursor(); }
  });
  function stopPlayback() {
    if (playTimer === null) return;
    clearInterval(playTimer); playTimer = null;
    playButton.textContent = '▶ Reproducir';
  }
  playButton.addEventListener('click', () => {
    if (playTimer !== null) return stopPlayback();
    if (cursorSec >= RANGE_END_SEC) cursorSec = RANGE_START_SEC;
    playButton.textContent = '⏸ Pausar';
    playTimer = setInterval(() => {
      cursorFromAssumption = false;
      cursorSec = clampCursor(cursorSec + 3600);
      scheduleRender();
      if (cursorSec >= RANGE_END_SEC) stopPlayback();
    }, 150);
  });

  // --- mapa ---
  const mapReady = whenMapReady(map).then(() => {
    mapLayers = createMapLayers(map);
    if (maplibre?.Popup) {
      clickHandler = e => {
        const present = mapLayers.layerIds();
        if (!present.length) return;
        const box = [[e.point.x - 4, e.point.y - 4], [e.point.x + 4, e.point.y + 4]];
        const hit = map.queryRenderedFeatures(box, {layers: present})[0];
        if (!hit) return;
        const name = MAP_LAYER_NAMES.find(n => mapLayerId(n) === hit.layer.id);
        const content = el(doc, 'div', {class: 'satellite-popup'}, ...popupLines(name, hit.properties).map(t => el(doc, 'p', {}, t)));
        popup?.remove();
        popup = new maplibre.Popup({maxWidth: '300px'}).setLngLat(e.lngLat).setDOMContent(content).addTo(map);
      };
      map.on('click', clickHandler);
    }
    return mapLayers;
  });

  renderStatic();
  renderCursor();
  const loads = [store.load('summary'), store.load('weather'), ...MAP_LAYER_NAMES.filter(n => refs[n].input.checked).map(activate)];
  const ready = Promise.allSettled(loads).then(() => mapReady).then(() => undefined);

  return {
    ready,
    onMomentChanged(frames) {
      lastFrames = Array.isArray(frames) ? frames : null;
      if (assumeOn) applyAssumption();
    },
    getCursor: () => cursorSec,
    setCursor: sec => setCursor(sec),
    destroy() {
      destroyed = true;
      stopPlayback();
      if (clickHandler) map.off('click', clickHandler);
      popup?.remove();
      container.replaceChildren();
    }
  };
}

export async function mountSatellite(map, container) {
  return createSatellite(map, container);
}
