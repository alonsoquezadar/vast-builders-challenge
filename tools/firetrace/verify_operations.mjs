// Run against a local server: node tools/firetrace/verify_operations.mjs http://localhost:5182
import assert from 'node:assert/strict';
import {validateForecast} from './firetrace_model.mjs';

const base = new URL(process.argv[2] || 'http://localhost:5173');
assert(['localhost', '127.0.0.1'].includes(base.hostname), 'Use a local FireTrace server.');
async function get(path) {
  const response = await fetch(new URL(path, base));
  assert.equal(response.status, 200, path);
  return response;
}
const entry = await get('/');
assert.equal(new URL(entry.url).pathname, '/firetrace.html');
for (const path of ['/firetrace.js', '/firetrace.css', '/firetrace_model.mjs']) await get(path);
const arrival = await (await get('/api/satellite?layer=arrival')).json();
const incident = await (await get('/api/incident')).json();
assert.equal(incident.cameras.length, 2);
assert(incident.frames.every(frame => frame.analysisIntegrity === 'matched'));

async function request(body) {
  const response = await fetch(new URL('/api/forecast-reconstruction', base), {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  return {status: response.status, body: await response.json()};
}
const timeUtc = '2025-08-27T23:00:00Z';
const initialCells = arrival.features.filter(f => f.properties.t <= Date.parse(timeUtc) / 1000).length;
const results = [];
let previousArea = 0;
for (const horizonHours of [6, 12, 24]) {
  const input = {timeUtc, horizonHours};
  const response = await request(input);
  assert.equal(response.status, 200, JSON.stringify(response.body));
  const {top, features} = validateForecast(response.body, input);
  const initial = features.find(f => f.properties.role === 'initial-extent');
  assert.equal(initial.properties.cellCount, initialCells, 'Forecast starts from the selected reconstruction.');
  assert.equal(top.validated, false);
  assert.equal(Date.parse(top.validUtc), Date.parse(timeUtc) + horizonHours * 3600000);
  const m = top.metrics;
  assert.equal(m.intersectionHa + m.overpredictionHa, m.predictedHa);
  assert.equal(m.intersectionHa + m.underpredictionHa, m.referenceHa);
  assert(m.predictedHa >= previousArea);
  previousArea = m.predictedHa;
  results.push({horizonHours, iou: m.iou, growthIou: m.growthIou, predictedHa: m.predictedHa,
    referenceHa: m.referenceHa, domainBoundaryReached: top.domainBoundaryReached});
}
const lateInput = {timeUtc: '2025-09-12T20:00:00Z', horizonHours: 6};
const late = await request(lateInput);
assert.equal(late.status, 200);
const {top: lateTop} = validateForecast(late.body, lateInput);
assert.equal(lateTop.referenceAvailable, false);
assert.equal(lateTop.metrics.iou, null);
for (const body of [{timeUtc, horizonHours: 7}, {timeUtc: '2025-08-24T00:00:00Z', horizonHours: 6}]) {
  assert.equal((await request(body)).status, 400);
}
console.log(JSON.stringify({base: base.origin, initialCells, cameraFrames: incident.frames.length,
  results, unavailableReferenceChecked: true, invalidRequestsChecked: true}, null, 2));
