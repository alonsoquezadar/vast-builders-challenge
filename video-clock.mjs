import {frameUtcSec} from './firetrace_model.mjs';

// Times between the reviewed printed timestamps are estimates, never extrapolated.
export function videoAnchors(camera, frames) {
  const anchors = frames.filter(frame => frame.cameraId === camera.id)
    .map(frame => ({video: frame.sourceVideoSecond - camera.sourceClipStart, utc: frameUtcSec(frame)}))
    .sort((a, b) => a.video - b.video);
  if (anchors.length < 2 || anchors.some((a, i) => !Number.isFinite(a.video) || a.video < 0 ||
    !Number.isFinite(a.utc) || (i > 0 && (a.video <= anchors[i - 1].video || a.utc <= anchors[i - 1].utc)))) return [];
  return anchors;
}

function interpolate(anchors, value, from, to) {
  if (anchors.length < 2 || !Number.isFinite(value) || value < anchors[0][from] || value > anchors.at(-1)[from]) return null;
  for (let i = 1; i < anchors.length; i++) {
    const a = anchors[i - 1], b = anchors[i];
    if (value <= b[from]) return a[to] + (value - a[from]) / (b[from] - a[from]) * (b[to] - a[to]);
  }
  return null;
}

export const videoToUtc = (anchors, seconds) => interpolate(anchors, seconds, 'video', 'utc');
export const utcToVideo = (anchors, utc) => interpolate(anchors, utc, 'utc', 'video');
