import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {
  RANGE_START_SEC, RANGE_END_SEC, DEFAULT_CURSOR_SEC, clampCursor, formatUtc, formatCount, hotspotWindow, hotspotFilter, arrivalFilter,
  sortedTimes, countInRange, parsePrintedClockAsUtcSeconds, assumedUtcFromPrinted, cursorFromFrames, assumptionNote, cardinal,
  prepareWeather, nearestWeatherHour, weatherLines, fetchLayer, validateLayer, createLayerStore, provenanceText, classificationWarning,
  createMapLayers, whenMapReady, popupLines, mapLayerId, SatelliteError, evidenceWarnings
} from './satellite-view.mjs';

const dir = new URL('./evidence/garnet/satellite/', import.meta.url);
const read = name => JSON.parse(readFileSync(new URL(name, dir)));
const hotspots = read('hotspots.geojson');
const arrival = read('arrival-reconstructed.geojson');
const weather = read('weather-hourly.json');
const summary = read('summary.json');
const utc = iso => Date.parse(iso) / 1000;

// Evaluador mínimo de las expresiones de filtro que genera el módulo.
const evalFilter = (expr, props) => {
  const [op, ...args] = expr;
  const value = a => (Array.isArray(a) ? (a[0] === 'get' ? props[a[1]] : evalFilter(a, props)) : a);
  if (op === 'all') return args.every(a => evalFilter(a, props));
  if (op === '>=') return value(args[0]) >= value(args[1]);
  if (op === '<=') return value(args[0]) <= value(args[1]);
  throw Error(`operador no soportado ${op}`);
};

test('el rango de la barra cubre todas las detecciones, celdas y horas del reanálisis usadas', () => {
  const ts = hotspots.features.map(f => f.properties.t);
  assert.ok(Math.min(...ts) >= RANGE_START_SEC && Math.max(...ts) <= RANGE_END_SEC);
  assert.ok(Math.max(...arrival.features.map(f => f.properties.t)) <= RANGE_END_SEC);
  assert.equal(formatUtc(RANGE_START_SEC), '2025-08-24 00:00 UTC');
  assert.equal(formatUtc(RANGE_END_SEC), '2025-09-12 23:59 UTC');
});

test('los conteos del archivo coinciden con el resumen publicado', () => {
  assert.equal(hotspots.features.length, summary.counts.detections);
  assert.equal(arrival.features.length, summary.counts.arrivalCells);
  assert.equal(arrival.features.filter(f => f.properties.kind === 'observed-support').length, summary.counts.cellsWithDetectionSupport);
  assert.equal(formatCount(13883), '13.883');
  assert.equal(formatCount(237), '237');
});

test('la ventana de focos nunca incluye detecciones posteriores al cursor, ni anteriores a 12 h', () => {
  for (const iso of ['2025-08-25T00:00:00Z', '2025-08-27T21:00:00Z', '2025-09-05T12:30:00Z', '2025-09-12T23:59:00Z']) {
    const cursor = utc(iso);
    const {fromSec, toSec} = hotspotWindow(cursor);
    assert.equal(cursor - fromSec, 12 * 3600);
    assert.equal(toSec, cursor);
    const inside = hotspots.features.filter(f => evalFilter(hotspotFilter(cursor), f.properties));
    assert.ok(inside.every(f => f.properties.t <= cursor && f.properties.t >= cursor - 12 * 3600));
    assert.equal(inside.length, countInRange(sortedTimes(hotspots.features), fromSec, toSec));
  }
});

test('las celdas reconstruidas solo aparecen cuando su hora estimada ya pasó', () => {
  const cursor = utc('2025-08-26T12:00:00Z');
  const shown = arrival.features.filter(f => evalFilter(arrivalFilter(cursor), f.properties));
  assert.ok(shown.length > 0 && shown.length < arrival.features.length);
  assert.ok(shown.every(f => f.properties.t <= cursor));
  const before = utc('2025-08-24T00:00:00Z');
  assert.equal(arrival.features.filter(f => evalFilter(arrivalFilter(before), f.properties)).length, 0);
});

test('countInRange incluye ambos extremos y tolera rangos vacíos', () => {
  const sorted = Float64Array.from([1, 2, 2, 5, 9]);
  assert.equal(countInRange(sorted, 2, 5), 3);
  assert.equal(countInRange(sorted, -Infinity, 2), 3);
  assert.equal(countInRange(sorted, 6, 8), 0);
  assert.equal(countInRange(sorted, 5, 2), 0);
});

test('el cursor se ajusta al paso y se limita al rango, y rechaza valores no numéricos', () => {
  assert.equal(clampCursor(RANGE_START_SEC - 10 * 86400), RANGE_START_SEC);
  assert.equal(clampCursor(RANGE_END_SEC + 10 * 86400), RANGE_END_SEC);
  assert.equal(clampCursor(DEFAULT_CURSOR_SEC + 29), DEFAULT_CURSOR_SEC);
  assert.equal(clampCursor(DEFAULT_CURSOR_SEC + 31), DEFAULT_CURSOR_SEC + 60);
  assert.throws(() => clampCursor(NaN), SatelliteError);
});

test('la meteorología elige la hora más cercana a ≤ 1 h y nunca la última fila fuera de rango', () => {
  const rows = prepareWeather(weather);
  const exact = nearestWeatherHour(rows, utc('2025-08-27T21:00:00Z'));
  assert.equal(exact.hour.timeUtc, '2025-08-27T21:00:00Z');
  assert.equal(exact.gapSec, 0);
  assert.equal(nearestWeatherHour(rows, utc('2025-08-27T21:20:00Z')).hour.timeUtc, '2025-08-27T21:00:00Z');
  assert.equal(nearestWeatherHour(rows, utc('2025-08-27T21:40:00Z')).hour.timeUtc, '2025-08-27T22:00:00Z');
  assert.equal(nearestWeatherHour(rows, utc('2025-08-27T21:30:00Z')).hour.timeUtc, '2025-08-27T21:00:00Z', 'empate: la hora anterior');
  const last = rows.at(-1);
  assert.equal(nearestWeatherHour(rows, last.sec + 3600).hour.timeUtc, last.timeUtc);
  assert.equal(nearestWeatherHour(rows, last.sec + 3601), null);
  assert.equal(nearestWeatherHour(rows, rows[0].sec - 3601), null);
  assert.equal(nearestWeatherHour([], DEFAULT_CURSOR_SEC), null);
  assert.equal(nearestWeatherHour(rows, NaN), null);
});

test('el texto del viento usa "desde" en grados y m/s, indica el punto y que la hora es del modelo', () => {
  const rows = prepareWeather(weather);
  const lines = weatherLines(nearestWeatherHour(rows, utc('2025-08-27T22:00:00Z')), weather.point);
  const text = lines.join('\n');
  assert.match(text, /Viento a 10 m: desde \d+° \([A-Z]+\) a \d+\.\d m\/s/);
  assert.match(text, /Humedad relativa: \d+ %/);
  assert.match(text, /Temperatura: -?\d+\.\d °C/);
  assert.match(text, /36\.871704, -118\.89473/);
  assert.match(weatherLines(null, weather.point)[0], /Sin hora del modelo histórico/);
  assert.equal(cardinal(245), 'OSO');
  assert.equal(cardinal(0), 'N');
  assert.equal(cardinal(359), 'N');
  assert.equal(cardinal(-90), 'O');
});

test('la meteorología rechaza datos sin horas válidas', () => {
  assert.throws(() => prepareWeather({hours: []}), SatelliteError);
  assert.throws(() => prepareWeather({hours: [{timeUtc: 'nunca'}]}), SatelliteError);
  assert.throws(() => prepareWeather(null), SatelliteError);
});

test('el supuesto PDT suma 7 h a la hora impresa del primer fotograma y lo rotula como supuesto', () => {
  assert.equal(assumedUtcFromPrinted('2025-08-27T16:16:57.53'), utc('2025-08-27T23:16:57Z'));
  const result = cursorFromFrames([{printedTime: '2025-08-27T16:16:57.53'}, {printedTime: '2025-08-27T16:26:41.25'}]);
  assert.equal(result.ok, true);
  assert.equal(result.sec, utc('2025-08-27T23:17:00Z'));
  assert.equal(result.printed, '2025-08-27 16:16:57');
  const note = assumptionNote(result);
  assert.match(note, /SUPUESTO, no verificado/);
  assert.match(note, /2025-08-27 23:17 UTC/);
  assert.match(note, /No afirma sincronía/);
});

test('el supuesto usa solo el primer fotograma y rechaza horas inválidas, vacías o fuera de rango', () => {
  const first = cursorFromFrames([{printedTime: '2025-08-27T10:00:00'}, {printedTime: '2025-09-01T10:00:00'}]);
  assert.equal(first.sec, utc('2025-08-27T17:00:00Z'));
  assert.deepEqual(cursorFromFrames([]), {ok: false, reason: 'sin-fotogramas'});
  assert.deepEqual(cursorFromFrames(null), {ok: false, reason: 'sin-fotogramas'});
  assert.deepEqual(cursorFromFrames([{printedTime: '25 de agosto'}]), {ok: false, reason: 'hora-invalida'});
  for (const bad of ['2025-08-27T25:00:00', '2025-08-27T12:60:00', '2025-02-30T12:00:00', '2025-08-27T12:00:00Z']) assert.throws(() => parsePrintedClockAsUtcSeconds(bad), SatelliteError);
  const out = cursorFromFrames([{printedTime: '2025-10-01T12:00:00'}]);
  assert.equal(out.ok, false);
  assert.equal(out.reason, 'fuera-de-rango');
  assert.match(assumptionNote(out), /fuera del rango/);
  assert.match(assumptionNote(null), /Aún no hay fotogramas/);
  assert.equal(cursorFromFrames([{printedTime: '2025-08-23T10:00:00'}]).ok, false);
  assert.equal(cursorFromFrames([{printedTime: '2025-08-23T17:00:00'}]).sec, RANGE_START_SEC);
  assert.equal(cursorFromFrames([{printedTime: '2025-09-12T17:00:00'}]).ok, false);
});

const jsonReply = (status, body) => async () => new Response(typeof body === 'string' ? body : JSON.stringify(body), {status});

test('cada fuente informa su propio error sin exponer detalles internos', async () => {
  await assert.rejects(fetchLayer('hotspots', jsonReply(502, {})), /HTTP 502/);
  await assert.rejects(fetchLayer('hotspots', jsonReply(502, '<html>Bad Gateway</html>')), /HTTP 502/);
  await assert.rejects(fetchLayer('hotspots', async () => { throw new TypeError('Failed to fetch https://x?MAP_KEY=secreto'); }), err => err instanceof SatelliteError && !/secreto|MAP_KEY/.test(err.message));
  await assert.rejects(fetchLayer('arrival', jsonReply(404, {error: 'Capa no disponible'})), /Capa no disponible/);
  await assert.rejects(fetchLayer('arrival', jsonReply(500, {error: 'x'.repeat(500)})), /HTTP 500/);
  await assert.rejects(fetchLayer('perimeter', jsonReply(200, {type: 'FeatureCollection', features: []})), /formato inesperado/);
  await assert.rejects(fetchLayer('weather', jsonReply(200, {hours: []})), /formato inesperado/);
  await assert.rejects(fetchLayer('summary', jsonReply(200, {})), /formato inesperado/);
  assert.throws(() => validateLayer('desconocida', {}), SatelliteError);
});

test('fetchLayer pide la capa por nombre y devuelve el JSON original con su procedencia', async () => {
  const calls = [];
  const data = await fetchLayer('weather', async url => { calls.push(url); return new Response(JSON.stringify({...weather, _provenance: {source: 'weather-hourly.json', sourceSha256: 'abcdef0123456789ff', dataClass: 'historical-weather-model'}})); });
  assert.deepEqual(calls, ['./api/satellite?layer=weather']);
  assert.equal(data.hours.length, weather.hours.length);
  assert.equal(provenanceText(data), 'historical-weather-model · sha256 abcdef012345…');
  assert.equal(provenanceText(weather), 'procedencia no declarada');
  assert.match(classificationWarning('arrival', {status: 'observed'}), /clasificación inesperada/);
  assert.equal(classificationWarning('arrival', {status: 'reconstructed'}), '');
  assert.equal(classificationWarning('hotspots', {}), '');
});

test('el estado de carga pasa por loading → ready/error, comparte la carga en curso y permite reintentar', async () => {
  let calls = 0, fail = true;
  const seen = [];
  const store = createLayerStore(async () => {
    calls++;
    if (fail) return new Response('{}', {status: 503});
    return new Response(JSON.stringify({type: 'FeatureCollection', features: [{}]}));
  }, name => seen.push(`${name}:${store.get(name).state}`));
  assert.equal(store.get('arrival').state, 'idle');
  const [a, b] = [store.load('arrival'), store.load('arrival')];
  assert.equal(store.get('arrival').state, 'loading');
  await assert.rejects(a);
  await assert.rejects(b);
  assert.equal(calls, 1);
  assert.equal(store.get('arrival').state, 'error');
  assert.match(store.get('arrival').error, /HTTP 503/);
  assert.equal(store.get('hotspots').state, 'idle', 'el error de una fuente no afecta a las demás');
  fail = false;
  await store.load('arrival');
  assert.equal(store.get('arrival').state, 'ready');
  assert.equal(store.get('arrival').error, null);
  await store.load('arrival');
  assert.equal(calls, 2);
  assert.deepEqual(seen, ['arrival:loading', 'arrival:error', 'arrival:loading', 'arrival:ready']);
  await assert.rejects(store.load('nada'), SatelliteError);
});

const fakeMap = () => {
  const log = [], layers = [], sources = new Set(), handlers = {};
  return {
    log, layers, handlers,
    getSource: id => (sources.has(id) ? {} : undefined),
    addSource: (id, spec) => { sources.add(id); log.push(['addSource', id, spec.type]); },
    addLayer: (spec, before) => { const at = before ? layers.findIndex(l => l.id === before) : layers.length; layers.splice(at, 0, spec); log.push(['addLayer', spec.id, before]); },
    setFilter: (id, f) => { layers.find(l => l.id === id).filter = f; log.push(['setFilter', id]); },
    setLayoutProperty: (id, k, v) => log.push(['layout', id, k, v]),
    getStyle: () => (handlers.ready ? {} : undefined),
    on: (ev, fn) => { (handlers[ev] ||= []).push(fn); },
    off: (ev, fn) => { handlers[ev] = (handlers[ev] || []).filter(f => f !== fn); }
  };
};

test('las capas del mapa se apilan en orden fijo, su filtro sigue al cursor y no se duplican', () => {
  const map = fakeMap();
  const ml = createMapLayers(map);
  ml.show('hotspots', hotspots);
  ml.show('arrival', arrival);
  ml.show('perimeter', read('perimeter.geojson'));
  assert.deepEqual(map.layers.map(l => l.id), ['arrival', 'perimeter', 'hotspots'].map(mapLayerId));
  assert.ok(map.layers.every(l => l.id.startsWith('firetrace-sat-')), 'sin chocar con la capa "satellite" del visor');
  const cursor = utc('2025-08-28T00:00:00Z');
  ml.setCursor(cursor);
  assert.deepEqual(map.layers.find(l => l.id === mapLayerId('hotspots')).filter, hotspotFilter(cursor));
  assert.deepEqual(map.layers.find(l => l.id === mapLayerId('arrival')).filter, arrivalFilter(cursor));
  assert.equal(map.layers.find(l => l.id === mapLayerId('perimeter')).filter, undefined);
  ml.hide('arrival');
  ml.show('arrival', arrival);
  assert.equal(map.log.filter(e => e[0] === 'addLayer').length, 3);
  assert.deepEqual(map.log.at(-1), ['layout', mapLayerId('arrival'), 'visibility', 'visible']);
  assert.deepEqual(map.log.filter(e => e[0] === 'layout' && e[3] === 'none').map(e => e[1]), [mapLayerId('arrival')]);
  ml.hide('weather');
});

test('una capa añadida después usa el cursor actual, no el inicial', () => {
  const map = fakeMap();
  const ml = createMapLayers(map);
  const cursor = utc('2025-09-01T06:00:00Z');
  ml.setCursor(cursor);
  ml.show('arrival', arrival);
  assert.deepEqual(map.layers[0].filter, arrivalFilter(cursor));
});

test('whenMapReady espera al estilo y no se queda colgado si ya está cargado', async () => {
  const ready = fakeMap();
  ready.handlers.ready = true;
  await whenMapReady(ready);
  const late = fakeMap();
  let done = false;
  const waiting = whenMapReady(late).then(() => { done = true; });
  await Promise.resolve();
  assert.equal(done, false);
  late.handlers.ready = true;
  late.handlers.styledata.forEach(fn => fn());
  await waiting;
  assert.deepEqual([late.handlers.styledata.length, late.handlers.load.length], [0, 0]);
});

test('los popups rotulan lo observado y lo reconstruido y no afirman frente, área ni velocidad', () => {
  const hot = popupLines('hotspots', hotspots.features[0].properties).join('\n');
  assert.match(hot, /OBSERVADO/);
  assert.match(hot, /\(UTC\)/);
  assert.match(hot, /VIIRS_NOAA21_NRT/);
  assert.match(hot, /no mide frente, área ni velocidad/);
  const cell = popupLines('arrival', arrival.features[0].properties).join('\n');
  assert.match(cell, /RECONSTRUIDA/);
  assert.match(cell, /no frente observado/);
  assert.match(cell, /observed-support|primera detección VIIRS a ≤ 400 m/);
  assert.match(popupLines('arrival', {kind: 'interpolated'}).join(' '), /interpolada/);
  const perimeter = popupLines('perimeter', read('perimeter.geojson').features[0].properties).join('\n');
  assert.match(perimeter, /FINAL/);
  assert.match(perimeter, /2025-12-19T20:09:49Z/);
  assert.match(perimeter, /no es el perímetro de una fecha intermedia/);
});

test('las advertencias conservan la sobrestimación y distinguen detección de ignición', () => {
  const lines = evidenceWarnings(summary).join(' ');
  assert.match(lines, /25\/08: superficie reconstruida ×1,53/);
  assert.match(lines, /31\/08: superficie reconstruida ×1,38/);
  assert.match(lines, /07:10 UTC/);
  assert.match(lines, /2025-08-24T09:26:00Z/);
  assert.match(lines, /FIRMS es posterior a WFIGS/);
  assert.match(lines, /Ninguna de estas horas establece la ignición exacta/);
});
