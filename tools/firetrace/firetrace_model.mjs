// Pure logic for the FireTrace operations view (Garnet Fire). No DOM or map: tested with node --test.

export const RANGE_START_SEC = Date.UTC(2025, 7, 24, 0, 0) / 1000;
export const RANGE_END_SEC = Date.UTC(2025, 8, 12, 23, 59) / 1000;
export const PDT_OFFSET_SEC = 7 * 3600;
export const WEATHER_HOUR_SEC = 3600;
export const NEVER_SEC = 4e10;
export const HORIZONS = [6, 12, 24];
export const RECENT_HOURS = [6, 12, 24];
export const SPEEDS = [{label: '3 h/s', hoursPerSec: 3}, {label: '6 h/s', hoursPerSec: 6}, {label: '12 h/s', hoursPerSec: 12}, {label: '24 h/s', hoursPerSec: 24}];

// Incident milestones. `utc` is the source time; `assumption` marks a time that depends on an assumption.
export const EVENTS = [
  {id: 'wfigs', utc: '2025-08-24T07:10:00Z', label: 'Discovery (WFIGS)', detail: '24 Aug 07:10 UTC · WFIGS record', tone: 'ok'},
  {id: 'calfire', utc: '2025-08-24T14:13:00Z', label: 'Discovery (CAL FIRE)', detail: '24 Aug 14:13 · CAL FIRE record, time zone unconfirmed (treated as UTC)', tone: 'warn', assumption: true},
  {id: 'frp', utc: '2025-08-27T23:00:00Z', label: 'FRP overpass, 27 Aug', detail: '27 Aug 23:00 UTC (~16:00 PDT) · MODIS overpass with the day\'s highest FRP', tone: 'ok'},
  {id: 'pyro', utc: '2025-08-27T23:00:00Z', label: 'Pyrocumulus on camera', detail: '27 Aug ~16:00 PDT · under the PDT assumption; equals 23:00 UTC', tone: 'warn', assumption: true}
];

export class FiretraceError extends Error {}

// ---------- time ----------

export function parseUtc(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?Z$/.exec(String(value));
  if (!m) throw new FiretraceError('Invalid UTC date.');
  const ms = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
  if (!Number.isFinite(ms)) throw new FiretraceError('Invalid UTC date.');
  return ms / 1000;
}
export function isoZ(sec) {
  return new Date(sec * 1000).toISOString().slice(0, 19) + 'Z';
}
export function clampCursor(sec) {
  if (!Number.isFinite(sec)) throw new FiretraceError('Invalid cursor date.');
  return Math.min(RANGE_END_SEC, Math.max(RANGE_START_SEC, Math.round(sec / 60) * 60));
}
export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const pad = n => String(n).padStart(2, '0');
// zone: 'UTC' | 'PDT' (PDT = UTC−7, an assumption used only to relate times to the cameras). en-GB: 24-hour clock, day month year.
export function formatStamp(sec, zone = 'UTC') {
  const d = new Date((sec - (zone === 'PDT' ? PDT_OFFSET_SEC : 0)) * 1000);
  return {date: `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`, time: `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`, zone};
}
export function formatDuration(sec) {
  const abs = Math.abs(sec), h = Math.floor(abs / 3600), m = Math.round((abs % 3600) / 60);
  return h ? `${h} h ${pad(m)} min` : `${m} min`;
}
// en-GB: comma thousands separator, decimal point.
export function formatNumber(value, decimals = 0) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const [int, frac] = Math.abs(value).toFixed(decimals).split('.');
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return (value < 0 ? '−' : '') + grouped + (frac ? '.' + frac : '');
}
// Day and month of a formatted date ("24 Aug 2025" -> "24 Aug").
export const shortDate = date => date.split(' ').slice(0, 2).join(' ');

// Animation step: never goes past the end of the range.
export function advanceCursor(cursorSec, elapsedMs, hoursPerSec) {
  const next = cursorSec + (elapsedMs / 1000) * hoursPerSec * 3600;
  return next >= RANGE_END_SEC ? {cursor: RANGE_END_SEC, ended: true} : {cursor: next, ended: false};
}

// ---------- map filters (MapLibre expressions) ----------

// Cumulative area: every cell whose reconstructed arrival is <= cursor. Never includes the future.
export function cumulativeFilter(cursor) {
  return ['<=', ['get', 't'], cursor];
}
export function recentFilter(cursor, hours) {
  return ['all', ['<=', ['get', 't'], cursor], ['>', ['get', 't'], cursor - hours * 3600]];
}
// Cumulative area outline: edges between an already-arrived cell and a neighbour that has not arrived yet (or does not exist).
export function boundaryFilter(cursor) {
  return ['all', ['<=', ['get', 'a'], cursor], ['>', ['get', 'b'], cursor]];
}
export function recentBoundaryFilter(cursor, hours) {
  return ['all', ['<=', ['get', 'a'], cursor], ['>', ['get', 'b'], cursor], ['>', ['get', 'a'], cursor - hours * 3600]];
}
export function oldBoundaryFilter(cursor, hours) {
  return ['all', ['<=', ['get', 'a'], cursor - hours * 3600], ['>', ['get', 'b'], cursor]];
}

// ---------- FIRMS overpasses ----------

// Latest overpass with t <= cursor (list sorted by t). Null if there has been none yet.
export function currentOverpass(overpasses, cursor) {
  let lo = 0, hi = overpasses.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (overpasses[mid].t <= cursor) lo = mid + 1; else hi = mid; }
  if (lo === 0) return null;
  // If several overpasses share the same t, keep the one with the most detections.
  const t = overpasses[lo - 1].t;
  let best = overpasses[lo - 1];
  for (let i = lo - 2; i >= 0 && overpasses[i].t === t; i--) if (overpasses[i].detections > best.detections) best = overpasses[i];
  return best;
}
export function sortOverpasses(list) {
  return list.filter(o => Number.isFinite(o?.t)).slice().sort((a, b) => a.t - b.t);
}
export function passFilter(pass) {
  if (!pass) return ['==', ['get', 't'], -1];
  return ['all', ['==', ['get', 't'], pass.t], ['==', ['get', 'source'], pass.source]];
}
export function hotspotsOfPass(features, pass) {
  if (!pass) return [];
  return features.filter(f => f.properties.t === pass.t && f.properties.source === pass.source);
}

// ---------- reconstruction: cells, outline and area ----------

const METRES_PER_DEG_LAT = lat => 111132.95 - 559.82 * Math.cos(2 * lat * Math.PI / 180) + 1.175 * Math.cos(4 * lat * Math.PI / 180);
const METRES_PER_DEG_LON = lat => 111412.84 * Math.cos(lat * Math.PI / 180) - 93.5 * Math.cos(3 * lat * Math.PI / 180);
const ACRES_PER_M2 = 1 / 4046.8564224;
export function bboxOf(feature) {
  const ring = feature.geometry.coordinates[0];
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  for (const [x, y] of ring) { if (x < minx) minx = x; if (x > maxx) maxx = x; if (y < miny) miny = y; if (y > maxy) maxy = y; }
  return {minx, miny, maxx, maxy};
}
export function cellAcres(feature) {
  const b = bboxOf(feature), lat = (b.miny + b.maxy) / 2;
  return (b.maxx - b.minx) * METRES_PER_DEG_LON(lat) * (b.maxy - b.miny) * METRES_PER_DEG_LAT(lat) * ACRES_PER_M2;
}

// Cumulative area series by arrival time (reconstructed acres).
export function cumulativeAreaSeries(features) {
  const rows = [];
  for (const f of features) {
    const t = f?.properties?.t;
    if (Number.isFinite(t) && f.geometry?.type === 'Polygon') rows.push([t, cellAcres(f)]);
  }
  rows.sort((a, b) => a[0] - b[0]);
  const t = new Float64Array(rows.length), acres = new Float64Array(rows.length);
  let sum = 0;
  rows.forEach(([ti, a], i) => { sum += a; t[i] = ti; acres[i] = sum; });
  return {t, acres};
}
export function areaAt(series, cursor) {
  let lo = 0, hi = series.t.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (series.t[mid] <= cursor) lo = mid + 1; else hi = mid; }
  return lo === 0 ? 0 : series.acres[lo - 1];
}
export function areaBetween(series, fromExclusive, toInclusive) {
  return areaAt(series, toInclusive) - areaAt(series, fromExclusive);
}

// Outline edges: each exists as a border between [a, b) = [cell arrival, neighbour arrival).
// Cells are rectangles of a regular grid; if they are not, an empty list is returned and the UI falls back to the fill.
export function buildBoundaryEdges(features) {
  const cells = [];
  for (const f of features) {
    if (f?.geometry?.type !== 'Polygon' || !Number.isFinite(f?.properties?.t)) continue;
    cells.push({t: f.properties.t, ...bboxOf(f)});
  }
  if (!cells.length) return [];
  const dx = cells[0].maxx - cells[0].minx, dy = cells[0].maxy - cells[0].miny;
  if (!(dx > 0 && dy > 0)) return [];
  const x0 = Math.min(...cells.map(c => c.minx)), y0 = Math.min(...cells.map(c => c.miny));
  const index = new Map();
  for (const c of cells) {
    c.ix = Math.round((c.minx - x0) / dx); c.iy = Math.round((c.miny - y0) / dy);
    if (Math.abs(c.maxx - c.minx - dx) > dx * 0.02 || Math.abs(c.maxy - c.miny - dy) > dy * 0.02) return [];
    const key = c.ix * 100003 + c.iy;
    const prev = index.get(key);
    if (!prev || c.t < prev.t) index.set(key, c);
  }
  const edges = [];
  const add = (a, b, p, q) => edges.push({type: 'Feature', properties: {a, b}, geometry: {type: 'LineString', coordinates: [p, q]}});
  for (const c of index.values()) {
    const sides = [
      [1, 0, [c.maxx, c.miny], [c.maxx, c.maxy]], [-1, 0, [c.minx, c.miny], [c.minx, c.maxy]],
      [0, 1, [c.minx, c.maxy], [c.maxx, c.maxy]], [0, -1, [c.minx, c.miny], [c.maxx, c.miny]]
    ];
    for (const [ox, oy, p, q] of sides) {
      const n = index.get((c.ix + ox) * 100003 + (c.iy + oy));
      if (!n) add(c.t, NEVER_SEC, p, q);
      else if (n.t > c.t) add(c.t, n.t, p, q);
    }
  }
  return edges;
}

// ---------- weather ----------

// Model hour covering the cursor: timeUtc <= cursor < timeUtc + 1 h. Out of range returns null (no extrapolation).
export function weatherAt(hours, cursor) {
  let best = null;
  for (const h of hours) {
    const t = parseUtc(h.timeUtc);
    if (t <= cursor && cursor < t + WEATHER_HOUR_SEC && (!best || t > best.t)) best = {t, hour: h};
  }
  return best ? best.hour : null;
}
const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
export function compassPoint(deg) {
  return COMPASS[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16];
}

// ---------- cameras ----------

// The printed time carries no zone: it is read as PDT (assumption) and converted to UTC.
export function frameUtcSec(frame) {
  return parseUtc(frame.printedTime.replace(/\.\d+$/, '') + 'Z') + PDT_OFFSET_SEC;
}
export function nearestFrame(frames, cameraId, cursor) {
  let best = null;
  for (const frame of frames) {
    if (frame.cameraId !== cameraId) continue;
    const utc = frameUtcSec(frame), delta = utc - cursor;
    if (!best || Math.abs(delta) < Math.abs(best.deltaSec)) best = {frame, utcSec: utc, deltaSec: delta};
  }
  return best;
}
// Hypothetical cone: sector from the candidate position, printed azimuth X (assumption) and 65.1° FOV at zoom 1 scaled by focal length.
export const CAMERA_POSES = [
  {cameraId: 'delilah', pose: 'G2', lon: -119.1175, lat: 36.80417, yawDeg: 25.27, zoom: 1.0},
  {cameraId: 'buckrock', pose: 'G4', lon: -118.86067, lat: 36.73727, yawDeg: 333.87, zoom: 1.4}
];
export const FOV_ZOOM1_DEG = 65.1;
export function fovDeg(zoom) {
  return (2 * Math.atan(Math.tan(FOV_ZOOM1_DEG * Math.PI / 360) / zoom) * 180) / Math.PI;
}
export function destination([lon, lat], bearingDeg, metres) {
  const R = 6371008.8, d = metres / R, b = bearingDeg * Math.PI / 180, p1 = lat * Math.PI / 180, l1 = lon * Math.PI / 180;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b));
  const l2 = l1 + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
  return [((l2 * 180 / Math.PI + 540) % 360) - 180, p2 * 180 / Math.PI];
}
export function coneFeature(pose, radiusM = 20000, steps = 24) {
  const fov = fovDeg(pose.zoom), apex = [pose.lon, pose.lat], ring = [apex];
  for (let i = 0; i <= steps; i++) ring.push(destination(apex, pose.yawDeg - fov / 2 + (fov * i) / steps, radiusM));
  ring.push(apex);
  return {type: 'Feature', properties: {cameraId: pose.cameraId, pose: pose.pose, yawDeg: pose.yawDeg, fovDeg: Math.round(fov * 100) / 100, hypothetical: true}, geometry: {type: 'Polygon', coordinates: [ring]}};
}

// ---------- forecast: contract, validation and lifecycle ----------

export const FORECAST_ROLES = ['initial-extent', 'modeled-extent', 'reference-extent', 'overlap', 'overprediction', 'underprediction'];
// Accepted data classes. The three comparison geometries are model results against the reconstruction.
export const COMPARISON_ROLES = ['overlap', 'overprediction', 'underprediction'];
export const FORECAST_CLASSES = ['modeled', 'reconstructed'];
export const COMPARISON_CLASS = 'modeled-comparison';
export function classAllowed(role, dataClass) {
  return COMPARISON_ROLES.includes(role) ? dataClass === COMPARISON_CLASS || FORECAST_CLASSES.includes(dataClass) : FORECAST_CLASSES.includes(dataClass);
}
export class ForecastError extends FiretraceError {}

export function forecastTop(fc) {
  return fc?.properties || fc?.top?.properties || null;
}
// Checks the exact contract and that the response matches what was requested.
export function validateForecast(fc, request) {
  const top = forecastTop(fc);
  if (!fc || fc.type !== 'FeatureCollection' || !Array.isArray(fc.features) || !top) throw new ForecastError('The model response does not have the expected format.');
  if (top.mode !== 'retrospective-forecast') throw new ForecastError('The response is not a retrospective forecast.');
  if (top.timeUtc !== request.timeUtc || top.horizonHours !== request.horizonHours) throw new ForecastError('The response does not match the requested time and horizon.');
  if (!top.metrics || typeof top.metrics !== 'object') throw new ForecastError('The matching metrics are missing.');
  for (const f of fc.features) {
    const p = f?.properties;
    if (!p || !FORECAST_ROLES.includes(p.role)) throw new ForecastError('A forecast geometry has an unknown role.');
    if (!classAllowed(p.role, p.dataClass)) throw new ForecastError('A forecast geometry does not declare its data class.');
    if (!['Polygon', 'MultiPolygon'].includes(f.geometry?.type)) throw new ForecastError('A forecast geometry is not a polygon.');
  }
  return {features: fc.features, top};
}
export function forecastBody(cursorSec, horizonHours) {
  if (!HORIZONS.includes(horizonHours)) throw new ForecastError('Unsupported horizon.');
  return {timeUtc: isoZ(cursorSec), horizonHours};
}
export async function requestForecast(request, fetchFn, signal) {
  let response, data = null;
  try {
    response = await fetchFn('./api/forecast-reconstruction', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(request), signal});
  } catch (e) {
    if (e?.name === 'AbortError') throw e;
    throw new ForecastError('Could not contact the projection service.');
  }
  try { data = await response.json(); } catch { /* non-JSON body */ }
  if (!response.ok) throw new ForecastError(typeof data?.error === 'string' && data.error ? data.error : `The projection service responded with HTTP ${response.status}.`);
  return validateForecast(data, request);
}

// A single current forecast. Any change of cursor or horizon invalidates it and stale responses are discarded.
export function createForecastTracker() {
  let seq = 0, current = null;
  const drop = () => { if (!current) return false; current.controller?.abort(); current = null; seq++; return true; };
  return {
    get state() { return current; },
    begin(request, controller = null) { drop(); seq++; current = {seq, request, controller, status: 'loading', result: null, error: null}; return current; },
    invalidate: drop,
    // Returns true if the current cursor/horizon no longer matches the current forecast and it was discarded.
    sync(cursorSec, horizonHours) {
      if (!current) return false;
      return current.request.timeUtc !== isoZ(cursorSec) || current.request.horizonHours !== horizonHours ? drop() : false;
    },
    accept(ticket, result) {
      if (!current || ticket.seq !== current.seq) return false;
      current.status = 'ready'; current.result = result; return true;
    },
    fail(ticket, error) {
      if (!current || ticket.seq !== current.seq) return false;
      current.status = 'error'; current.error = error; return true;
    }
  };
}

// ---------- framing ----------

export function featureBounds(features) {
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  const walk = c => { if (typeof c[0] === 'number') { if (c[0] < minx) minx = c[0]; if (c[0] > maxx) maxx = c[0]; if (c[1] < miny) miny = c[1]; if (c[1] > maxy) maxy = c[1]; } else c.forEach(walk); };
  for (const f of features) if (f?.geometry?.coordinates) walk(f.geometry.coordinates);
  return minx <= maxx ? {minx, miny, maxx, maxy} : null;
}
// ---------- provenance summary ----------

export function areaComparisons(summary) {
  return (summary?.validationAgainstReportedAcres || []).map(c => ({
    atUtc: isoZ(Date.parse(c.at) / 1000), reportedAcres: c.reportedAcres, reconstructedAcres: c.reconstructedAcres, ratio: c.ratio, source: c.source
  }));
}
