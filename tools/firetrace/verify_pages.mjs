// Verify a built directory served over HTTP, including a GitHub Pages project path.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {validateForecast} from './firetrace_model.mjs';

const base = new URL(process.argv[2] || 'http://localhost:5184/');
assert(base.pathname.endsWith('/'), 'The site URL must end with /.');
async function get(path) {
  const response = await fetch(new URL(path, base));
  assert.equal(response.status, 200, path);
  return response;
}
const html = await (await get('index.html')).text();
assert(html.includes('data-deployment="static"'));
assert(html.includes('id="tour-start"'));
assert(html.includes('id="camera-video"'));
const build = await (await get('build-manifest.json')).json();
for (const name of ['firetrace.js', 'tour.js', 'tour.css', 'data-client.mjs', 'camera-player.js', 'video-clock.mjs']) {
  const bytes = Buffer.from(await (await get(name)).arrayBuffer());
  assert.equal(createHash('sha256').update(bytes).digest('hex'), build.sha256[name], name);
}
const arrival = await (await get('data/arrival.json')).json();
assert(arrival.features.length > 0);
for (const layer of ['hotspots', 'weather', 'daily', 'summary', 'overpasses', 'perimeter']) {
  await (await get(`data/${layer}.json`)).json();
}
const incident = await (await get('data/incident.json')).json();
assert.equal(incident.frames.length, 6);
for (const frame of incident.frames) {
  assert.equal(frame.analysisIntegrity, 'matched');
  const bytes = Buffer.from(await (await get(frame.imagePath)).arrayBuffer());
  assert.equal(createHash('sha256').update(bytes).digest('hex'), frame.imageSha256);
}
for (const camera of incident.cameras) {
  const response = await get(camera.clipPath);
  assert(response.headers.get('content-type')?.includes('video/mp4'));
  await response.arrayBuffer();
  if (base.hostname.endsWith('.github.io')) {
    const partial = await fetch(new URL(camera.clipPath, base), {headers: {Range: 'bytes=100-199'}});
    assert.equal(partial.status, 206, 'The published video must support seeking.');
    assert.equal((await partial.arrayBuffer()).byteLength, 100);
  }
}
const catalogue = await (await get('data/projections.json')).json();
assert(catalogue.times.length > 400);
assert.equal(build.projectionCount, catalogue.times.length * 3);
const sampleTimes = [catalogue.times[0], Date.parse('2025-08-27T23:00:00Z') / 1000, catalogue.times.at(-1)];
for (const seconds of sampleTimes) {
  for (const horizonHours of [6, 12, 24]) {
    const request = {timeUtc: new Date(seconds * 1000).toISOString().replace('.000Z', 'Z'), horizonHours};
    const payload = await (await get(`data/projections/${seconds}-${horizonHours}.json`)).json();
    const result = validateForecast(payload, request);
    assert.equal(result.top.validated, false);
  }
}
console.log(JSON.stringify({site: base.href, tour: true, verifiedFrames: incident.frames.length,
  hourlyStartingTimes: catalogue.times.length, savedProjections: build.projectionCount,
  checkedProjectionSamples: sampleTimes.length * 3}, null, 2));
