import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {readMulticam, incidentToVideo, videoToIncident, clampTime, cameraAtVideo} from './multicam-clock.mjs';

const raw = JSON.parse(readFileSync(new URL('./evidence/gann/youtube.json', import.meta.url)));
const data = readMulticam(raw);

test('the shared replay ends at the conservative Southworth anchor, not the report estimate', () => {
  assert.equal(new Date(data.start * 1000).toISOString(), '2026-08-04T00:47:24.700Z');
  assert.equal(new Date(data.end * 1000).toISOString(), '2026-08-04T07:53:31.000Z');
  assert.equal(data.cameras.length, 4);
});

test('every camera maps the same incident clock to its own segment and back, including midnight', () => {
  for (const utc of [data.start, Date.parse('2026-08-04T05:00:00Z') / 1000, Date.parse('2026-08-04T07:30:00Z') / 1000, data.end]) {
    const videos = data.cameras.map(camera => {
      const video = incidentToVideo(camera, utc);
      assert.ok(Math.abs(videoToIncident(camera, video) - utc) < 0.001);
      return video;
    });
    assert.equal(new Set(videos).size, 4);
  }
});

test('dense timestamps preserve variable timelapse speed', () => {
  const camera = data.cameras[0];
  for (const a of camera.anchors) assert.equal(incidentToVideo(camera, a.utc), a.video);
  const a = camera.anchors[0], b = camera.anchors[1];
  assert.ok(Math.abs(incidentToVideo(camera, (a.utc + b.utc) / 2) - (a.video + b.video) / 2) < 0.00001);
});

test('a compilation cut or an unavailable time never extrapolates footage', () => {
  for (const camera of data.cameras) {
    assert.equal(videoToIncident(camera, camera.anchors.at(-1).video + 0.01), null);
    assert.equal(incidentToVideo(camera, camera.anchors[0].utc - 1), null);
    assert.equal(cameraAtVideo(camera, -1, data.start).delta, null);
  }
  assert.equal(clampTime(data, data.end + 100), data.end);
});

test('duplicate, reversed and non-overlapping readings are rejected at the evidence boundary', () => {
  for (const change of [
    d => { d.cameras[0].anchors[1].utc = d.cameras[0].anchors[0].utc; },
    d => { d.cameras[0].anchors[1].video = -1; },
    d => { d.cameras[0].anchors.forEach(a => { a.utc += 86400; }); },
    d => { d.cameras[1].id = d.cameras[0].id; }
  ]) {
    const copy = structuredClone(raw); change(copy);
    assert.throws(() => readMulticam(copy));
  }
});
