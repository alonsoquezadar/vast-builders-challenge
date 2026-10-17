import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {initCameraPlayer} from './camera-player.js';
import {videoAnchors, videoToUtc} from './video-clock.mjs';

const incident = JSON.parse(readFileSync(new URL('./evidence/garnet/manifest.json', import.meta.url)));
class Element extends EventTarget {
  hidden = true; textContent = ''; dataset = {}; value = '';
  click() { this.dispatchEvent(new Event('click')); }
  setAttribute() {}
  focus() {}
  replaceChildren() {}
  append() {}
}
class Video extends Element {
  readyState = 0; duration = 52; paused = true; seeking = false; _time = 0;
  get currentTime() { return this._time; }
  set currentTime(time) { this._time = time; this.seeking = true; }
  pause() { this.paused = true; this.dispatchEvent(new Event('pause')); }
  play() { this.paused = false; this.dispatchEvent(new Event('play')); this.dispatchEvent(new Event('playing')); return Promise.resolve(); }
  completeSeek() { this.seeking = false; this.dispatchEvent(new Event('seeked')); }
  advanceTo(time) { this._time = time; this.dispatchEvent(new Event('timeupdate')); }
}
function fixture() {
  const ids = ['camera-player', 'camera-video', 'video-camera', 'video-sync-status', 'video-range', 'footage-open', 'video-restart', 'video-close'];
  const elements = Object.fromEntries(ids.map(id => [id, id === 'camera-video' ? new Video() : new Element()]));
  globalThis.document = {getElementById: id => elements[id], createElement: () => new Element(), hidden: false};
  const anchors = videoAnchors(incident.cameras[0], incident.frames);
  let cursor = anchors[0].utc;
  const player = initCameraPlayer({getCursor: () => cursor, getZone: () => 'UTC', setCursor: utc => { cursor = utc; }, pauseTimeline() {}});
  player.setIncident(incident); player.open();
  return {player, elements, video: elements['camera-video'], anchors, get cursor() { return cursor; }};
}

test('starting before metadata waits for the initial frame, then video playback drives the incident clock', () => {
  const f = fixture();
  f.player.restart();
  assert.equal(f.video.paused, true);
  assert.match(f.elements['video-sync-status'].textContent, /Loading/);
  f.video.readyState = 4; f.video.dispatchEvent(new Event('loadedmetadata'));
  assert.equal(f.video.currentTime, f.anchors[0].video);
  assert.equal(f.video.paused, true);
  f.video.completeSeek();
  assert.equal(f.video.paused, false);
  f.video.advanceTo(20);
  assert.equal(f.cursor, videoToUtc(f.anchors, 20));
  assert.match(f.elements['video-sync-status'].textContent, /Estimated video time/);
});

test('moving the timeline while a start is loading cancels delayed autoplay', () => {
  const f = fixture();
  f.player.restart();
  const utc = videoToUtc(f.anchors, 20);
  f.player.syncCursor(utc);
  f.video.readyState = 4; f.video.dispatchEvent(new Event('loadedmetadata')); f.video.completeSeek();
  assert.equal(f.video.paused, true);
  assert(Math.abs(f.video.currentTime - 20) < 0.001);
});

test('closing the dock while loading cannot start a hidden video later', () => {
  const f = fixture();
  f.player.restart(); f.elements['video-close'].click();
  f.video.readyState = 4; f.video.dispatchEvent(new Event('loadedmetadata')); f.video.completeSeek();
  assert.equal(f.video.paused, true);
  assert.equal(f.elements['camera-player'].hidden, true);
});

test('a stale seek completion cannot complete a newer timeline seek', () => {
  const f = fixture(); f.video.readyState = 4;
  f.player.syncCursor(videoToUtc(f.anchors, 10));
  f.player.syncCursor(videoToUtc(f.anchors, 25));
  f.video._time = 10; f.video.completeSeek();
  assert.equal(f.elements['video-sync-status'].dataset.state, 'seeking');
  f.video._time = 25; f.video.completeSeek();
  assert.equal(f.elements['video-sync-status'].dataset.state, 'linked');
});
