import {formatStamp} from './firetrace_model.mjs';
import {videoAnchors, videoToUtc, utcToVideo} from './video-clock.mjs';

export function initCameraPlayer({getCursor, getZone, setCursor, pauseTimeline}) {
  const dock = document.getElementById('camera-player');
  const video = document.getElementById('camera-video');
  const select = document.getElementById('video-camera');
  const status = document.getElementById('video-sync-status');
  const range = document.getElementById('video-range');
  const openButton = document.getElementById('footage-open');
  let incident, camera, anchors = [], pendingSeek = null, desiredTime = null, playAfterSeek = false;
  const requestPlay = () => {
    playAfterSeek = false;
    video.play().catch(() => { status.textContent = 'Press Play on the video to begin the synced sequence.'; });
  };
  const stamp = utc => {
    const value = formatStamp(utc, getZone());
    return `${value.date} ${value.time} ${value.zone}`;
  };
  const showTime = utc => { status.textContent = `Estimated video time · ${stamp(utc)}`; status.dataset.state = 'linked'; };
  function refreshLabels() {
    if (!anchors.length) return;
    range.textContent = `${stamp(anchors[0].utc)} – ${stamp(anchors.at(-1).utc)}`;
    const utc = videoToUtc(anchors, video.currentTime);
    if (utc !== null && status.dataset.state === 'linked') showTime(utc);
  }
  const seek = seconds => {
    desiredTime = seconds;
    pendingSeek = seconds;
    if (!video.readyState) { status.textContent = 'Loading the timestamped video…'; status.dataset.state = 'seeking'; return; }
    if (Math.abs(video.currentTime - seconds) < 0.08) { pendingSeek = null; return; }
    status.textContent = 'Seeking to the selected incident time…'; status.dataset.state = 'seeking';
    video.currentTime = Math.min(seconds, video.duration);
  };
  function syncCursor(utc) {
    if (dock.hidden || !camera) return;
    playAfterSeek = false;
    video.pause();
    const time = utcToVideo(anchors, utc);
    if (time === null) {
      status.textContent = 'Outside the timestamped video range. The displayed frame does not match the timeline.';
      status.dataset.state = 'outside';
      return;
    }
    seek(time); if (pendingSeek === null) showTime(utc);
  }
  function changeCamera(id) {
    camera = incident.cameras.find(item => item.id === id);
    anchors = videoAnchors(camera, incident.frames);
    video.pause(); pendingSeek = null; desiredTime = null; playAfterSeek = false;
    select.value = camera.id;
    video.src = camera.clipPath;
    video.poster = incident.frames.find(frame => frame.cameraId === id)?.imagePath || '';
    const start = anchors[0], end = anchors.at(-1);
    range.textContent = start ? `${stamp(start.utc)} – ${stamp(end.utc)}` : 'No timestamped sequence available.';
    document.getElementById('video-restart').disabled = !start;
    // A valid timestamped frame is the starting view, even if the main cursor is elsewhere.
    if (start) seek(utcToVideo(anchors, getCursor()) ?? start.video);
    syncCursor(getCursor());
  }
  function driveTimeline(seconds = video.currentTime) {
    if (pendingSeek !== null || !video.readyState || !anchors.length) return;
    const utc = videoToUtc(anchors, seconds);
    if (utc === null) {
      video.pause();
      status.textContent = 'Outside the timestamped video range. Use Start synced sequence to return.';
      status.dataset.state = 'outside';
      return;
    }
    pauseTimeline(); setCursor(utc); showTime(utc);
  }
  const restart = () => {
    if (!anchors.length) return;
    pauseTimeline(); video.pause(); playAfterSeek = true;
    seek(anchors[0].video); setCursor(anchors[0].utc);
    if (pendingSeek === null) showTime(anchors[0].utc);
    if (pendingSeek === null) requestPlay();
  };
  video.addEventListener('loadedmetadata', () => {
    if (desiredTime !== null) seek(desiredTime);
    if (pendingSeek === null && playAfterSeek) requestPlay();
  });
  video.addEventListener('seeked', () => {
    if (pendingSeek !== null) {
      if (video.seeking || Math.abs(video.currentTime - pendingSeek) > 0.2) return;
      pendingSeek = null;
      const utc = videoToUtc(anchors, video.currentTime);
      if (utc !== null && status.dataset.state === 'seeking') showTime(utc);
      if (playAfterSeek && !dock.hidden) requestPlay();
      return;
    }
    driveTimeline();
  });
  function updatePlayback(seconds) {
    if (video.paused || pendingSeek !== null || !anchors.length) return;
    if (seconds >= anchors.at(-1).video) {
      video.pause(); seek(anchors.at(-1).video); setCursor(anchors.at(-1).utc);
      status.textContent = `End of timestamped sequence · ${stamp(anchors.at(-1).utc)}`;
      return;
    }
    driveTimeline(seconds);
  }
  let videoFrame = null, lastFrameUpdate = -Infinity;
  const cancelFrame = () => {
    if (videoFrame !== null) video.cancelVideoFrameCallback(videoFrame);
    videoFrame = null;
  };
  function presentFrame(now, metadata) {
    videoFrame = null;
    if (video.paused || dock.hidden) return;
    if (now - lastFrameUpdate >= 100) { lastFrameUpdate = now; updatePlayback(metadata.mediaTime); }
    if (!video.paused) videoFrame = video.requestVideoFrameCallback(presentFrame);
  }
  video.addEventListener('playing', () => {
    if (typeof video.requestVideoFrameCallback === 'function') {
      cancelFrame(); lastFrameUpdate = -Infinity;
      videoFrame = video.requestVideoFrameCallback(presentFrame);
    }
  });
  video.addEventListener('pause', cancelFrame);
  video.addEventListener('timeupdate', () => {
    if (typeof video.requestVideoFrameCallback !== 'function' || document.hidden) updatePlayback(video.currentTime);
  });
  video.addEventListener('play', () => {
    pauseTimeline();
    if (pendingSeek !== null) { playAfterSeek = true; video.pause(); return; }
    if (videoToUtc(anchors, video.currentTime) === null) restart();
    else driveTimeline();
  });
  video.addEventListener('error', () => { status.textContent = 'The video could not be loaded. Check your connection or choose the other camera.'; status.dataset.state = 'outside'; });
  select.addEventListener('change', () => changeCamera(select.value));
  document.getElementById('video-restart').addEventListener('click', restart);
  document.getElementById('video-close').addEventListener('click', () => {
    playAfterSeek = false; video.pause(); dock.hidden = true; openButton.setAttribute('aria-expanded', 'false'); openButton.focus();
  });
  function open(id, utc) {
    if (!incident) return;
    dock.hidden = false; openButton.setAttribute('aria-expanded', 'true');
    pauseTimeline();
    if (!camera || id && id !== camera.id) changeCamera(id || incident.cameras[0].id);
    if (utc !== undefined) { setCursor(utc); syncCursor(utc); }
    else syncCursor(getCursor());
  }
  openButton.addEventListener('click', () => open());
  return {
    open, syncCursor, refreshLabels, restart,
    pause: () => { playAfterSeek = false; video.pause(); },
    setIncident(value) {
      incident = value; select.replaceChildren();
      for (const item of value.cameras) { const option = document.createElement('option'); option.value = item.id; option.textContent = item.name; select.append(option); }
      openButton.disabled = false;
    }
  };
}
