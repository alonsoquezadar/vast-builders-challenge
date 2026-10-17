import {mapStyle} from './terrain-style.mjs';
import {readMulticam, incidentToVideo, videoToIncident, clampTime, cameraAtVideo} from './multicam-clock.mjs';

const $ = id => document.getElementById(id);
const HOME = {center: [-120.79, 38.16], zoom: 10.7, pitch: 60, bearing: -22};
let evidence, cursor, map, master, running = false, loading = false, pendingMaster = null;
const entries = new Map();
const stamp = (utc, zone = 'PDT') => new Intl.DateTimeFormat('en-GB', {
  timeZone: zone === 'PDT' ? 'Etc/GMT+7' : 'UTC', day: '2-digit', month: 'short',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
}).format(new Date(utc * 1000)) + ` ${zone}`;
const message = text => { $('playback-status').textContent = text; };

function paintClock() {
  $('shared-time').value = cursor;
  $('incident-clock').textContent = stamp(cursor);
  $('utc-clock').textContent = stamp(cursor, 'UTC');
}

function selectMaster(id) {
  pauseAll(); master = id;
  for (const entry of entries.values()) {
    const selected = entry.camera.id === id;
    entry.card.classList.toggle('selected', selected);
    entry.pin?.classList.toggle('selected', selected);
    entry.choose.setAttribute('aria-pressed', String(selected));
    entry.choose.textContent = selected ? 'Clock camera' : 'Use as clock';
  }
  const lead = entries.get(master);
  $('play-all').disabled = !lead?.ready || Boolean(lead.error);
  if (loading) seekAll(cursor);
}

function pauseAll() {
  running = false;
  for (const entry of entries.values()) if (entry.ready && !entry.error) entry.player.pauseVideo();
}

function seekAll(utc) {
  cursor = clampTime(evidence, utc); paintClock();
  pendingMaster = null;
  for (const entry of entries.values()) {
    if (!entry.ready || entry.error) continue;
    const target = incidentToVideo(entry.camera, cursor);
    entry.player.seekTo(target, true);
    if (entry.camera.id === master) pendingMaster = target;
    entry.status.textContent = 'Seeking to approximately ' + stamp(cursor);
  }
}

function playAll() {
  const lead = entries.get(master);
  if (!lead?.ready || lead.error) { message('Choose a loaded camera as the clock.'); return; }
  if (cursor >= evidence.end - 1) seekAll(evidence.start);
  running = true;
  for (const entry of entries.values()) if (entry.ready && !entry.error) {
    entry.player.mute(); entry.player.playVideo();
  }
  message('Following ' + lead.camera.name + '. Other cameras seek to the same estimated incident time.');
}

function createCards() {
  evidence.cameras.forEach((camera, i) => {
    const card = document.createElement('article'); card.className = 'camera-card';
    const head = document.createElement('div'); head.className = 'camera-heading';
    const title = document.createElement('h3'); title.textContent = `${i + 1}. ${camera.name}`;
    const choose = document.createElement('button'); choose.textContent = 'Use as clock';
    choose.addEventListener('click', () => selectMaster(camera.id)); head.append(title, choose);
    const holder = document.createElement('div'); holder.className = 'camera-video';
    const mount = document.createElement('div'); mount.id = 'youtube-' + camera.id;
    mount.textContent = 'Original YouTube camera segment'; holder.append(mount);
    const status = document.createElement('p'); status.className = 'camera-status';
    status.textContent = 'Timestamped footage · PDT assumed';
    const source = document.createElement('a'); source.target = '_blank'; source.rel = 'noopener';
    source.textContent = 'Open this camera segment on YouTube ↗';
    source.href = `${evidence.videoUrl}&t=${Math.floor(incidentToVideo(camera, cursor))}s`;
    card.append(head, holder, status, source); $('camera-wall').append(card);
    entries.set(camera.id, {camera, card, choose, status, source, mount, ready: false, error: null});
  });
  selectMaster(evidence.cameras[0].id);
}

function createMap() {
  if (!window.maplibregl) { $('map-status').textContent = 'Map engine unavailable. Camera playback remains accessible.'; return; }
  map = new maplibregl.Map({container: 'map', style: mapStyle(), ...HOME, maxPitch: 80, canvasContextAttributes: {antialias: true}});
  map.addControl(new maplibregl.NavigationControl({visualizePitch: true}));
  map.addControl(new maplibregl.ScaleControl({unit: 'metric'}));
  map.on('load', async () => {
    map.setTerrain({source: 'dem', exaggeration: 1});
    $('map-status').textContent = 'Real terrain · four camera locations · 1× elevation';
    try {
      const response = await fetch('./evidence/gann/perimeter.geojson');
      if (!response.ok) throw new Error('Perimeter unavailable');
      map.addSource('later-perimeter', {type: 'geojson', data: await response.json()});
      map.addLayer({id: 'later-perimeter', type: 'line', source: 'later-perimeter', layout: {visibility: $('later-perimeter').checked ? 'visible' : 'none'}, paint: {'line-color': '#ffd36b', 'line-width': 2, 'line-dasharray': [3, 2]}});
    } catch { $('later-perimeter').disabled = true; $('map-status').textContent = 'Terrain available; later perimeter could not be loaded.'; }
  });
  map.on('error', () => { $('map-status').textContent = 'Some map tiles could not load. Camera playback remains available.'; });
  evidence.cameras.forEach((camera, i) => {
    const entry = entries.get(camera.id), pin = document.createElement('button');
    pin.className = 'camera-pin'; pin.textContent = i + 1; pin.setAttribute('aria-label', 'Use ' + camera.name + ' as the clock camera');
    pin.onclick = () => selectMaster(camera.id); entry.pin = pin;
    new maplibregl.Marker({element: pin}).setLngLat(camera.coordinates).addTo(map);
  });
  new maplibregl.Marker({color: '#b9c5d1'}).setLngLat(evidence.reference.coordinates)
    .setPopup(new maplibregl.Popup().setText(evidence.reference.source)).addTo(map);
  entries.get(master).pin.classList.add('selected');
}

function onPlayerState(entry, code) {
  if (entry.camera.id !== master) return;
  if (code === 1) {
    if (!running) playAll();
    else for (const other of entries.values()) if (other !== entry && other.ready && !other.error) other.player.playVideo();
    message('Following ' + entry.camera.name + '. Other cameras seek to the same estimated incident time.');
  } else if (code === 2 && running) {
    pauseAll(); message('Paused. Move the timeline or press Play cameras.');
  } else if (code === 3 && running) {
    for (const other of entries.values()) if (other !== entry && other.ready && !other.error) other.player.pauseVideo();
    message('Clock camera buffering. Other views wait for it.');
  } else if (code === 0) { pauseAll(); message('The source video ended.'); }
}

function initialisePlayers() {
  for (const entry of entries.values()) {
    entry.player = new YT.Player(entry.mount.id, {
      width: '100%', height: '100%', videoId: evidence.videoId,
      playerVars: {playsinline: 1, controls: 1, origin: location.origin, start: Math.floor(incidentToVideo(entry.camera, cursor))},
      events: {
        onReady: event => {
          entry.ready = true; event.target.mute();
          const target = incidentToVideo(entry.camera, cursor);
          event.target.cueVideoById({videoId: evidence.videoId, startSeconds: target});
          entry.status.textContent = 'Ready at approximately ' + stamp(cursor);
          const frame = entry.card.querySelector('iframe'); if (frame) frame.title = entry.camera.name + ' · Gann Fire';
          const lead = entries.get(master);
          $('play-all').disabled = !lead.ready || Boolean(lead.error);
          $('pause-all').disabled = false;
          if ([...entries.values()].every(item => item.ready || item.error)) message('YouTube players ready. Press Play cameras; all views are muted initially.');
        },
        onStateChange: event => onPlayerState(entry, event.data),
        onAutoplayBlocked: () => { entry.status.textContent = 'Playback blocked by the browser. Press play inside this YouTube player.'; },
        onError: event => {
          entry.error = event.data;
          entry.status.textContent = `YouTube playback unavailable (code ${event.data}). Use the original-video link below.`;
          if (entry.camera.id === master) { pauseAll(); $('play-all').disabled = true; message('Clock camera unavailable. Choose another loaded camera or open the original on YouTube.'); }
        }
      }
    });
  }
}

function loadYouTube() {
  if (loading) return;
  loading = true; $('load-youtube').disabled = true; message('Loading the original YouTube players…');
  if (window.YT?.Player) { initialisePlayers(); return; }
  window.onYouTubeIframeAPIReady = initialisePlayers;
  const script = document.createElement('script'); script.src = 'https://www.youtube.com/iframe_api';
  script.onerror = () => message('YouTube could not load. Use the original-video links; map and timestamp evidence remain available.');
  document.head.append(script);
  setTimeout(() => {
    if (![...entries.values()].some(entry => entry.ready)) message('YouTube is taking longer to load. Check your connection or use the original-video links.');
  }, 20000);
}

function tick() {
  if (!evidence || document.hidden) return;
  const lead = entries.get(master);
  if (lead?.ready && !lead.error) {
    const current = lead.player.getCurrentTime();
    if (pendingMaster !== null && Math.abs(current - pendingMaster) <= 0.8) pendingMaster = null;
    if (running && pendingMaster === null && lead.player.getPlayerState() === 1) {
      const utc = videoToIncident(lead.camera, current);
      if (utc === null || utc < evidence.start - 1 || utc > evidence.end) {
        pauseAll();
        seekAll(utc !== null && utc >= evidence.end ? evidence.end : cursor);
        message('End of the shared timestamp interval, or outside this camera segment. Choose a time to resume.');
      } else { cursor = clampTime(evidence, utc); paintClock(); }
    }
  }
  for (const entry of entries.values()) {
    entry.source.href = `${evidence.videoUrl}&t=${Math.floor(incidentToVideo(entry.camera, cursor))}s`;
    if (!entry.ready || entry.error) continue;
    const video = entry.player.getCurrentTime(), target = incidentToVideo(entry.camera, cursor);
    const measured = cameraAtVideo(entry.camera, video, cursor);
    const state = entry.player.getPlayerState();
    if (running && entry !== lead && lead?.player.getPlayerState() === 1 && pendingMaster === null && state !== 3 && Math.abs(video - target) > 0.6 && performance.now() - (entry.lastSeek || -Infinity) > 1600) {
      entry.lastSeek = performance.now(); entry.player.seekTo(target, true);
    }
    entry.card.dataset.playerState = state;
    entry.card.dataset.videoSecond = video.toFixed(3);
    entry.status.textContent = state === 3 ? 'Buffering · timestamp alignment pending' : measured.utc === null ? 'Waiting for this camera segment' :
      `${stamp(measured.utc)} · ${Math.abs(measured.delta) <= 45 ? 'approximately aligned' : `offset ${Math.round(measured.delta / 60)} min · aligning`}`;
  }
}

async function start() {
  try {
    const response = await fetch('./evidence/gann/youtube.json');
    if (!response.ok) throw new Error('Camera timestamp evidence could not be loaded.');
    evidence = readMulticam(await response.json());
    cursor = clampTime(evidence, Date.parse('2026-08-04T05:00:00Z') / 1000);
    Object.assign($('shared-time'), {min: evidence.start, max: evidence.end, value: cursor, disabled: false});
    $('range-start').textContent = stamp(evidence.start); $('range-end').textContent = stamp(evidence.end);
    $('range-note').textContent = `Shared interval supported by the supplied OCR anchors: ${stamp(evidence.start)} to ${stamp(evidence.end)}. The source report gives a longer endpoint based on an additional visual reading; this replay uses the conservative anchors.`;
    createCards(); createMap(); paintClock();
    $('load-youtube').disabled = false;
    message('Load the original YouTube cameras to begin. The initial incident time is 22:00 PDT.');
    $('load-youtube').onclick = loadYouTube;
    $('play-all').onclick = playAll;
    $('pause-all').onclick = () => { pauseAll(); message('Paused. All four views retain their incident time.'); };
    $('shared-time').oninput = event => { pauseAll(); seekAll(Number(event.target.value)); };
    $('frame-map').onclick = () => map?.easeTo({...HOME, duration: 700});
    $('tilt-map').onclick = () => { const tilted = map?.getPitch() < 20; map?.easeTo({pitch: tilted ? 60 : 0}); $('tilt-map').setAttribute('aria-pressed', String(tilted)); };
    $('later-perimeter').onchange = event => { if (map?.getLayer('later-perimeter')) map.setLayoutProperty('later-perimeter', 'visibility', event.target.checked ? 'visible' : 'none'); };
    document.addEventListener('visibilitychange', () => { if (document.hidden) { pauseAll(); message('Paused while this page is hidden.'); } });
    setInterval(tick, 400);
  } catch (error) { message(error.message); $('incident-clock').textContent = 'Camera evidence unavailable'; }
}
start();
