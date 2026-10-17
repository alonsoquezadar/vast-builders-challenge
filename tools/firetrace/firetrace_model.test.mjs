import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import * as M from './firetrace_model.mjs';

const read = name => JSON.parse(readFileSync(new URL('./evidence/garnet/satellite/' + name, import.meta.url)));
const arrival = read('arrival-reconstructed.geojson').features;
const hotspots = read('hotspots.geojson').features;
const overpasses = M.sortOverpasses(read('overpasses.json').overpasses);
const daily = read('daily-extent-reconstructed.geojson').features;
const weather = read('weather-hourly.json');
const utc = s => M.parseUtc(s);

// Evalúa el subconjunto de expresiones que usan los filtros del mapa.
function evaluate(expr, props) {
  if (!Array.isArray(expr)) return expr;
  const [op, ...args] = expr;
  if (op === 'get') return props[args[0]];
  const v = args.map(a => evaluate(a, props));
  switch (op) {
    case '<=': return v[0] <= v[1];
    case '>': return v[0] > v[1];
    case '==': return v[0] === v[1];
    case 'all': return v.every(Boolean);
    default: throw Error('operador no soportado ' + op);
  }
}

test('el área acumulada nunca incluye celdas posteriores al cursor', () => {
  for (const iso of ['2025-08-24T12:00:00Z', '2025-08-27T20:38:00Z', '2025-09-01T00:00:00Z']) {
    const cursor = utc(iso), filter = M.cumulativeFilter(cursor);
    const shown = arrival.filter(f => evaluate(filter, f.properties));
    assert.ok(shown.length > 0);
    assert.ok(shown.every(f => f.properties.t <= cursor));
    assert.equal(shown.length, arrival.filter(f => f.properties.t <= cursor).length);
  }
  assert.equal(arrival.filter(f => evaluate(M.cumulativeFilter(utc('2025-08-24T00:00:00Z')), f.properties)).length, 0);
});

test('la franja reciente solo contiene celdas de las últimas X horas y es subconjunto del acumulado', () => {
  const cursor = utc('2025-08-27T20:00:00Z');
  for (const hours of M.RECENT_HOURS) {
    const recent = arrival.filter(f => evaluate(M.recentFilter(cursor, hours), f.properties));
    assert.ok(recent.every(f => f.properties.t <= cursor && f.properties.t > cursor - hours * 3600));
  }
  const six = arrival.filter(f => evaluate(M.recentFilter(cursor, 6), f.properties)).length;
  const day = arrival.filter(f => evaluate(M.recentFilter(cursor, 24), f.properties)).length;
  assert.ok(six <= day);
});

test('FIRMS muestra solo la última pasada <= cursor, con su t y source exactos', () => {
  const cursor = utc('2025-08-27T20:40:00Z');
  const pass = M.currentOverpass(overpasses, cursor);
  assert.ok(pass.t <= cursor);
  assert.ok(!overpasses.some(o => o.t > pass.t && o.t <= cursor));
  const filter = M.passFilter(pass);
  const shown = hotspots.filter(f => evaluate(filter, f.properties));
  assert.ok(shown.length > 0);
  assert.ok(shown.every(f => f.properties.t === pass.t && f.properties.source === pass.source && f.properties.t <= cursor));
  assert.equal(shown.length, M.hotspotsOfPass(hotspots, pass).length);
  assert.equal(shown.length, pass.detections);
});

test('antes de la primera pasada no hay pasada actual ni puntos; los puntos futuros nunca cuentan', () => {
  const first = overpasses[0];
  assert.equal(M.currentOverpass(overpasses, first.t - 1), null);
  assert.equal(hotspots.filter(f => evaluate(M.passFilter(null), f.properties)).length, 0);
  assert.equal(M.currentOverpass(overpasses, first.t).t, first.t);
  const mid = utc('2025-08-30T00:00:00Z');
  const pass = M.currentOverpass(overpasses, mid);
  assert.ok(hotspots.filter(f => evaluate(M.passFilter(pass), f.properties)).every(f => f.properties.t <= mid));
});

test('dos pasadas con el mismo t se distinguen por source', () => {
  const a = {t: 100, source: 'A', detections: 2}, b = {t: 100, source: 'B', detections: 5};
  assert.equal(M.currentOverpass([a, b], 100).source, 'B');
  const pts = [{properties: {t: 100, source: 'A'}}, {properties: {t: 100, source: 'B'}}];
  assert.equal(M.hotspotsOfPass(pts, b).length, 1);
});

test('el área reconstruida concuerda con los acres diarios publicados y es monótona', () => {
  const series = M.cumulativeAreaSeries(arrival);
  assert.equal(series.t.length, arrival.length);
  for (let i = 1; i < series.acres.length; i++) assert.ok(series.acres[i] >= series.acres[i - 1]);
  for (const day of daily.slice(0, 8)) {
    const end = Date.parse(day.properties.endPdt) / 1000;
    const acres = M.areaAt(series, end);
    assert.ok(Math.abs(acres / day.properties.reconstructedAcres - 1) < 0.01, `${day.properties.localDate}: ${acres} vs ${day.properties.reconstructedAcres}`);
  }
  assert.equal(M.areaAt(series, utc('2025-08-24T00:00:00Z')), 0);
  const cursor = utc('2025-08-27T00:00:00Z');
  assert.ok(Math.abs(M.areaBetween(series, cursor - 6 * 3600, cursor) + M.areaAt(series, cursor - 6 * 3600) - M.areaAt(series, cursor)) < 1e-6);
});

test('el contorno acumulado solo aparece en el límite entre llegada y no llegada', () => {
  const edges = M.buildBoundaryEdges(arrival);
  assert.ok(edges.length > 1000);
  const cursor = utc('2025-08-27T20:00:00Z');
  const visible = edges.filter(e => evaluate(M.boundaryFilter(cursor), e.properties));
  assert.ok(visible.length > 0 && visible.every(e => e.properties.a <= cursor && e.properties.b > cursor));
  assert.equal(edges.filter(e => evaluate(M.boundaryFilter(utc('2025-08-24T00:00:00Z')), e.properties)).length, 0);
  const recent = edges.filter(e => evaluate(M.recentBoundaryFilter(cursor, 12), e.properties));
  const old = edges.filter(e => evaluate(M.oldBoundaryFilter(cursor, 12), e.properties));
  assert.equal(recent.length + old.length, visible.length);
});

test('contorno de una rejilla pequeña: solo aristas exteriores y frontera temporal', () => {
  const cell = (ix, t) => ({type: 'Feature', properties: {t}, geometry: {type: 'Polygon', coordinates: [[[ix, 0], [ix + 1, 0], [ix + 1, 1], [ix, 1], [ix, 0]]]}});
  const edges = M.buildBoundaryEdges([cell(0, 10), cell(1, 20)]);
  const at = c => edges.filter(e => e.properties.a <= c && e.properties.b > c).length;
  assert.equal(at(5), 0);
  assert.equal(at(15), 4);
  assert.equal(at(25), 6);
});

test('el tiempo se formatea en UTC o PDT sin confundir la zona', () => {
  const t = utc('2025-08-27T23:00:00Z');
  assert.deepEqual(M.formatStamp(t, 'UTC'), {date: '27 ago 2025', time: '23:00', zone: 'UTC'});
  assert.deepEqual(M.formatStamp(t, 'PDT'), {date: '27 ago 2025', time: '16:00', zone: 'PDT'});
  assert.equal(M.isoZ(t), '2025-08-27T23:00:00Z');
  assert.equal(M.formatNumber(null), '—');
  assert.equal(M.formatNumber(12345.6, 0), '12.346');
  assert.equal(M.formatNumber(0.456, 2), '0,46');
});

test('la animación avanza a la velocidad pedida y se detiene en el final del rango', () => {
  assert.equal(M.advanceCursor(0, 1000, 6).cursor, 6 * 3600);
  const end = M.advanceCursor(M.RANGE_END_SEC - 10, 5000, 24);
  assert.deepEqual(end, {cursor: M.RANGE_END_SEC, ended: true});
  assert.equal(M.clampCursor(0), M.RANGE_START_SEC);
  assert.equal(M.clampCursor(1e12), M.RANGE_END_SEC);
});

test('la meteorología usa la hora que cubre el cursor y no extrapola fuera de rango', () => {
  const t = utc('2025-08-27T20:40:00Z');
  const hour = M.weatherAt(weather.hours, t);
  assert.equal(hour.timeUtc, '2025-08-27T20:00:00Z');
  assert.equal(M.weatherAt(weather.hours, utc('2025-08-24T00:00:00Z')).timeUtc, '2025-08-24T00:00:00Z');
  assert.equal(M.weatherAt(weather.hours, utc('2025-08-23T23:59:00Z')), null);
  const last = weather.hours.at(-1);
  assert.equal(M.weatherAt(weather.hours, utc(last.timeUtc) + 3600), null);
  assert.equal(M.compassPoint(221), 'SO');
  assert.equal(M.compassPoint(359), 'N');
});

test('la cámara más cercana usa la hora impresa como PDT y informa la diferencia con el cursor', () => {
  const frames = [
    {id: 'a', cameraId: 'delilah', printedTime: '2025-08-27T16:16:57.53'},
    {id: 'b', cameraId: 'delilah', printedTime: '2025-08-27T18:13:32.25'},
    {id: 'c', cameraId: 'buckrock', printedTime: '2025-08-27T16:26:41.00'}
  ];
  assert.equal(M.frameUtcSec(frames[0]), utc('2025-08-27T23:16:57Z'));
  const near = M.nearestFrame(frames, 'delilah', utc('2025-08-28T01:00:00Z'));
  assert.equal(near.frame.id, 'b');
  assert.equal(Math.round(near.deltaSec), 13 * 60 + 32);
  assert.equal(M.nearestFrame(frames, 'buckrock', utc('2025-08-24T00:00:00Z')).frame.id, 'c');
  assert.equal(M.nearestFrame(frames, 'otra', 0), null);
});

test('los conos son hipótesis con apertura por focal y apuntan al azimut declarado', () => {
  assert.ok(Math.abs(M.fovDeg(1) - 65.1) < 1e-9);
  assert.ok(Math.abs(M.fovDeg(1.4) - 49.02) < 0.1);
  const cone = M.coneFeature(M.CAMERA_POSES[0]);
  assert.equal(cone.properties.hypothetical, true);
  const ring = cone.geometry.coordinates[0];
  assert.deepEqual(ring[0], ring.at(-1));
  const mid = ring[Math.floor(ring.length / 2)];
  const bearing = (Math.atan2((mid[0] - ring[0][0]) * Math.cos(36.8 * Math.PI / 180), mid[1] - ring[0][1]) * 180 / Math.PI + 360) % 360;
  assert.ok(Math.abs(bearing - 25.27) < 2, String(bearing));
});

// ---------- pronóstico ----------

const request = {timeUtc: '2025-08-27T20:00:00Z', horizonHours: 12};
const square = [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]];
const forecast = overrides => ({type: 'FeatureCollection', features: [{type: 'Feature', geometry: {type: 'Polygon', coordinates: square}, properties: {role: 'modeled-extent', dataClass: 'modeled'}}],
  properties: {mode: 'retrospective-forecast', validated: false, timeUtc: request.timeUtc, validUtc: '2025-08-28T08:00:00Z', horizonHours: 12, referenceAvailable: true, metrics: {iou: .5, growthIou: null}, ...overrides}});

// Forma de la respuesta real de /api/forecast-reconstruction (geometrías reducidas).
const realForecast = () => {
  const poly = {type: 'Polygon', coordinates: square}, multi = {type: 'MultiPolygon', coordinates: [square]};
  const feature = (role, dataClass, geometry) => ({type: 'Feature', geometry, properties: {role, dataClass}});
  return {type: 'FeatureCollection', features: [
    feature('initial-extent', 'reconstructed', multi), feature('modeled-extent', 'modeled', poly), feature('reference-extent', 'reconstructed', multi),
    feature('overlap', 'modeled-comparison', multi), feature('overprediction', 'modeled-comparison', multi), feature('underprediction', 'modeled-comparison', multi)],
  properties: {mode: 'retrospective-forecast', validated: false, label: 'PRONÓSTICO RETROSPECTIVO · NO VALIDADO', timeUtc: request.timeUtc, validUtc: '2025-08-28T08:00:00Z', horizonHours: 12,
    referenceAvailable: true, domainBoundaryReached: false, metrics: {iou: 0.2873, growthIou: 0.046, intersectionHa: 7528, overpredictionHa: 18676, underpredictionHa: 0, predictedHa: 26204, referenceHa: 7528, initialHa: 6628},
    weather: {windFromDeg: 253, hourly: []}, assumptions: {}, limitations: [], provenance: {}}};
};
test('la respuesta real con comparación modeled-comparison se acepta; una clase desconocida se rechaza', () => {
  const ok = M.validateForecast(realForecast(), request);
  assert.equal(ok.features.length, 6);
  const wrongRole = realForecast(); wrongRole.features[1].properties.dataClass = 'modeled-comparison';
  assert.throws(() => M.validateForecast(wrongRole, request), M.ForecastError);
  const unknown = realForecast(); unknown.features[3].properties.dataClass = 'observed';
  assert.throws(() => M.validateForecast(unknown, request), M.ForecastError);
  assert.equal(M.classAllowed('overlap', 'modeled-comparison'), true);
  assert.equal(M.classAllowed('initial-extent', 'modeled-comparison'), false);
});

test('el cuerpo del pronóstico usa ISO con Z y solo horizontes 6, 12 o 24', () => {
  assert.deepEqual(M.forecastBody(utc('2025-08-27T20:00:00Z'), 24), {timeUtc: '2025-08-27T20:00:00Z', horizonHours: 24});
  assert.throws(() => M.forecastBody(0, 7), M.ForecastError);
});

test('validateForecast acepta el contrato y rechaza roles, clases o solicitudes distintas', () => {
  assert.equal(M.validateForecast(forecast(), request).top.mode, 'retrospective-forecast');
  assert.throws(() => M.validateForecast(forecast({horizonHours: 6}), request), M.ForecastError);
  assert.throws(() => M.validateForecast(forecast({mode: 'otro'}), request), M.ForecastError);
  const bad = forecast(); bad.features[0].properties.role = 'raro';
  assert.throws(() => M.validateForecast(bad, request), M.ForecastError);
  const cls = forecast(); cls.features[0].properties.dataClass = 'observed';
  assert.throws(() => M.validateForecast(cls, request), M.ForecastError);
  assert.throws(() => M.validateForecast({type: 'FeatureCollection', features: []}, request), M.ForecastError);
});

test('requestForecast transmite el mensaje de error del servicio (503) y valida la respuesta', async () => {
  const unavailable = async () => ({ok: false, status: 503, json: async () => ({error: 'El modelo desde el frente todavía se está preparando.'})});
  await assert.rejects(M.requestForecast(request, unavailable), /todavía se está preparando/);
  const ok = async (url, init) => { assert.equal(url, './api/forecast-reconstruction'); assert.deepEqual(JSON.parse(init.body), request); return {ok: true, status: 200, json: async () => forecast()}; };
  assert.equal((await M.requestForecast(request, ok)).features.length, 1);
  await assert.rejects(M.requestForecast(request, async () => { throw new TypeError('red'); }), /No se pudo contactar/);
});

test('cambiar el cursor o el horizonte invalida el pronóstico vigente y aborta la petición', () => {
  const tracker = M.createForecastTracker(), controller = new AbortController();
  const ticket = tracker.begin(request, controller);
  assert.equal(tracker.sync(utc(request.timeUtc), 12), false);
  assert.equal(tracker.state.status, 'loading');
  assert.equal(tracker.sync(utc(request.timeUtc) + 60, 12), true);
  assert.equal(controller.signal.aborted, true);
  assert.equal(tracker.state, null);
  assert.equal(tracker.accept(ticket, {}), false);
  const t2 = tracker.begin(request);
  assert.equal(tracker.sync(utc(request.timeUtc), 24), true);
  assert.equal(tracker.accept(t2, {}), false);
});

test('una respuesta tardía de una petición anterior se ignora', () => {
  const tracker = M.createForecastTracker();
  const first = tracker.begin(request);
  const second = tracker.begin({timeUtc: '2025-08-27T21:00:00Z', horizonHours: 12});
  assert.equal(tracker.accept(first, {late: true}), false);
  assert.equal(tracker.fail(first, new Error('x')), false);
  assert.equal(tracker.state.status, 'loading');
  assert.equal(tracker.accept(second, {ok: true}), true);
  assert.equal(tracker.state.status, 'ready');
  assert.equal(tracker.sync(utc('2025-08-27T21:00:00Z'), 12), false);
  assert.equal(tracker.state.status, 'ready');
});

test('la comparación de procedencia conserva las razones 1,53 y 1,38', () => {
  const summary = read('summary.json');
  const comparisons = M.areaComparisons(summary);
  assert.deepEqual(comparisons.map(c => c.ratio), [1.53, 1.38]);
  assert.equal(comparisons[0].atUtc, '2025-08-26T06:59:00Z');
});

test('los eventos marcados caen dentro del rango y declaran cuáles dependen de un supuesto', () => {
  for (const e of M.EVENTS) { const t = utc(e.utc); assert.ok(t >= M.RANGE_START_SEC && t <= M.RANGE_END_SEC); }
  assert.equal(M.EVENTS.find(e => e.id === 'calfire').assumption, true);
  assert.equal(M.EVENTS.find(e => e.id === 'pyro').utc, M.EVENTS.find(e => e.id === 'frp').utc);
  const frp = overpasses.find(o => o.t === utc('2025-08-27T23:00:00Z'));
  assert.ok(frp && frp.source === 'MODIS_SP');
});

test('los límites del pronóstico abarcan todas las geometrías, incluidas las partes separadas', () => {
  const small = M.featureBounds([{geometry: {type: 'Polygon', coordinates: [[[-119.1, 36.9], [-119.05, 36.9], [-119.05, 36.95], [-119.1, 36.9]]]}}]);
  const big = M.featureBounds([{geometry: {type: 'MultiPolygon', coordinates: [[[[-119.2, 36.8], [-118.8, 36.8], [-118.8, 37.1], [-119.2, 36.8]]]]}}, {geometry: {type: 'Polygon', coordinates: [[[-119.1, 36.9], [-119.05, 36.9], [-119.05, 36.95], [-119.1, 36.9]]]}}]);
  assert.deepEqual(big, {minx: -119.2, miny: 36.8, maxx: -118.8, maxy: 37.1});
  assert.deepEqual(small, {minx: -119.1, miny: 36.9, maxx: -119.05, maxy: 36.95});
  assert.equal(M.featureBounds([]), null);
});
