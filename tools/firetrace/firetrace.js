import * as M from './firetrace_model.mjs';

const $ = id => document.getElementById(id);
const el = (tag, props = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') node.className = v; else if (k === 'text') node.textContent = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v); else if (v !== false && v != null) node.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids) node.append(kid);
  return node;
};
const svgText = (parent, attrs, text) => { const n = svgEl('text', attrs); n.textContent = text; parent.append(n); return n; };
const svgEl = (tag, attrs = {}) => {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
};

const HOME = {center: [-119.08, 36.955], zoom: 11.1, pitch: 60, bearing: -22};
const framePadding = () => ({top: 10, bottom: $('map').clientWidth < 700 ? 20 : 70, left: 0, right: 0});
const frameFire = (duration = 0) => map?.easeTo({...HOME, zoom: $('map').clientWidth < 700 ? 10.3 : HOME.zoom, padding: framePadding(), duration});
const hash = new URLSearchParams(location.hash.slice(1));
const speedDefault = Number(hash.get('speed')) || 6;
const DEFAULT_CURSOR = M.parseUtc('2025-08-27T23:00:00Z');
const startCursor = (() => { try { return hash.get('t') ? M.clampCursor(M.parseUtc(hash.get('t'))) : DEFAULT_CURSOR; } catch { return DEFAULT_CURSOR; } })();

const state = {
  cursor: startCursor, playPos: startCursor, zone: 'UTC', playing: false, speed: speedDefault,
  recentHours: 12, horizon: 12, selectedCamera: null, mapReady: false, tileErrors: 0
};
const data = {arrival: null, hotspots: null, overpasses: null, perimeter: null, daily: null, weather: null, summary: null, incident: null};
const dataStatus = {};
const derived = {areaSeries: null, edges: null, overpasses: [], weatherHours: []};
const forecastTracker = M.createForecastTracker();
let map = null;
const pendingSources = new Map();

// ---------- utilidades ----------

const fmtStamp = sec => M.formatStamp(sec, state.zone);
function showData(msg) { const chip = $('data-chip'); chip.hidden = !msg; chip.textContent = msg || ''; }
const failures = new Set();
function reportFailure(name, message) { failures.add(name); showData(`No disponible: ${[...failures].join(', ')}. El resto de la vista sigue funcionando.`); return message; }

async function fetchJson(url, init) {
  let response;
  try { response = await fetch(url, init); } catch { throw new Error('No se pudo contactar con el servidor.'); }
  let body = null;
  try { body = await response.json(); } catch { /* sin cuerpo JSON */ }
  if (!response.ok) throw new Error(typeof body?.error === 'string' ? body.error : `HTTP ${response.status}`);
  return body;
}

// ---------- capas de datos ----------

const LAYER_DEFS = [
  {id: 'reconstruction', label: 'Reconstrucción de llegada', cls: 'rec', pill: 'RECONSTRUIDO', on: true, data: 'arrival', map: ['burn-fill', 'recent-fill', 'edge-old', 'edge-glow', 'edge-recent']},
  {id: 'firms', label: 'Focos FIRMS · pasada actual', cls: 'obs', pill: 'OBSERVADO', on: true, data: 'hotspots', map: ['firms-glow', 'firms']},
  {id: 'perimeter', label: 'Perímetro FINAL (dic 2025)', cls: 'obs', pill: 'OBSERVADO', on: false, data: 'perimeter', map: ['perimeter-fill', 'perimeter-line']},
  {id: 'forecast', label: 'Pronóstico', cls: 'mod', pill: 'MODELADO', on: true, data: null, map: []},
  {id: 'cones', label: 'Conos de cámara', cls: 'hyp', pill: 'HIPÓTESIS', on: false, data: null, map: ['cones-fill', 'cones-line']}
];
const layerOn = Object.fromEntries(LAYER_DEFS.map(d => [d.id, d.on]));
const PILL = {rec: 'pill-rec', obs: 'pill-obs', mod: 'pill-mod', hyp: 'pill-hyp'};

async function loadData(name) {
  if (data[name] || dataStatus[name] === 'loading') return;
  dataStatus[name] = 'loading'; renderLayerRows();
  try {
    const value = await fetchJson(`./api/satellite?layer=${encodeURIComponent(name)}`);
    data[name] = value; dataStatus[name] = 'ready';
    failures.delete(name); if (!failures.size) showData('');
  } catch (e) {
    dataStatus[name] = 'error:' + e.message; reportFailure(name);
  }
  if (data[name]) { try { onData(name); } catch (e) { console.error('firetrace render', name, e); } }
  renderLayerRows();
}
async function loadIncident() {
  dataStatus.incident = 'loading';
  try { data.incident = await fetchJson('./api/incident'); dataStatus.incident = 'ready'; addCameraPins(); }
  catch (e) { dataStatus.incident = 'error:' + e.message; reportFailure('cámaras'); }
  cameraKey = ''; paintAll(); if (data.incident) paintProvenance();
}
function onData(name) {
  if (name === 'arrival') {
    derived.areaSeries = M.cumulativeAreaSeries(data.arrival.features);
    derived.edges = M.buildBoundaryEdges(data.arrival.features);
    setSource('arrival', data.arrival); setSource('edges', {type: 'FeatureCollection', features: derived.edges});
  } else if (name === 'hotspots') setSource('hotspots', data.hotspots);
  else if (name === 'perimeter') setSource('perimeter', data.perimeter);
  else if (name === 'overpasses') derived.overpasses = M.sortOverpasses(data.overpasses.overpasses || []);
  else if (name === 'weather') derived.weatherHours = data.weather.hours || [];
  if (['arrival', 'overpasses', 'weather', 'daily', 'summary'].includes(name)) { weatherKey = ''; drawCharts(); }
  if (name === 'summary' || name === 'arrival') paintProvenance();
  paintAll();
}
function setSource(id, fc) {
  pendingSources.set(id, fc);
  const src = map?.getSource(id);
  if (src) src.setData(fc);
}

function layerStatusText(def) {
  if (!def.data) return def.id === 'forecast' ? (forecastTracker.state?.status === 'ready' ? 'proyección activa' : 'sin proyección en este instante') : 'posiciones hipotéticas';
  const s = dataStatus[def.data];
  if (!s) return def.on ? 'pendiente' : 'se carga al activarla';
  if (s === 'loading') return 'cargando…';
  if (s.startsWith('error:')) return s.slice(6);
  const n = {arrival: data.arrival?.features.length, hotspots: data.hotspots?.features.length, perimeter: data.perimeter?.features.length}[def.data];
  return n != null ? `${M.formatNumber(n)} elementos` : 'listo';
}
function renderLayerRows() {
  const list = $('layer-list'); list.replaceChildren();
  for (const def of LAYER_DEFS) {
    const id = 'layer-' + def.id, s = def.data && dataStatus[def.data];
    const isErr = s?.startsWith?.('error:');
    const row = el('li', {class: 'layer-row'},
      el('input', {type: 'checkbox', id, checked: layerOn[def.id], onchange: e => toggleLayer(def.id, e.target.checked)}),
      el('label', {for: id}, el('span', {text: def.label}), el('span', {class: 'layer-status' + (isErr ? ' err' : ''), text: layerStatusText(def)})),
      isErr ? el('button', {text: 'Reintentar', onclick: () => { dataStatus[def.data] = null; failures.delete(def.data); loadData(def.data); }}) : el('b', {class: 'pill ' + PILL[def.cls], text: def.pill}));
    list.append(row);
  }
  updateLegend();
}
function toggleLayer(id, on) {
  layerOn[id] = on;
  const def = LAYER_DEFS.find(d => d.id === id);
  if (on && def.data) loadData(def.data);
  applyVisibility(); updateLegend(); renderLayerRows();
}
function applyVisibility() {
  if (!state.mapReady) return;
  for (const def of LAYER_DEFS) for (const l of def.map) if (map.getLayer(l)) map.setLayoutProperty(l, 'visibility', layerOn[def.id] ? 'visible' : 'none');
  setForecastVisibility();
}
function updateLegend() {
  const q = sel => document.querySelector(sel);
  q('.legend-perimeter').hidden = !layerOn.perimeter;
  q('.legend-cones').hidden = !layerOn.cones;
  const forecastShown = layerOn.forecast && forecastTracker.state?.status === 'ready';
  document.querySelectorAll('.legend-forecast').forEach(n => { n.hidden = !forecastShown; });
  $('legend-recent').textContent = `Actividad reciente RECONSTRUIDA (${state.recentHours} h)`;
}

// ---------- mapa ----------

function mapStyle() {
  return {
    version: 8,
    sky: {'sky-color': '#0b1520', 'horizon-color': '#2b3b4d', 'fog-color': '#10161e', 'sky-horizon-blend': 0.5, 'horizon-fog-blend': 0.7, 'fog-ground-blend': 0.25},
    sources: {
      imagery: {type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 17, attribution: 'Imagery © Esri & contributors'},
      dem: {type: 'raster-dem', tiles: ['https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png'], tileSize: 256, encoding: 'terrarium', maxzoom: 15, attribution: 'Elevation: AWS Terrain Tiles'},
      shade: {type: 'raster-dem', tiles: ['https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png'], tileSize: 256, encoding: 'terrarium', maxzoom: 15}
    },
    layers: [
      {id: 'imagery', type: 'raster', source: 'imagery', paint: {'raster-brightness-max': 0.78, 'raster-saturation': -0.28, 'raster-contrast': 0.12}},
      {id: 'hillshade', type: 'hillshade', source: 'shade', paint: {'hillshade-shadow-color': '#000000', 'hillshade-highlight-color': '#9fb0c4', 'hillshade-accent-color': '#000000', 'hillshade-exaggeration': 0.35, 'hillshade-illumination-direction': 315}}
    ]
  };
}
const EMPTY = {type: 'FeatureCollection', features: []};
const initial = id => pendingSources.get(id) || EMPTY;

function addMapContent() {
  for (const id of ['arrival', 'edges', 'hotspots', 'perimeter', 'forecast', 'cones']) map.addSource(id, {type: 'geojson', data: initial(id)});
  const c = state.cursor;
  map.addLayer({id: 'burn-fill', type: 'fill', source: 'arrival', filter: M.cumulativeFilter(c), paint: {'fill-color': '#1c1210', 'fill-opacity': 0.66, 'fill-antialias': false}});
  map.addLayer({id: 'recent-fill', type: 'fill', source: 'arrival', filter: M.recentFilter(c, state.recentHours), paint: {'fill-color': '#ff4a18', 'fill-opacity': 0.5, 'fill-antialias': false}});
  map.addLayer({id: 'edge-old', type: 'line', source: 'edges', filter: M.oldBoundaryFilter(c, state.recentHours), paint: {'line-color': '#c0592a', 'line-width': 1.1, 'line-opacity': 0.85}});
  map.addLayer({id: 'edge-glow', type: 'line', source: 'edges', filter: M.recentBoundaryFilter(c, state.recentHours), paint: {'line-color': '#ff6a1a', 'line-width': 7, 'line-blur': 5, 'line-opacity': 0.55}});
  map.addLayer({id: 'edge-recent', type: 'line', source: 'edges', filter: M.recentBoundaryFilter(c, state.recentHours), paint: {'line-color': '#ffc46b', 'line-width': 1.7, 'line-opacity': 0.95}});
  map.addLayer({id: 'perimeter-fill', type: 'fill', source: 'perimeter', layout: {visibility: 'none'}, paint: {'fill-color': '#ffd36b', 'fill-opacity': 0.06}});
  map.addLayer({id: 'perimeter-line', type: 'line', source: 'perimeter', layout: {visibility: 'none'}, paint: {'line-color': '#ffd36b', 'line-width': 1.8, 'line-dasharray': [3, 2]}});
  addForecastLayers();
  map.addLayer({id: 'cones-fill', type: 'fill', source: 'cones', layout: {visibility: 'none'}, paint: {'fill-color': '#38c7e8', 'fill-opacity': 0.14}});
  map.addLayer({id: 'cones-line', type: 'line', source: 'cones', layout: {visibility: 'none'}, paint: {'line-color': '#38c7e8', 'line-width': 1.4, 'line-dasharray': [2, 2]}});
  const radius = ['interpolate', ['linear'], ['get', 'frpMW'], 0, 3, 20, 5, 100, 8, 400, 11];
  map.addLayer({id: 'firms-glow', type: 'circle', source: 'hotspots', filter: M.passFilter(null), paint: {'circle-radius': ['+', radius, 4], 'circle-color': '#ff6a1a', 'circle-opacity': 0.3, 'circle-blur': 1, 'circle-pitch-alignment': 'map'}});
  map.addLayer({id: 'firms', type: 'circle', source: 'hotspots', filter: M.passFilter(null), paint: {'circle-radius': radius, 'circle-color': '#ffd36b', 'circle-opacity': 0.9, 'circle-stroke-color': '#ff5a1a', 'circle-stroke-width': 1.5, 'circle-pitch-alignment': 'map'}});
  for (const l of ['firms']) {
    map.on('click', l, e => popup(e.lngLat, e.features[0].properties));
    map.on('mouseenter', l, () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', l, () => { map.getCanvas().style.cursor = ''; });
  }
  setSource('cones', {type: 'FeatureCollection', features: M.CAMERA_POSES.map(p => M.coneFeature(p))});
}
function popup(lngLat, p) {
  const t = fmtStamp(p.t);
  new maplibregl.Popup({closeButton: true, maxWidth: '260px'}).setLngLat(lngLat)
    .setHTML(`<b>Foco térmico OBSERVADO</b><br>${t.date} ${t.time} ${t.zone}<br>Fuente: ${p.source}<br>FRP ${M.formatNumber(p.frpMW, 1)} MW · píxel ${p.pixelM} m<br><span style="color:#8d99a9">Centro del píxel de la pasada, no área ni frente.</span>`).addTo(map);
}

function initMap() {
  map = new maplibregl.Map({container: 'map', style: mapStyle(), ...HOME, maxPitch: 80, attributionControl: {compact: true}, canvasContextAttributes: {antialias: true}});
  window.__firetraceMap = map;
  map.addControl(new maplibregl.NavigationControl({visualizePitch: true}), 'top-right');
  map.addControl(new maplibregl.ScaleControl({unit: 'metric'}), 'bottom-right');
  map.on('load', () => {
    map.setTerrain({source: 'dem', exaggeration: 1});
    addMapContent();
    state.mapReady = true; frameFire(0);
    applyVisibility(); paintAll(); mapForecast();
    addCameraPins();
  });
  map.on('error', e => {
    const tile = e?.sourceId === 'imagery' || e?.sourceId === 'dem' || e?.sourceId === 'shade' || e?.tile;
    if (!tile) return;
    state.tileErrors++;
    const chip = $('tiles-chip'); chip.hidden = false;
    chip.textContent = `Algunas teselas del mapa no cargan (${state.tileErrors}). Los datos del incendio siguen visibles.`;
  });
}

// ---------- pintado dependiente del cursor ----------

let paintQueued = false;
function paintAll() {
  if (paintQueued) return;
  paintQueued = true;
  requestAnimationFrame(() => { paintQueued = false; paintNow(); });
}
function paintNow() {
  const c = state.cursor, h = state.recentHours, stamp = fmtStamp(c);
  $('hud-date').textContent = stamp.date; $('hud-time').textContent = stamp.time; $('hud-zone').textContent = stamp.zone;
  $('now-date').textContent = stamp.date; $('now-time').textContent = stamp.time; $('now-zone').textContent = stamp.zone;
  const slider = $('slider'); if (Number(slider.value) !== c) slider.value = c;
  document.title = `${stamp.date} ${stamp.time} ${stamp.zone} · FireTrace Garnet`;
  const pass = M.currentOverpass(derived.overpasses, c);
  if (state.mapReady) {
    map.setFilter('burn-fill', M.cumulativeFilter(c));
    map.setFilter('recent-fill', M.recentFilter(c, h));
    map.setFilter('edge-old', M.oldBoundaryFilter(c, h));
    map.setFilter('edge-glow', M.recentBoundaryFilter(c, h));
    map.setFilter('edge-recent', M.recentBoundaryFilter(c, h));
    const pf = M.passFilter(pass);
    map.setFilter('firms-glow', pf); map.setFilter('firms', pf);
  }
  paintState(pass); paintHudSub(pass);
  paintCursorExtras();
}
function paintHudSub(pass) {
  const sub = $('hud-sub');
  if (!derived.areaSeries) { sub.textContent = dataStatus.arrival?.startsWith?.('error') ? 'Reconstrucción no disponible.' : 'Cargando reconstrucción…'; return; }
  const acres = M.areaAt(derived.areaSeries, state.cursor);
  sub.replaceChildren(el('b', {text: `${M.formatNumber(acres)} acres`}), document.createTextNode(` reconstruidos${pass ? ` · última pasada hace ${M.formatDuration(state.cursor - pass.t)}` : ''}`));
}
function paintState(pass) {
  const kv = $('state-kv'); kv.replaceChildren();
  const row = (k, v, sub, cls) => kv.append(el('dt', {text: k}), el('dd', {class: cls || ''}, document.createTextNode(v), sub ? el('small', {text: sub}) : ''));
  if (derived.areaSeries) {
    const a = M.areaAt(derived.areaSeries, state.cursor), recent = M.areaBetween(derived.areaSeries, state.cursor - state.recentHours * 3600, state.cursor);
    row('Área acumulada', `${M.formatNumber(a)} ac`, `${M.formatNumber(a * 0.404686)} ha · RECONSTRUIDA`);
    row(`Nueva en ${state.recentHours} h`, `${M.formatNumber(recent)} ac`, 'actividad reciente RECONSTRUIDA', 'hot');
  } else row('Área acumulada', '—', dataStatus.arrival?.startsWith?.('error') ? 'capa no disponible' : 'cargando…');
  if (pass) {
    const t = fmtStamp(pass.t);
    row('Pasada FIRMS actual', `${t.time} ${t.zone}`, `${t.date} · ${pass.source}`);
    row('Focos / FRP', `${M.formatNumber(pass.detections)} · ${M.formatNumber(pass.totalFrpMW, 0)} MW`, `hace ${M.formatDuration(state.cursor - pass.t)} · OBSERVADO`);
  } else row('Pasada FIRMS actual', '—', derived.overpasses.length ? 'aún no hay pasadas con detección' : 'cargando…');
  $('state-note').textContent = 'La actividad reciente es la llegada reconstruida con datos posteriores, no un frente físico conocido. El mapa no usa puntos futuros.';
}

// ---------- reproducción y línea de tiempo ----------

function setCursor(sec, {fromPlay = false} = {}) {
  const c = M.clampCursor(sec);
  if (!fromPlay) state.playPos = sec;
  if (c === state.cursor) return;
  state.cursor = c;
  invalidateForecastIfStale();
  paintAll();
}
let rafId = 0, lastTs = 0;
function tick(ts) {
  if (!state.playing) return;
  const dt = Math.min(120, ts - lastTs); lastTs = ts;
  const next = M.advanceCursor(state.playPos, dt, state.speed);
  state.playPos = next.cursor;
  setCursor(next.cursor, {fromPlay: true});
  if (next.ended) { pause(); return; }
  rafId = requestAnimationFrame(tick);
}
function play() {
  if (state.playing) return;
  if (state.cursor >= M.RANGE_END_SEC) { state.playPos = M.RANGE_START_SEC; setCursor(M.RANGE_START_SEC); }
  state.playing = true; lastTs = performance.now(); rafId = requestAnimationFrame(tick);
  $('play').textContent = '❚❚'; $('play').setAttribute('aria-label', 'Pausar');
  refreshForecastControls();
}
function pause() {
  state.playing = false; cancelAnimationFrame(rafId);
  $('play').textContent = '▶'; $('play').setAttribute('aria-label', 'Reproducir');
  refreshForecastControls();
}
const togglePlay = () => state.playing ? pause() : play();

function buildTimeline() {
  const slider = $('slider');
  slider.min = M.RANGE_START_SEC; slider.max = M.RANGE_END_SEC; slider.value = state.cursor;
  slider.addEventListener('input', () => { if (state.playing) pause(); setCursor(Number(slider.value)); });
  const speed = $('speed');
  for (const s of M.SPEEDS) speed.append(el('option', {value: s.hoursPerSec, text: s.label, selected: s.hoursPerSec === state.speed}));
  if (![...speed.options].some(o => Number(o.value) === state.speed)) speed.append(el('option', {value: state.speed, text: `${state.speed} h/s`, selected: true}));
  speed.addEventListener('change', () => { state.speed = Number(speed.value); });
  $('play').addEventListener('click', togglePlay);
  $('step-back').addEventListener('click', () => { if (state.playing) pause(); setCursor(state.cursor - 3600); });
  $('step-fwd').addEventListener('click', () => { if (state.playing) pause(); setCursor(state.cursor + 3600); });
  document.addEventListener('keydown', e => {
    if (e.code === 'Space' && !/^(INPUT|SELECT|BUTTON|TEXTAREA)$/.test(document.activeElement?.tagName || '')) { e.preventDefault(); togglePlay(); }
  });
  const span = M.RANGE_END_SEC - M.RANGE_START_SEC, pos = t => `calc(8px + (100% - 16px) * ${(t - M.RANGE_START_SEC) / span})`;
  const events = $('scrub-events'); events.replaceChildren();
  const seen = new Map();
  for (const ev of M.EVENTS) {
    const t = M.parseUtc(ev.utc), alt = seen.get(t) || 0; seen.set(t, alt + 1);
    const mark = el('button', {class: `ev-mark ${ev.tone}${alt ? ' alt' : ''}`, title: `${ev.label} — ${ev.detail}`, 'aria-label': `${ev.label}: ${ev.detail}`, onclick: () => { if (state.playing) pause(); setCursor(t); }});
    mark.style.left = pos(t); events.append(mark);
  }
  const axis = $('scrub-axis'); axis.replaceChildren();
  for (let d = 0; d <= 19; d += 1) {
    const t = M.RANGE_START_SEC + d * 86400;
    if (d % 2 && d !== 19) continue;
    const s = el('span', {text: `${new Date(t * 1000).getUTCDate()} ${['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep'][new Date(t * 1000).getUTCMonth()]}`});
    s.style.left = pos(t); axis.append(s);
  }
}
function buildEventList() {
  const list = $('event-list'); list.replaceChildren();
  for (const ev of M.EVENTS) list.append(el('li', {}, el('button', {class: ev.tone, onclick: () => { if (state.playing) pause(); setCursor(M.parseUtc(ev.utc)); }}, el('i'), el('span', {}, el('strong', {text: ev.label}), el('small', {text: ev.detail})))));
}

// ---------- controles de vista ----------

function bindView() {
  $('view-reset').addEventListener('click', () => {
    const forecast = forecastTracker.state;
    if (layerOn.forecast && forecast?.status === 'ready') return fitForecast(forecast.result.features);
    frameFire(900);
    $('view-flat').setAttribute('aria-pressed', 'false'); $('view-tilt').setAttribute('aria-pressed', 'true');
  });
  $('view-flat').addEventListener('click', () => { map?.easeTo({pitch: 0, bearing: 0, duration: 700}); $('view-flat').setAttribute('aria-pressed', 'true'); $('view-tilt').setAttribute('aria-pressed', 'false'); });
  $('view-tilt').addEventListener('click', () => { map?.easeTo({pitch: HOME.pitch, bearing: HOME.bearing, duration: 700}); $('view-tilt').setAttribute('aria-pressed', 'true'); $('view-flat').setAttribute('aria-pressed', 'false'); });
  $('zone-utc').addEventListener('click', () => setZone('UTC'));
  $('zone-pdt').addEventListener('click', () => setZone('PDT'));
  $('recent-hours').addEventListener('change', e => { state.recentHours = Number(e.target.value); updateLegend(); paintAll(); });
  $('legend-toggle').addEventListener('click', () => {
    const legend = document.querySelector('.legend'), collapsed = legend.classList.toggle('collapsed');
    $('legend-toggle').setAttribute('aria-expanded', String(!collapsed)); $('legend-toggle').textContent = collapsed ? '+' : '–';
    $('legend-toggle').setAttribute('aria-label', collapsed ? 'Desplegar leyenda' : 'Plegar leyenda');
  });
}
function setZone(zone) {
  state.zone = zone;
  $('zone-utc').setAttribute('aria-pressed', String(zone === 'UTC')); $('zone-pdt').setAttribute('aria-pressed', String(zone === 'PDT'));
  paintAll();
}

// ---------- gráficos (SVG, mismo eje temporal y cursor alineado) ----------

const CH = {l: 38, r: 8, t: 6, b: 15};
const charts = {};
const SPAN = M.RANGE_END_SEC - M.RANGE_START_SEC;
const niceMax = v => { const p = 10 ** Math.floor(Math.log10(v || 1)), n = v / p; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p; };

function chartFrame(id) {
  const svg = $(id), w = Math.max(120, svg.clientWidth), h = Math.max(50, svg.clientHeight);
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`); svg.replaceChildren();
  const x = t => CH.l + ((t - M.RANGE_START_SEC) / SPAN) * (w - CH.l - CH.r);
  return {svg, w, h, x, y0: h - CH.b, y1: CH.t};
}
function axisDays(f) {
  for (let d = 0; d <= 19; d += 5) {
    const t = M.RANGE_START_SEC + d * 86400, label = M.formatStamp(t).date.slice(0, 6);
    f.svg.append(svgEl('line', {x1: f.x(t), x2: f.x(t), y1: f.y1, y2: f.y0, class: 'grid'}));
    svgText(f.svg, {x: f.x(t), y: f.h - 3, 'text-anchor': d === 0 ? 'start' : 'middle'}, label);
  }
}
function yTicks(f, max, scale, fmt) {
  for (const v of [0, max / 2, max]) {
    const y = f.y0 - scale(v) * (f.y0 - f.y1);
    f.svg.append(svgEl('line', {x1: CH.l, x2: f.w - CH.r, y1: y, y2: y, class: 'grid'}));
    svgText(f.svg, {x: CH.l - 4, y: y + 3, 'text-anchor': 'end'}, fmt(v));
  }
}
function finishChart(name, f) {
  const future = svgEl('rect', {class: 'future', y: f.y1, height: f.y0 - f.y1, fill: '#0a0d11', 'fill-opacity': '.62'});
  const line = svgEl('line', {y1: f.y1 - 2, y2: f.y0, stroke: '#fff', 'stroke-width': '1.5'});
  const dot = svgEl('circle', {r: 3, fill: '#fff', stroke: '#ff6a1a', 'stroke-width': '1.5'});
  f.svg.append(future, line, dot);
  charts[name] = {f, future, line, dot};
  f.svg.onpointerdown = e => { f.svg.setPointerCapture(e.pointerId); scrubFromChart(f, e); f.svg.onpointermove = ev => scrubFromChart(f, ev); };
  f.svg.onpointerup = f.svg.onpointercancel = () => { f.svg.onpointermove = null; };
}
function scrubFromChart(f, e) {
  const rect = f.svg.getBoundingClientRect(), px = (e.clientX - rect.left) * (f.w / rect.width);
  if (state.playing) pause();
  setCursor(M.RANGE_START_SEC + Math.min(1, Math.max(0, (px - CH.l) / (f.w - CH.l - CH.r))) * SPAN);
}
function drawAreaChart() {
  const f = chartFrame('chart-area'); if (!f.svg.clientWidth) return;
  const series = derived.areaSeries;
  if (!series) { svgText(f.svg, {x: f.w / 2, y: f.h / 2, 'text-anchor': 'middle'}, dataStatus.arrival?.startsWith?.('error') ? 'Serie no disponible' : 'Cargando…'); return; }
  const comps = M.areaComparisons(data.summary), maxA = niceMax(Math.max(series.acres[series.acres.length - 1], ...comps.map(c => c.reportedAcres)));
  const sy = v => v / maxA;
  axisDays(f); yTicks(f, maxA, sy, v => v >= 1000 ? `${v / 1000}k` : String(v));
  const dailyRows = (data.daily?.features || []).map(d => ({end: Date.parse(d.properties.endPdt) / 1000, acres: d.properties.reconstructedAcres}));
  let prev = 0;
  dailyRows.forEach(d => {
    const grown = d.acres - prev; prev = d.acres;
    const x0 = f.x(d.end - 86400), x1 = f.x(d.end), hgt = Math.max(0, sy(grown)) * (f.y0 - f.y1);
    f.svg.append(svgEl('rect', {x: x0 + 1, width: Math.max(1, x1 - x0 - 2), y: f.y0 - hgt, height: hgt, fill: '#ff6a1a', 'fill-opacity': '.28'}));
  });
  let d = '';
  for (let t = M.RANGE_START_SEC; t <= M.RANGE_END_SEC; t += 3600) d += `${d ? 'L' : 'M'}${f.x(t).toFixed(1)},${(f.y0 - sy(M.areaAt(series, t)) * (f.y0 - f.y1)).toFixed(1)}`;
  f.svg.append(svgEl('path', {d: d + `L${f.x(M.RANGE_END_SEC)},${f.y0}L${f.x(M.RANGE_START_SEC)},${f.y0}Z`, fill: '#ff6a1a', 'fill-opacity': '.12'}));
  f.svg.append(svgEl('path', {d, fill: 'none', stroke: '#ff8a3d', 'stroke-width': '1.8'}));
  for (const c of comps) {
    const x = f.x(M.parseUtc(c.atUtc)), y = f.y0 - sy(c.reportedAcres) * (f.y0 - f.y1);
    const mark = svgEl('path', {d: `M${x},${y - 4.5}L${x + 4.5},${y}L${x},${y + 4.5}L${x - 4.5},${y}Z`, fill: '#0a0d11', stroke: '#38c7e8', 'stroke-width': '1.6'});
    mark.append(svgEl('title')); mark.firstChild.textContent = `Reportado ${M.formatNumber(c.reportedAcres)} ac frente a ${M.formatNumber(c.reconstructedAcres)} ac reconstruidos (${M.formatNumber(c.ratio, 2)}×)`;
    f.svg.append(mark);
    svgText(f.svg, {x: x + 7, y: y + 3, fill: '#7fdcf5', style: 'fill:#7fdcf5'}, `${M.formatNumber(c.ratio, 2)}×`);
  }
  finishChart('area', f);
}
function drawFrpChart() {
  const f = chartFrame('chart-frp'); if (!f.svg.clientWidth) return;
  const passes = derived.overpasses;
  if (!passes.length) { svgText(f.svg, {x: f.w / 2, y: f.h / 2, 'text-anchor': 'middle'}, dataStatus.overpasses?.startsWith?.('error') ? 'Serie no disponible' : 'Cargando…'); return; }
  const max = Math.max(...passes.map(p => p.totalFrpMW)), sy = v => Math.sqrt(v / max);
  axisDays(f);
  for (const v of [0, max * 0.1, max]) {
    const y = f.y0 - sy(v) * (f.y0 - f.y1);
    f.svg.append(svgEl('line', {x1: CH.l, x2: f.w - CH.r, y1: y, y2: y, class: 'grid'}));
    svgText(f.svg, {x: CH.l - 4, y: y + 3, 'text-anchor': 'end'}, v >= 1000 ? `${M.formatNumber(v / 1000, v >= 10000 ? 0 : 1)}k` : String(Math.round(v)));
  }
  for (const p of passes) {
    const hgt = sy(p.totalFrpMW) * (f.y0 - f.y1), x = f.x(p.t);
    const bar = svgEl('rect', {x: x - 0.9, width: 1.8, y: f.y0 - hgt, height: hgt, fill: p.source.startsWith('MODIS') ? '#ffd36b' : '#ff6a1a'});
    f.svg.append(bar);
  }
  const frp = M.EVENTS.find(e => e.id === 'frp');
  f.svg.append(svgEl('line', {x1: f.x(M.parseUtc(frp.utc)), x2: f.x(M.parseUtc(frp.utc)), y1: f.y1, y2: f.y0, stroke: '#8fe0a0', 'stroke-dasharray': '2 2', 'stroke-width': '1'}));
  svgText(f.svg, {x: f.w - CH.r, y: f.y1 + 8, 'text-anchor': 'end', style: 'fill:#ffd36b'}, 'MODIS');
  svgText(f.svg, {x: f.w - CH.r - 38, y: f.y1 + 8, 'text-anchor': 'end', style: 'fill:#ff8a3d'}, 'VIIRS');
  finishChart('frp', f);
}
function drawWindChart() {
  const f = chartFrame('chart-wind'); if (!f.svg.clientWidth) return;
  const hours = derived.weatherHours;
  if (!hours.length) { svgText(f.svg, {x: f.w / 2, y: f.h / 2, 'text-anchor': 'middle'}, dataStatus.weather?.startsWith?.('error') ? 'Serie no disponible' : 'Cargando…'); return; }
  const max = niceMax(Math.max(...hours.map(h => h.gustMps ?? h.windSpeedMps))), sy = v => v / max;
  axisDays(f); yTicks(f, max, sy, v => String(v));
  const path = key => hours.map((h, i) => `${i ? 'L' : 'M'}${f.x(M.parseUtc(h.timeUtc)).toFixed(1)},${(f.y0 - sy(h[key]) * (f.y0 - f.y1)).toFixed(1)}`).join('');
  f.svg.append(svgEl('path', {d: path('gustMps'), fill: 'none', stroke: '#38c7e8', 'stroke-opacity': '.4', 'stroke-width': '1', 'stroke-dasharray': '2 2'}));
  f.svg.append(svgEl('path', {d: path('windSpeedMps'), fill: 'none', stroke: '#38c7e8', 'stroke-width': '1.5'}));
  hours.forEach((h, i) => {
    if (i % 12) return;
    const x = f.x(M.parseUtc(h.timeUtc)), y = f.y1 + 4, to = (h.windFromDeg + 180) * Math.PI / 180;
    f.svg.append(svgEl('path', {d: `M${x - Math.sin(to) * 3.5},${y + Math.cos(to) * 3.5}L${x + Math.sin(to) * 3.5},${y - Math.cos(to) * 3.5}`, stroke: '#7fdcf5', 'stroke-width': '1.1', 'marker-end': ''}));
    f.svg.append(svgEl('circle', {cx: x + Math.sin(to) * 3.5, cy: y - Math.cos(to) * 3.5, r: 1.3, fill: '#7fdcf5'}));
  });
  finishChart('wind', f);
}
function drawCharts() { drawAreaChart(); drawFrpChart(); drawWindChart(); paintChartCursor(); }
function paintChartCursor() {
  for (const c of Object.values(charts)) {
    const x = c.f.x(state.cursor);
    c.line.setAttribute('x1', x); c.line.setAttribute('x2', x);
    c.future.setAttribute('x', x); c.future.setAttribute('width', Math.max(0, c.f.w - CH.r - x));
    c.dot.setAttribute('cx', x);
  }
  const area = charts.area;
  if (area && derived.areaSeries) {
    const max = niceMax(Math.max(derived.areaSeries.acres.at(-1), ...M.areaComparisons(data.summary).map(c => c.reportedAcres)));
    area.dot.setAttribute('cy', area.f.y0 - (M.areaAt(derived.areaSeries, state.cursor) / max) * (area.f.y0 - area.f.y1));
  } else area?.dot.setAttribute('cy', -10);
  charts.frp?.dot.setAttribute('cy', -10); charts.wind?.dot.setAttribute('cy', -10);
  const wx = charts.wind, hour = M.weatherAt(derived.weatherHours, state.cursor);
  if (wx && hour) { const max = niceMax(Math.max(...derived.weatherHours.map(h => h.gustMps ?? h.windSpeedMps))); wx.dot.setAttribute('cy', wx.f.y0 - (hour.windSpeedMps / max) * (wx.f.y0 - wx.f.y1)); }
}
let resizeTimer = 0;
function observeCharts() {
  new ResizeObserver(() => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { drawCharts(); map?.resize(); }, 80); }).observe($('charts'));
}

// ---------- meteorología ----------

let weatherKey = '';
function paintWeather() {
  const body = $('weather-body'), hour = M.weatherAt(derived.weatherHours, state.cursor);
  const key = hour ? hour.timeUtc + state.zone : (derived.weatherHours.length ? 'none' : dataStatus.weather || 'wait');
  if (key === weatherKey) return; weatherKey = key;
  body.replaceChildren();
  if (!derived.weatherHours.length) { body.append(el('p', {class: 'muted', text: dataStatus.weather?.startsWith?.('error') ? 'Meteorología no disponible.' : 'Cargando…'})); return; }
  if (!hour) { body.append(el('p', {class: 'muted', text: 'Sin dato modelado para este instante; no se extrapola fuera del rango.'})); return; }
  const to = (hour.windFromDeg + 180) * Math.PI / 180, ax = 37 + Math.sin(to) * 24, ay = 37 - Math.cos(to) * 24, bx = 37 - Math.sin(to) * 24, by = 37 + Math.cos(to) * 24;
  const dial = svgEl('svg', {viewBox: '0 0 74 74', class: 'wind-dial', role: 'img', 'aria-label': `Viento desde ${M.compassPoint(hour.windFromDeg)}`});
  dial.append(svgEl('circle', {cx: 37, cy: 37, r: 33, fill: 'none', stroke: '#2c3744'}));
  svgText(dial, {x: 37, y: 11, 'text-anchor': 'middle', style: 'fill:#8d99a9;font-size:9px'}, 'N');
  dial.append(svgEl('line', {x1: bx, y1: by, x2: ax, y2: ay, stroke: '#38c7e8', 'stroke-width': '2.5', 'stroke-linecap': 'round'}));
  const ang = Math.atan2(ay - by, ax - bx);
  dial.append(svgEl('path', {d: `M${ax},${ay}L${ax - 8 * Math.cos(ang - 0.45)},${ay - 8 * Math.sin(ang - 0.45)}L${ax - 8 * Math.cos(ang + 0.45)},${ay - 8 * Math.sin(ang + 0.45)}Z`, fill: '#38c7e8'}));
  const metric = (value, unit, label, wide) => el('div', {class: 'metric' + (wide ? ' wide' : '')}, el('b', {text: value}), el('span', {text: `${unit} ${label}`.trim()}));
  const stamp = M.formatStamp(M.parseUtc(hour.timeUtc), state.zone);
  body.append(el('div', {class: 'weather-grid'}, dial,
    metric(`${M.compassPoint(hour.windFromDeg)} ${hour.windFromDeg}°`, '', 'viento DESDE'),
    metric(M.formatNumber(hour.windSpeedMps, 1), 'm/s', `· ráfaga ${M.formatNumber(hour.gustMps, 1)}`),
    metric(`${M.formatNumber(hour.tempC, 1)} °C`, '', 'temperatura'),
    metric(`${M.formatNumber(hour.rhPct)} %`, '', 'humedad relativa del aire')));
  body.append(el('p', {class: 'weather-note', text: `Hora del modelo: ${stamp.date} ${stamp.time} ${stamp.zone} (última hora ≤ cursor). Open-Meteo Historical, Best Match, un punto a ${M.formatNumber(data.weather?.point?.elevationM)} m: modelo, no estación medida. La humedad relativa no es humedad del combustible.`}));
}

// ---------- cámaras ----------

let cameraKey = '', cameraMarkers = [];
const CAMERA_NAME = id => data.incident?.cameras.find(c => c.id === id)?.name || id;
function selectCamera(id) { state.selectedCamera = state.selectedCamera === id ? null : id; cameraMarkers.forEach(m => m.pin.setAttribute('aria-pressed', String(m.id === state.selectedCamera))); cameraKey = ''; paintCameras(); if (state.selectedCamera) $('panel-camera').scrollIntoView({block: 'nearest', behavior: 'smooth'}); }
const deltaText = d => `${d >= 0 ? '+' : '−'}${M.formatDuration(d)}`;
const detailDelta = d => `${d >= 0 ? 'Posterior' : 'Anterior'} al cursor en ${M.formatDuration(d)}${Math.abs(d) > 1800 ? ' · no hay fotograma más cercano; la imagen no corresponde al instante del cursor' : ''}`;
function updateCameraDeltas(near) {
  for (const n of near) {
    if (!n) continue;
    const c = document.querySelector(`[data-delta-card="${n.frame.cameraId}"]`); if (c) c.textContent = deltaText(n.deltaSec);
    const d = document.querySelector(`[data-delta-detail="${n.frame.cameraId}"]`); if (d) d.textContent = detailDelta(n.deltaSec);
  }
}
function paintCameras() {
  const body = $('camera-body'), inc = data.incident;
  if (!inc) { if (cameraKey !== 'wait') { cameraKey = 'wait'; body.replaceChildren(el('p', {class: 'muted', text: dataStatus.incident?.startsWith?.('error') ? 'Evidencia de cámaras no disponible.' : 'Cargando evidencia…'})); } return; }
  const near = inc.cameras.map(c => M.nearestFrame(inc.frames, c.id, state.cursor));
  const key = near.map(n => n?.frame.id).join('|') + '|' + state.selectedCamera + '|' + state.zone;
  if (key === cameraKey) { updateCameraDeltas(near); return; }
  cameraKey = key;
  body.replaceChildren();
  const grid = el('div', {class: 'cam-grid'});
  near.forEach((n, i) => {
    const cam = inc.cameras[i]; if (!n) return;
    const st = M.formatStamp(n.utcSec, state.zone);
    grid.append(el('button', {class: 'cam-card', 'aria-pressed': String(state.selectedCamera === cam.id), onclick: () => selectCamera(cam.id), 'aria-label': `${cam.name}: fotograma más cercano, ${st.date} ${st.time} ${st.zone}`},
      el('img', {src: n.frame.imagePath, alt: `${cam.name}, ${st.time} ${st.zone}`, loading: 'lazy'}),
      el('span', {class: 'cam-meta'}, el('b', {text: cam.name}), document.createTextNode(`${st.date} ${st.time} ${st.zone} · `), el('span', {'data-delta-card': cam.id, text: deltaText(n.deltaSec)}))));
  });
  body.append(grid);
  const sel = near.find(n => n?.frame.cameraId === state.selectedCamera);
  if (!sel) { body.append(el('p', {class: 'muted small', text: 'Toca una cámara (aquí o en el mapa) para ver el fotograma más cercano al cursor, su fecha real y la descripción guardada de NVIDIA Cosmos.'})); return; }
  const cam = inc.cameras.find(c => c.id === sel.frame.cameraId), real = M.formatStamp(sel.utcSec, 'UTC'), pdt = M.formatStamp(sel.utcSec, 'PDT');
  const a = sel.frame.analysis;
  const detail = el('div', {class: 'cam-detail'});
  detail.append(el('img', {src: sel.frame.imagePath, alt: `${cam.name}, fotograma ${sel.frame.id}`}));
  detail.append(el('div', {class: 'stamp'}, el('b', {text: `${real.date} ${real.time} UTC`}), document.createTextNode(` · hora impresa ${sel.frame.printedTime.slice(11, 19)} (supuesto PDT = ${pdt.time} PDT)`)));
  detail.append(el('div', {class: 'delta', 'data-delta-detail': cam.id, text: detailDelta(sel.deltaSec)}));
  detail.append(el('p', {text: a?.content || 'Sin descripción guardada para este fotograma.'}));
  if (sel.frame.reviewNotes?.length) detail.append(el('p', {class: 'review-notes', text: sel.frame.reviewNotes.join(' ')}));
  detail.append(el('div', {class: 'tiny', text: a ? `Descripción guardada de NVIDIA Cosmos (${a.model}, ${a.analyzedAt}); requiere revisión. La zona horaria de la cámara no está verificada.` : 'La zona horaria de la cámara no está verificada.'}));
  const video = el('div'), actions = el('div', {class: 'cam-actions'}, el('button', {text: 'Ver clip', onclick: ev => {
    const v = el('video', {controls: true, playsinline: true, preload: 'metadata', src: cam.clipPath});
    v.addEventListener('error', () => { video.replaceChildren(el('p', {class: 'tiny', text: 'El clip no está disponible en este servidor.'})); });
    v.addEventListener('loadedmetadata', () => { v.currentTime = Math.max(0, sel.frame.sourceVideoSecond - cam.sourceClipStart); });
    video.replaceChildren(v); ev.target.disabled = true;
  }}), el('button', {text: 'Ir a su hora', onclick: () => { if (state.playing) pause(); setCursor(sel.utcSec); }}));
  detail.append(actions, video);
  body.append(detail);
}
function addCameraPins() {
  if (!data.incident || !state.mapReady || cameraMarkers.length) return;
  for (const pose of M.CAMERA_POSES) {
    const cam = data.incident.cameras.find(c => c.id === pose.cameraId); if (!cam) continue;
    const pin = el('button', {class: 'cam-pin', 'aria-label': `Cámara ${cam.name}`, 'aria-pressed': 'false', title: `${cam.name} · posición candidata, no verificada`}, el('span', {class: 'cam-label', text: cam.name}));
    pin.addEventListener('click', e => { e.stopPropagation(); selectCamera(cam.id); });
    cameraMarkers.push({id: cam.id, pin, marker: new maplibregl.Marker({element: pin}).setLngLat([pose.lon, pose.lat]).addTo(map)});
  }
}

// ---------- procedencia ----------

function paintProvenance() {
  const body = $('provenance-body'); body.replaceChildren();
  const s = data.summary;
  if (!s) { body.append(el('p', {class: 'muted', text: dataStatus.summary?.startsWith?.('error') ? 'Resumen no disponible.' : 'Cargando…'})); return; }
  const comps = M.areaComparisons(s), ratios = comps.map(c => `${M.formatNumber(c.ratio, 2)}× el ${M.formatStamp(M.parseUtc(c.atUtc), 'PDT').date.slice(0, 6)}`).join(' · ');
  body.append(el('p', {class: 'prov-warn', text: `La reconstrucción supera la superficie reportada (${ratios}; rango 1,4–1,5×). Es retrospectiva y está recortada con el perímetro final de dic 2025: no sustituye a un perímetro observado.`}));
  body.append(el('p', {class: 'prov-warn', text: `Cronología sin resolver: WFIGS registra el descubrimiento el 24 ago a las 07:10 UTC, CAL FIRE publica 14:13 sin zona horaria confirmada y la primera detección FIRMS es ${s.firstDetectionUtc?.slice(11, 16) || '—'} UTC. Ninguna fija la ignición.`}));
  const lims = data.arrival?._provenance?.limitations || [];
  body.append(el('details', {}, el('summary', {text: 'Más sobre los datos'}), el('ul', {class: 'prov-list'},
    el('li', {text: `${M.formatNumber(s.counts.detections)} detecciones FIRMS en ${M.formatNumber(s.counts.overpasses)} pasadas; ${M.formatNumber(s.counts.arrivalCells)} celdas de ${s.parameters.cellM} m.`}),
    ...lims.map(t => el('li', {text: t})),
    el('li', {text: 'Meteorología: modelo Open-Meteo en un punto, no una estación medida.'}),
    el('li', {text: 'Los conos de cámara son hipótesis (azimut impreso supuesto, FOV 65,1° a zoom 1 escalado por focal); no son un campo de visión verificado.'}))));
}

// ---------- pronóstico desde el frente ----------

const FC_LAYERS = ['fc-model-fill', 'fc-overlap-fill', 'fc-over-fill', 'fc-under-fill', 'fc-initial-line', 'fc-model-line', 'fc-ref-line'];
function addForecastLayers() {
  const role = r => ['==', ['get', 'role'], r];
  const fill = (id, r, color, opacity) => map.addLayer({id, type: 'fill', source: 'forecast', filter: role(r), paint: {'fill-color': color, 'fill-opacity': opacity, 'fill-antialias': true}});
  const line = (id, r, paint) => map.addLayer({id, type: 'line', source: 'forecast', filter: role(r), paint});
  fill('fc-model-fill', 'modeled-extent', '#e0409a', 0.3);
  fill('fc-overlap-fill', 'overlap', '#ffb8e0', 0.28);
  fill('fc-over-fill', 'overprediction', '#ff7a1a', 0.55);
  fill('fc-under-fill', 'underprediction', '#c47cff', 0.5);
  line('fc-initial-line', 'initial-extent', {'line-color': '#ffffff', 'line-width': 1.4, 'line-dasharray': [2, 2], 'line-opacity': 0.9});
  line('fc-model-line', 'modeled-extent', {'line-color': '#ff5fb3', 'line-width': 2});
  line('fc-ref-line', 'reference-extent', {'line-color': '#38c7e8', 'line-width': 2.6});
}
function setForecastVisibility() {
  if (!state.mapReady) return;
  for (const id of FC_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', layerOn.forecast ? 'visible' : 'none');
}
function mapForecast() {
  const st = forecastTracker.state;
  setSource('forecast', st?.status === 'ready' ? {type: 'FeatureCollection', features: st.result.features} : EMPTY);
  setForecastVisibility(); updateLegend(); renderLayerRows();
}
function fitForecast(features) {
  const b = M.featureBounds(features); if (!b || !state.mapReady) return;
  map.fitBounds([[b.minx, b.miny], [b.maxx, b.maxy]], {
    pitch: map.getPitch(), bearing: map.getBearing(),
    padding: {top: 80, bottom: 70, left: 35, right: 35}, maxZoom: 11.6, duration: 1000
  });
}
function setForecastStatus(text, kind = '') { const n = $('forecast-status'); n.textContent = text; n.className = 'forecast-status ' + kind; }
function refreshForecastControls() {
  const loading = forecastTracker.state?.status === 'loading', btn = $('forecast-run');
  btn.disabled = loading; btn.textContent = loading ? 'Proyectando…' : 'Proyectar desde este frente';
  document.querySelectorAll('.horizon button').forEach(b => { b.setAttribute('aria-pressed', String(Number(b.dataset.h) === state.horizon)); });
}
function invalidateForecastIfStale() {
  if (!forecastTracker.sync(state.cursor, state.horizon)) return;
  $('forecast-card').replaceChildren();
  mapForecast(); refreshForecastControls();
  setForecastStatus('El cursor cambió: la proyección anterior se ocultó. Proyecta de nuevo desde este instante.');
}
function bindForecast() {
  document.querySelectorAll('.horizon button').forEach(b => b.addEventListener('click', () => {
    state.horizon = Number(b.dataset.h); invalidateForecastIfStale(); refreshForecastControls();
  }));
  $('forecast-run').addEventListener('click', runForecast);
  refreshForecastControls();
}
async function runForecast() {
  if (state.playing) pause();
  let request;
  try { request = M.forecastBody(state.cursor, state.horizon); } catch (e) { setForecastStatus(e.message, 'err'); return; }
  const controller = new AbortController(), ticket = forecastTracker.begin(request, controller);
  $('forecast-card').replaceChildren(); mapForecast(); refreshForecastControls();
  const when = M.formatStamp(state.cursor, state.zone);
  setForecastStatus(`Proyectando ${request.horizonHours} h desde ${when.date} ${when.time} ${when.zone}…`, 'busy');
  try {
    const result = await M.requestForecast(request, (...a) => fetch(...a), controller.signal);
    if (!forecastTracker.accept(ticket, result)) return; // respuesta obsoleta
    setForecastStatus(`Proyección de ${request.horizonHours} h lista. Solo vale para el instante ${when.time} ${when.zone}; si mueves el cursor se oculta.`);
    renderForecastCard(result.top); mapForecast(); fitForecast(result.features);
  } catch (e) {
    if (e?.name === 'AbortError') return;
    if (forecastTracker.fail(ticket, e)) setForecastStatus(e.message || 'No se pudo completar la proyección.', 'err');
  }
  refreshForecastControls();
}
const listify = v => v == null ? [] : Array.isArray(v) ? v.map(x => typeof x === 'string' ? x : JSON.stringify(x)) : typeof v === 'object' ? Object.entries(v).map(([k, x]) => `${k}: ${typeof x === 'object' ? JSON.stringify(x) : x}`) : [String(v)];
function weatherLines(w) {
  if (!w || typeof w !== 'object') return [];
  const t = w.timeUtc ? M.formatStamp(M.parseUtc(w.timeUtc), state.zone) : null;
  return [`Primera hora: viento DESDE ${w.windFromDeg}° (${M.compassPoint(w.windFromDeg)}), ${M.formatNumber(w.windSpeedMps, 1)} m/s, ráfaga ${M.formatNumber(w.gustMps, 1)} m/s (no se usa), HR ${M.formatNumber(w.rhPct)} %, ${M.formatNumber(w.tempC, 1)} °C${t ? ` · ${t.date} ${t.time} ${t.zone}` : ''}.`,
    `${w.hoursUsed ?? '?'} horas de viento histórico modelado (un punto), constante dentro de cada hora. Sin humedad del combustible.`];
}
function renderForecastCard(top) {
  const card = $('forecast-card'), m = top.metrics, valid = M.formatStamp(M.parseUtc(top.validUtc), state.zone);
  const badges = el('div', {class: 'fc-badges'}, el('span', {class: 'fc-badge warn', text: top.validated ? 'VALIDACIÓN DECLARADA' : 'NO VALIDADO'}), el('span', {class: 'fc-badge info', text: 'vs RECONSTRUCCIÓN'}));
  if (top.domainBoundaryReached) badges.append(el('span', {class: 'fc-badge warn', text: 'ALCANZÓ EL LÍMITE DEL DOMINIO'}));
  if (!top.referenceAvailable) badges.append(el('span', {class: 'fc-badge info', text: 'SIN REFERENCIA POSTERIOR'}));
  card.replaceChildren(badges);
  if (top.label) card.append(el('p', {class: 'fc-label', text: top.label}));
  if (top.domainBoundaryReached) card.append(el('p', {class: 'prov-warn', text: 'La proyección alcanzó el límite del dominio de cálculo: el resultado está truncado y las métricas subestiman o distorsionan la comparación.'}));
  const stat = (label, value, cls) => el('div', {class: 'fc-stat ' + (cls || '')}, el('b', {text: value}), el('span', {text: label}));
  if (top.referenceAvailable) {
    card.append(el('div', {class: 'fc-grid'},
      stat('IoU total', M.formatNumber(m.iou, 2)), stat('IoU del crecimiento', m.growthIou == null ? '—' : M.formatNumber(m.growthIou, 2)),
      stat('Sobrepredicción (ha)', M.formatNumber(m.overpredictionHa), 'over'), stat('Subpredicción (ha)', M.formatNumber(m.underpredictionHa), 'under'),
      stat('Predicho (ha)', M.formatNumber(m.predictedHa)), stat('Referencia (ha)', M.formatNumber(m.referenceHa))));
  } else card.append(el('div', {class: 'fc-grid'}, stat('Superficie inicial (ha)', M.formatNumber(m.initialHa)), stat('Predicho (ha)', M.formatNumber(m.predictedHa))));
  const noGrowth = top.referenceAvailable && m.referenceHa != null && m.initialHa != null && m.referenceHa <= m.initialHa * 1.001;
  card.append(el('p', {class: 'fc-compare'}, document.createTextNode(`Válida hasta ${valid.date} ${valid.time} ${valid.zone} (+${top.horizonHours} h). `), el('strong', {text: 'Compara el modelo con la RECONSTRUCCIÓN posterior, no con una validación independiente.'}), document.createTextNode(noGrowth ? ' La referencia no añade área nueva: eso no demuestra que el fuego se detuviera.' : '')));
  if (m.growthIou == null && m.growthIouReason) card.append(el('p', {class: 'fc-compare', text: `IoU del crecimiento no disponible: ${m.growthIouReason}`}));
  const more = (title, items) => items.length ? el('details', {class: 'fc-more'}, el('summary', {text: title}), el('ul', {}, ...items.map(t => el('li', {text: t})))) : '';
  card.append(more('Supuestos', listify(top.assumptions)), more('Límites', listify(top.limitations)), more('Meteorología usada', weatherLines(top.weather)), more('Diagnóstico', listify(top.diagnostics)), more('Procedencia', listify(top.provenance)));
}

// ---------- extras que dependen del cursor ----------

function paintCursorExtras() { paintChartCursor(); paintWeather(); paintCameras(); }

// ---------- arranque ----------

function start() {
  renderLayerRows(); buildTimeline(); buildEventList(); bindView(); paintNow();
  if (window.maplibregl) initMap(); else showData('No se pudo cargar el motor de mapas; la línea de tiempo sigue disponible.');
  loadData('overpasses'); loadData('arrival'); loadData('hotspots'); loadData('weather'); loadData('daily'); loadData('summary');
  loadIncident(); bindForecast(); observeCharts(); drawCharts();
  if (hash.get('play') === '1') play();
}
start();
