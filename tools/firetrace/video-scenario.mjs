export function readVideoScenario(value) {
  const p = value?.properties;
  if (value?.type !== 'FeatureCollection' || p?.schema !== 'firetrace-video-scenario-v1' ||
      p.validated !== false || !Number.isFinite(p.startSec) || !Number.isFinite(p.endSec) ||
      p.endSec <= p.startSec || !(p.cellAreaHa > 0) || !(p.initialAreaHa > 0) || !Array.isArray(value.features)) {
    throw new Error('The video-linked scenario has an unsupported data format.');
  }
  const times = value.features.map(f => {
    const time = f.properties?.arrivalSec;
    if (f.geometry?.type !== 'Polygon' || f.properties?.dataClass !== 'modelled' ||
        !Number.isFinite(time) || time < p.startSec || time > p.endSec ||
        Math.abs(f.properties.cellAreaHa - p.cellAreaHa) > 0.001) {
      throw new Error('A scenario cell has invalid arrival time, area or provenance.');
    }
    return time;
  }).sort((a, b) => a - b);
  return {geojson: value, properties: p, times};
}

export function videoScenarioFrame(scenario, cursor, enabled = true) {
  if (!scenario) return {status: 'loading', visibleCells: 0, filter: ['==', ['get', 'arrivalSec'], -1]};
  const {startSec, endSec, initialAreaHa, cellAreaHa} = scenario.properties;
  const status = !enabled ? 'off' : cursor < startSec ? 'before' : cursor > endSec ? 'after' : 'active';
  if (status !== 'active') return {status, visibleCells: 0, filter: ['==', ['get', 'arrivalSec'], -1]};
  let low = 0, high = scenario.times.length;
  while (low < high) {
    const mid = (low + high) >>> 1;
    if (scenario.times[mid] <= cursor) low = mid + 1;
    else high = mid;
  }
  return {status, visibleCells: low, newAreaHa: low * cellAreaHa, modelledAreaHa: initialAreaHa + low * cellAreaHa,
    elapsedHours: (cursor - startSec) / 3600, filter: ['<=', ['get', 'arrivalSec'], cursor]};
}
