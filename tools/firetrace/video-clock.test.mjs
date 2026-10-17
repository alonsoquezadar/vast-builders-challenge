import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {videoAnchors, videoToUtc, utcToVideo} from './video-clock.mjs';
import {frameUtcSec} from './firetrace_model.mjs';

const incident = JSON.parse(readFileSync(new URL('./evidence/garnet/manifest.json', import.meta.url)));
for (const camera of incident.cameras) {
  test(`${camera.id}: exact printed anchors honour the trimmed clip offset and assumed PDT`, () => {
    const anchors = videoAnchors(camera, incident.frames);
    assert.equal(anchors.length, 3);
    for (const frame of incident.frames.filter(f => f.cameraId === camera.id)) {
      const seconds = frame.sourceVideoSecond - camera.sourceClipStart;
      assert.equal(videoToUtc(anchors, seconds), frameUtcSec(frame));
      assert.equal(utcToVideo(anchors, frameUtcSec(frame)), seconds);
    }
    const first = incident.frames.find(f => f.cameraId === camera.id);
    const offset = frameUtcSec(first) - Date.parse(first.printedTime + 'Z') / 1000;
    assert(Math.abs(offset - (7 * 3600 - Number('0.' + first.printedTime.split('.')[1]))) < 0.001);
  });
  test(`${camera.id}: timelapse interpolation is reversible in each timestamp interval`, () => {
    const anchors = videoAnchors(camera, incident.frames);
    for (let i = 1; i < anchors.length; i++) {
      const a = anchors[i - 1], b = anchors[i];
      const seconds = a.video + (b.video - a.video) * 0.4;
      const utc = a.utc + (b.utc - a.utc) * 0.4;
      assert(Math.abs(videoToUtc(anchors, seconds) - utc) < 0.001);
      assert(Math.abs(utcToVideo(anchors, utc) - seconds) < 0.001);
    }
  });
  test(`${camera.id}: footage outside the timestamped interval is never extrapolated`, () => {
    const anchors = videoAnchors(camera, incident.frames);
    assert.equal(videoToUtc(anchors, anchors[0].video - 1), null);
    assert.equal(videoToUtc(anchors, anchors.at(-1).video + 1), null);
    assert.equal(utcToVideo(anchors, anchors[0].utc - 60), null);
    assert.equal(utcToVideo(anchors, anchors.at(-1).utc + 60), null);
  });
}
test('incomplete or contradictory anchors cannot be used to synchronise footage', () => {
  const camera = incident.cameras[0];
  assert.deepEqual(videoAnchors(camera, incident.frames.slice(0, 1)), []);
  assert.deepEqual(videoAnchors(camera, [incident.frames[0], incident.frames[0]]), []);
  assert.equal(videoToUtc([], 10), null);
});
