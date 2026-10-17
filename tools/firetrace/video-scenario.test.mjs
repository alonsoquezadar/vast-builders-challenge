import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {readVideoScenario, videoScenarioFrame} from './video-scenario.mjs';

const raw = JSON.parse(readFileSync(new URL('./evidence/garnet/video-scenario.json', import.meta.url)));
const scenario = readVideoScenario(raw);
const seconds = value => Date.parse(value) / 1000;

test('the model visibly grows across the real video while the satellite reconstruction is unchanged', () => {
  const frames = ['2025-08-27T23:17:00Z', '2025-08-28T01:13:00Z', '2025-08-28T03:17:00Z']
    .map(time => videoScenarioFrame(scenario, seconds(time)));
  assert(frames.every(frame => frame.status === 'active'));
  assert(frames[0].visibleCells < frames[1].visibleCells);
  assert(frames[1].visibleCells < frames[2].visibleCells);
  const reference = JSON.parse(readFileSync(new URL('./evidence/garnet/satellite/arrival-reconstructed.geojson', import.meta.url)));
  const counts = ['2025-08-27T23:17:00Z', '2025-08-28T03:17:00Z'].map(time =>
    reference.features.filter(feature => feature.properties.t <= seconds(time)).length);
  assert.equal(counts[0], counts[1]);
});

test('seeking backwards removes later modelled cells and never displays future arrivals', () => {
  for (const cursor of [scenario.properties.startSec, seconds('2025-08-28T01:13:00Z'), scenario.properties.endSec]) {
    const frame = videoScenarioFrame(scenario, cursor);
    const visible = raw.features.filter(feature => feature.properties.arrivalSec <= cursor);
    assert.equal(frame.visibleCells, visible.length);
    assert.equal(frame.newAreaHa, visible.reduce((sum, feature) => sum + feature.properties.cellAreaHa, 0));
    assert.deepEqual(frame.filter, ['<=', ['get', 'arrivalSec'], cursor]);
  }
  assert.equal(videoScenarioFrame(scenario, scenario.properties.startSec).newAreaHa, 0);
});

test('the layer is hidden outside the scenario and when disabled', () => {
  for (const frame of [videoScenarioFrame(scenario, scenario.properties.startSec - 1),
    videoScenarioFrame(scenario, scenario.properties.endSec + 1), videoScenarioFrame(scenario, scenario.properties.startSec + 60, false)]) {
    assert.notEqual(frame.status, 'active'); assert.equal(frame.visibleCells, 0);
    assert.deepEqual(frame.filter, ['==', ['get', 'arrivalSec'], -1]);
  }
});

test('invalid data cannot be presented as a validated or observed video model', () => {
  assert.throws(() => readVideoScenario({...raw, properties: {...raw.properties, validated: true}}));
  assert.throws(() => readVideoScenario({...raw, features: [{...raw.features[0], properties: {...raw.features[0].properties, arrivalSec: scenario.properties.endSec + 1}}]}));
});
