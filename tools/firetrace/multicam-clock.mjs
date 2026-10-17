// UTC seconds and original YouTube seconds, bounded by the supplied OCR readings.
export function readMulticam(doc) {
  if (doc?.schema !== 'firetrace-youtube-multicam-v1' || !/^[\w-]{11}$/.test(doc.videoId) || !Array.isArray(doc.cameras) || doc.cameras.length < 2) throw new Error('Invalid multi-camera evidence.');
  const ids = new Set();
  for (const camera of doc.cameras) {
    if (!/^[a-z0-9-]+$/.test(camera.id) || ids.has(camera.id) || !Array.isArray(camera.anchors) || camera.anchors.length < 2 || !Array.isArray(camera.coordinates) || camera.coordinates.length !== 2 || !camera.coordinates.every(Number.isFinite)) throw new Error('Invalid camera evidence.');
    ids.add(camera.id);
    camera.anchors.forEach((a, i) => {
      const previous = camera.anchors[i - 1];
      if (!Number.isFinite(a.video) || a.video < 0 || !Number.isFinite(a.utc) || previous && (a.video <= previous.video || a.utc <= previous.utc)) throw new Error('Camera timestamps must increase.');
    });
  }
  const start = Math.max(...doc.cameras.map(c => c.anchors[0].utc));
  const end = Math.min(...doc.cameras.map(c => c.anchors.at(-1).utc));
  if (start >= end) throw new Error('No shared camera interval.');
  return {...doc, start, end};
}

function interpolate(anchors, value, from, to) {
  if (!Number.isFinite(value) || value < anchors[0][from] || value > anchors.at(-1)[from]) return null;
  let lo = 1, hi = anchors.length - 1;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (anchors[mid][from] < value) lo = mid + 1; else hi = mid; }
  const a = anchors[lo - 1], b = anchors[lo];
  return a[to] + (value - a[from]) / (b[from] - a[from]) * (b[to] - a[to]);
}

export const incidentToVideo = (camera, utc) => interpolate(camera.anchors, utc, 'utc', 'video');
export const videoToIncident = (camera, video) => interpolate(camera.anchors, video, 'video', 'utc');
export const clampTime = (evidence, utc) => Math.max(evidence.start, Math.min(evidence.end, utc));

export function cameraAtVideo(camera, video, targetUtc) {
  const utc = videoToIncident(camera, video);
  return {utc, delta: utc === null ? null : utc - targetUtc};
}
