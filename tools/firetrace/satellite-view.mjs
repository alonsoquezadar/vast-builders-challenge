// Satellite and weather layers for the Garnet Fire in the FireTrace viewer.
// Contract with incident.js:
//   const satellite = await mountSatellite(map, document.getElementById('satellite-panel'));
//   satellite.onMomentChanged(pair.frames);          // from render()
// `mountSatellite` is async only by contract: it builds the panel and resolves immediately; the data
// and map layers load afterwards (controller.ready). `createSatellite` is the same function,
// synchronous, in case the root prefers to receive the controller without await.
// The layers and the time cursor do not depend on the camera pairs, except with the PDT assumption option.

export const RANGE_START_SEC = Date.UTC(2025, 7, 24, 0, 0) / 1000;
export const RANGE_END_SEC = Date.UTC(2025, 8, 12, 23, 59) / 1000;
export const CURSOR_STEP_SEC = 60;
// Arbitrary initial cursor (start of 27 Aug UTC); it does not correspond to any camera time.
export const DEFAULT_CURSOR_SEC = Date.UTC(2025, 7, 27, 0, 0) / 1000;
export const HOTSPOT_WINDOW_HOURS = 12;
export const WEATHER_MAX_GAP_SEC = 3600;
export const PDT_OFFSET_HOURS = 7;
export const PERIMETER_PUBLISHED_FALLBACK = '2025-12-19';

export const LAYERS = {
  hotspots: {label: 'OBSERVED thermal hotspots (NASA FIRMS)', expected: 'observed', defaultOn: true},
  arrival: {label: 'RECONSTRUCTED arrival (200 m cells)', expected: 'reconstructed', defaultOn: false},
  perimeter: {label: 'FINAL perimeter (WFIGS)', expected: 'observed', defaultOn: false},
  weather: {label: 'Historical weather (model)', expected: 'historical-model'},
  summary: {label: 'Summary', expected: null}
};
const MAP_LAYER_NAMES = ['arrival', 'perimeter', 'hotspots']; // bottom to top
const UI_ORDER = ['hotspots', 'arrival', 'perimeter'];

export class SatelliteError extends Error {}

// ---------- time ----------

export function clampCursor(sec) {
  if (!Number.isFinite(sec)) throw new SatelliteError('Invalid cursor date.');
  const snapped = Math.round((sec - RANGE_START_SEC) / CURSOR_STEP_SEC) * CURSOR_STEP_SEC + RANGE_START_SEC;
  return Math.min(RANGE_END_SEC, Math.max(RANGE_START_SEC, snapped));
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// en-GB: day month year, 24-hour clock.
export function formatUtc(sec) {
  const iso = new Date(sec * 1000).toISOString();
  return `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)} ${iso.slice(11, 16)} UTC`;
}

// Day and month only (en-GB), from an ISO date or timestamp string.
export function formatDayMonth(value) {
  return `${Number(String(value).slice(8, 10))} ${MONTHS[Number(String(value).slice(5, 7)) - 1]}`;
}

// Formats an ISO timestamp from the data for display; anything unparseable is shown unchanged.
export function formatTimestamp(value) {
  const sec = Date.parse(value) / 1000;
  return Number.isFinite(sec) ? formatUtc(sec) : String(value);
}

// en-GB: comma as the thousands separator.
export function formatCount(n) {
  return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// Hotspot window: [cursor − 12 h, cursor]; never includes detections after the cursor.
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
// First index whose value does not satisfy `before(value)`.
function partition(sorted, before) {
  let lo = 0, hi = sorted.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (before(sorted[mid])) lo = mid + 1; else hi = mid; }
  return lo;
}
// Elements with lo <= t <= hi.
export function countInRange(sorted, lo, hi) {
  if (hi < lo) return 0;
  return partition(sorted, v => v <= hi) - partition(sorted, v => v < lo);
}

// ---------- PDT assumption to relate the cameras' printed time ----------

export function parsePrintedClockAsUtcSeconds(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?$/.exec(String(value));
  if (!m) throw new SatelliteError('Invalid printed time.');
  const [y, mo, d, h, mi, s] = m.slice(1).map(Number);
  const date = new Date(Date.UTC(y, mo - 1, d, h, mi, s));
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== mo - 1 || date.getUTCDate() !== d || h > 23 || mi > 59 || s > 59) throw new SatelliteError('Invalid printed time.');
  return date.getTime() / 1000;
}

// The cameras' time zone is not confirmed: this is a HYPOTHESIS, not a verified conversion.
export function assumedUtcFromPrinted(printedTime, offsetHours = PDT_OFFSET_HOURS) {
  return parsePrintedClockAsUtcSeconds(printedTime) + offsetHours * 3600;
}

export function cursorFromFrames(frames) {
  const first = Array.isArray(frames) ? frames[0] : null;
  if (!first || typeof first.printedTime !== 'string') return {ok: false, reason: 'sin-fotogramas'};
  let assumedSec;
  try { assumedSec = assumedUtcFromPrinted(first.printedTime); } catch { return {ok: false, reason: 'hora-invalida'}; }
  const printed = `${formatDayMonth(first.printedTime)} ${first.printedTime.slice(0, 4)} ${first.printedTime.slice(11, 19)}`;
  if (assumedSec < RANGE_START_SEC - CURSOR_STEP_SEC / 2 || assumedSec > RANGE_END_SEC + CURSOR_STEP_SEC / 2) return {ok: false, reason: 'fuera-de-rango', assumedSec, printed};
  return {ok: true, sec: clampCursor(assumedSec), assumedSec, printed};
}

export function assumptionNote(result) {
  if (!result) return 'No frames are selected yet; it will apply once a moment is chosen.';
  if (result.ok) return `ASSUMPTION, not verified: printed time of the first frame (${result.printed}, time zone unconfirmed) + ${PDT_OFFSET_HOURS} h = ${formatUtc(result.sec)}. It does not claim synchronisation between cameras or with the satellites.`;
  if (result.reason === 'fuera-de-rango') return `The PDT assumption would give ${formatUtc(result.assumedSec)}, outside the 24 Aug–12 Sep range. Cursor unchanged.`;
  if (result.reason === 'hora-invalida') return 'The printed time of the first frame could not be interpreted. Cursor unchanged.';
  return 'No frames are selected yet; it will apply once a moment is chosen.';
}

// ---------- weather ----------

const CARDINALS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
export function cardinal(deg) {
  return CARDINALS[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16];
}

export function prepareWeather(raw) {
  if (!Array.isArray(raw?.hours) || !raw.hours.length) throw new SatelliteError('Weather data in an unexpected format.');
  const rows = [];
  for (const h of raw.hours) {
    const sec = Date.parse(h?.timeUtc) / 1000;
    if (Number.isFinite(sec)) rows.push({...h, sec});
  }
  if (!rows.length) throw new SatelliteError('Weather data in an unexpected format.');
  return rows.sort((a, b) => a.sec - b.sec);
}

// Reanalysis hour closest to the cursor and within 1 h; otherwise returns null (never the last row).
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
  if (!match) return ['No historical-model hour within 1 h of the cursor.'];
  const h = match.hour;
  const num = (v, unit, digits = 0) => (Number.isFinite(v) ? `${Number(v).toFixed(digits)}${unit === '%' || unit === '°C' ? '' : ' '}${unit}` : 'no data');
  const wind = Number.isFinite(h.windFromDeg) ? `from ${Math.round(h.windFromDeg)}° (${cardinal(h.windFromDeg)}) at ${num(h.windSpeedMps, 'm/s', 1)}` : 'no data';
  const lines = [
    `Historical-model hour: ${formatUtc(h.sec)}${match.gapSec ? ` (${Math.round(match.gapSec / 60)} min from the cursor)` : ''}`,
    `Wind at 10 m: ${wind}`,
    `Relative humidity: ${num(h.rhPct, '%')}`,
    `Temperature: ${num(h.tempC, '°C', 1)}`
  ];
  if (Number.isFinite(h.gustMps)) lines.splice(2, 0, `Gusts: ${num(h.gustMps, 'm/s', 1)}`);
  if (point && Number.isFinite(point.lat) && Number.isFinite(point.lon)) lines.push(`Historical-model point: ${point.lat}, ${point.lon}${Number.isFinite(point.elevationM) ? ` · ${Math.round(point.elevationM)} m` : ''}`);
  return lines;
}

// ---------- layer loading ----------

export function evidenceWarnings(summary) {
  const comparisons = summary?.validationAgainstReportedAcres || [];
  const areas = comparisons.map(row => {
    return `${formatDayMonth(row.at)}: reconstructed area ×${row.ratio.toFixed(2)} relative to the reported area`;
  });
  return [
    areas.length ? `Area overestimate: ${areas.join('; ')}. Do not use as an official area; the 31 Aug comparison comes from local press.` : 'Area comparison not yet available; the reconstruction is not an official area.',
    `Unresolved timeline: WFIGS records discovery on 24 Aug at 07:10 UTC; the first FIRMS detection in the package is ${summary?.firstDetectionUtc ? formatTimestamp(summary.firstDetectionUtc) : 'not yet available'}. The CAL FIRE incident page gives 14:13 on the same day (time zone not verified here). FIRMS is later than WFIGS in this package. None of these times establishes the exact ignition.`
  ];
}

export function validateLayer(name, data) {
  const bad = () => new SatelliteError(`Data for ‘${LAYERS[name]?.label || name}’ in an unexpected format.`);
  if (!LAYERS[name] || !data || typeof data !== 'object') throw bad();
  if (name === 'weather') { prepareWeather(data); return; }
  if (name === 'summary') { if (!data.counts || typeof data.counts !== 'object') throw bad(); return; }
  if (data.type !== 'FeatureCollection' || !Array.isArray(data.features) || (name === 'perimeter' && !data.features.length)) throw bad();
}

export async function fetchLayer(name, fetchFn) {
  let response, data = null;
  try { response = await fetchFn(`./api/satellite?layer=${encodeURIComponent(name)}`); } catch { throw new SatelliteError('Could not reach the satellite data service.'); }
  try { data = await response.json(); } catch { /* non-JSON body */ }
  if (!response.ok) throw new SatelliteError(typeof data?.error === 'string' && data.error && data.error.length < 200 ? data.error : `The service responded with HTTP ${response.status}.`);
  validateLayer(name, data);
  return data;
}

// State per source: idle | loading | ready | error. A load in progress is shared; an error allows a retry.
export function createLayerStore(fetchFn, onChange = () => {}) {
  const entries = {};
  for (const name of Object.keys(LAYERS)) entries[name] = {state: 'idle', data: null, error: null, promise: null};
  return {
    get: name => entries[name],
    load(name) {
      const entry = entries[name];
      if (!entry) return Promise.reject(new SatelliteError('Unknown layer.'));
      if (entry.state === 'ready') return Promise.resolve(entry.data);
      if (entry.state === 'loading') return entry.promise;
      entry.state = 'loading'; entry.error = null; onChange(name);
      entry.promise = fetchLayer(name, fetchFn).then(data => {
        entry.state = 'ready'; entry.data = data; onChange(name); return data;
      }, error => {
        entry.state = 'error'; entry.error = error instanceof SatelliteError ? error.message : 'Unexpected error while loading the layer.'; onChange(name); throw error;
      });
      return entry.promise;
    }
  };
}

export function provenanceText(data) {
  const p = data?._provenance;
  if (!p || typeof p !== 'object') return 'provenance not declared';
  const parts = [];
  if (typeof p.dataClass === 'string') parts.push(p.dataClass);
  const hashKey = Object.keys(p).find(k => /hash|sha/i.test(k) && typeof p[k] === 'string');
  if (hashKey) parts.push(`sha256 ${p[hashKey].slice(0, 12)}…`);
  return parts.length ? parts.join(' · ') : 'provenance not declared';
}

export function classificationWarning(name, data) {
  const expected = LAYERS[name]?.expected;
  return expected && typeof data?.status === 'string' && data.status !== expected ? `unexpected classification ‘${data.status}’` : '';
}

// ---------- map layers ----------

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
    'OBSERVED thermal hotspot',
    `Date: ${props.acquiredUtc ? formatTimestamp(props.acquiredUtc) : 'no data'}`,
    `Source: ${props.source ?? 'no data'}${props.satellite ? ` · ${props.satellite}` : ''}`,
    `Confidence: ${props.confidence ?? 'no data'} · FRP ${Number.isFinite(props.frpMW) ? props.frpMW + ' MW' : 'no data'}`,
    `Centre of a pixel of ~${props.pixelM ?? '?'} m: does not measure front, area or speed.`
  ];
  if (name === 'arrival') return [
    'RECONSTRUCTED cell (200 m), not an observed front',
    `Estimated arrival time: ${props.arrivalUtc ? formatTimestamp(props.arrivalUtc) : 'no data'}`,
    `Type: ${props.kind === 'interpolated' ? 'interpolated (median of 6 neighbouring supported cells)' : props.kind === 'observed-support' ? 'first VIIRS detection within ≤ 400 m' : props.kind ?? 'no data'}`,
    'Source: FIRMS detections; clipped by the final perimeter.'
  ];
  return [
    'FINAL WFIGS perimeter',
    `Published polygon: ${props.polygonDateTime ? formatTimestamp(props.polygonDateTime) : 'no data'}`,
    `Method: ${props.mapMethod ?? 'no data'}`,
    'Final state of the fire; not the perimeter of an intermediate date.'
  ];
}

// ---------- panel ----------

const LEGEND = [
  ['satellite-chip-hotspot', 'Observed thermal hotspot; the radius grows with FRP'],
  ['satellite-chip-arrival', 'Reconstructed cell with detection support (≤ 400 m)'],
  ['satellite-chip-interpolated', 'Interpolated reconstructed cell'],
  ['satellite-chip-perimeter', 'FINAL WFIGS perimeter']
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
  const panel = el(doc, 'section', {class: 'satellite-panel', 'aria-label': 'Satellite and weather layer'});
  panel.append(el(doc, 'h3', {class: 'satellite-title'}, 'Satellite and weather'));
  panel.append(el(doc, 'p', {class: 'satellite-scope'}, 'Thermal detections from NASA FIRMS (24 Aug–12 Sep 2025) and a historical weather model. Hotspots are thermal anomalies at the centre of a pixel: they do not measure front, area or speed.'));

  const fieldset = el(doc, 'fieldset', {class: 'satellite-layers'}, el(doc, 'legend', {}, 'Layers'));
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
  const badge = el(doc, 'span', {class: 'satellite-badge', hidden: ''}, 'PDT ASSUMPTION');
  const playButton = el(doc, 'button', {type: 'button', class: 'satellite-play'}, '▶ Play');
  const assumeInput = el(doc, 'input', {type: 'checkbox', id: 'satellite-assume-pdt'});
  const assumeNote = el(doc, 'p', {class: 'satellite-assume-note', role: 'status', 'aria-live': 'polite'});
  panel.append(el(doc, 'div', {class: 'satellite-time'},
    el(doc, 'label', {for: 'satellite-cursor', class: 'satellite-time-label'}, 'Time cursor (UTC)'),
    el(doc, 'div', {class: 'satellite-time-row'}, slider),
    el(doc, 'div', {class: 'satellite-time-row'}, dateOut, badge, playButton),
    el(doc, 'label', {class: 'satellite-assume', for: 'satellite-assume-pdt'}, assumeInput, el(doc, 'span', {}, 'Assume PDT (UTC−7) to relate camera times')),
    assumeNote));

  const countersList = el(doc, 'ul', {class: 'satellite-counters'});
  const weatherList = el(doc, 'ul', {class: 'satellite-weather-list'});
  const weatherHead = el(doc, 'p', {class: 'satellite-weather-note'}, 'MODELLED weather (Open-Meteo Historical · Best Match), a single point; not an observed station.');
  const legendList = el(doc, 'ul', {class: 'satellite-legend-list'});
  for (const [cls, text] of LEGEND) legendList.append(el(doc, 'li', {}, el(doc, 'i', {class: `satellite-chip ${cls}`}), text));
  const dependency = el(doc, 'p', {class: 'satellite-dependency'});
  const quality = el(doc, 'ul', {id: 'satellite-quality', class: 'satellite-counters'});
  panel.append(
    el(doc, 'div', {class: 'satellite-block'}, el(doc, 'h4', {}, 'At the cursor'), countersList),
    el(doc, 'div', {class: 'satellite-block'}, el(doc, 'h4', {}, 'Weather at the cursor'), weatherHead, weatherList),
    el(doc, 'div', {class: 'satellite-block'}, el(doc, 'h4', {}, 'Legend'), legendList),
    dependency,
    el(doc, 'div', {class: 'satellite-block'}, el(doc, 'h4', {}, 'Verified limitations of the data'), quality));
  container.replaceChildren(panel);

  const setList = (list, lines) => list.replaceChildren(...lines.map(l => el(doc, 'li', {}, l)));

  function perimeterDate() {
    const props = store.get('perimeter').data?.features?.[0]?.properties;
    return typeof props?.polygonDateTime === 'string' ? props.polygonDateTime.slice(0, 10) : PERIMETER_PUBLISHED_FALLBACK;
  }

  function renderStatic() {
    setList(quality, evidenceWarnings(summary));
    refs.perimeter.text.textContent = `${LAYERS.perimeter.label}, published ${formatDayMonth(perimeterDate())} ${perimeterDate().slice(0, 4)}`;
    const c = summary?.counts;
    const scope = Number.isFinite(c?.arrivalCells) && Number.isFinite(c?.cellsWithDetectionSupport) ? `${formatCount(c.arrivalCells)} cells of 200 m, ${formatCount(c.cellsWithDetectionSupport)} with a nearby detection (≤ 400 m) and ${formatCount(c.arrivalCells - c.cellsWithDetectionSupport)} interpolated; ` : '200 m cells with a nearby detection or interpolated; ';
    dependency.textContent = `Retrospective reconstruction (${scope}all RECONSTRUCTED, not an observed front). It depends on the FINAL perimeter published on ${formatDayMonth(perimeterDate())} ${perimeterDate().slice(0, 4)}: it is clipped by it and does not represent the state of any intermediate day. No perimeter, area or speed is inferred.`;
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
    status.textContent = entry.state === 'loading' ? 'Loading…'
      : entry.state === 'error' ? `Error: ${entry.error} Tick the checkbox to retry.`
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
    if (!refs.hotspots.input.checked || !times.hotspots) lines.push(`Observed hotspots (${HOTSPOT_WINDOW_HOURS} h window): ${store.get('hotspots').state === 'ready' ? 'layer switched off' : '—'}`);
    else lines.push(`Observed thermal hotspots in the previous ${HOTSPOT_WINDOW_HOURS} h: ${formatCount(countInRange(times.hotspots, fromSec, toSec))} of ${formatCount(times.hotspots.length)} in total`);
    if (!refs.arrival.input.checked || !times.arrivalSupported) lines.push(`Reconstructed cells up to the cursor: ${store.get('arrival').state === 'ready' ? 'layer switched off' : 'layer switched off or not loaded'}`);
    else {
      const a = countInRange(times.arrivalSupported, -Infinity, cursorSec), b = countInRange(times.arrivalInterpolated, -Infinity, cursorSec);
      lines.push(`RECONSTRUCTED cells up to the cursor: ${formatCount(a + b)} of ${formatCount(times.arrivalSupported.length + times.arrivalInterpolated.length)} (${formatCount(a)} with detection support, ${formatCount(b)} interpolated)`);
    }
    setList(countersList, lines);
    if (!weatherRows) setList(weatherList, [store.get('weather').state === 'error' ? `Weather unavailable: ${store.get('weather').error}` : 'Loading weather…']);
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

  // --- layers ---
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
      if (entryNow.state !== 'error') { refs[name].status.textContent = 'Error: the layer could not be added to the map.'; refs[name].status.classList.add('satellite-error'); refs[name].input.checked = false; refs[name].input.disabled = false; }
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

  // --- time ---
  slider.addEventListener('input', () => { stopPlayback(); cursorSec = clampCursor(Number(slider.value)); cursorFromAssumption = false; scheduleRender(); });
  assumeInput.addEventListener('change', () => {
    assumeOn = assumeInput.checked;
    if (assumeOn) applyAssumption(); else { assumeNote.textContent = ''; cursorFromAssumption = false; renderCursor(); }
  });
  function stopPlayback() {
    if (playTimer === null) return;
    clearInterval(playTimer); playTimer = null;
    playButton.textContent = '▶ Play';
  }
  playButton.addEventListener('click', () => {
    if (playTimer !== null) return stopPlayback();
    if (cursorSec >= RANGE_END_SEC) cursorSec = RANGE_START_SEC;
    playButton.textContent = '⏸ Pause';
    playTimer = setInterval(() => {
      cursorFromAssumption = false;
      cursorSec = clampCursor(cursorSec + 3600);
      scheduleRender();
      if (cursorSec >= RANGE_END_SEC) stopPlayback();
    }, 150);
  });

  // --- map ---
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
