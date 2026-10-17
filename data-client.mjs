export const STATIC = document.documentElement.dataset.deployment === 'static';

export function dataUrl(path) {
  if (!STATIC) return path;
  const url = new URL(path, location.href);
  if (!url.pathname.includes('/api/')) return path;
  if (url.pathname.endsWith('/api/satellite')) return `./data/${encodeURIComponent(url.searchParams.get('layer'))}.json`;
  if (url.pathname.endsWith('/api/incident')) return './data/incident.json';
  throw new Error('This feature requires the local FireTrace server.');
}

let manifest;
export async function projectionCursor(cursor, signal) {
  if (!STATIC) return cursor;
  if (!manifest) {
    const response = await fetch('./data/projections.json', {signal});
    if (!response.ok) throw new Error('The saved projection catalogue could not be loaded.');
    manifest = await response.json();
  }
  return manifest.times.reduce((best, time) => Math.abs(time - cursor) < Math.abs(best - cursor) ? time : best);
}

export function forecastFetch(path, options) {
  if (!STATIC) return fetch(path, options);
  const request = JSON.parse(options.body);
  const seconds = Date.parse(request.timeUtc) / 1000;
  return fetch(`./data/projections/${seconds}-${request.horizonHours}.json`, {signal: options.signal});
}
