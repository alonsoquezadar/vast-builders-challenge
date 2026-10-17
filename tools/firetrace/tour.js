const STEPS = [
  ['.stage', 'Welcome to FireTrace', 'Explore the Garnet Fire in California, from 24 August to 12 September 2025. This historical research demo brings satellite observations, reconstructed growth, weather and camera evidence together. It is not a live emergency service.'],
  ['.view-controls', 'Explore the terrain', 'Drag the map to pan, scroll to zoom, and right-drag to change the viewing angle. Use 2D for a top-down view, 3D for relief, and Frame to return to the fire. Map imagery and terrain need an internet connection.'],
  ['.transport', 'Play the history', 'Press Play to watch the incident unfold. Pause whenever you want to investigate a moment. The arrow buttons move one hour at a time; Speed changes how quickly the replay advances. The space bar also plays or pauses when the map is focused.'],
  ['.scrub', 'Choose a moment', 'Drag the timeline to choose a date and time. The date above the map and the analysis panels follow this cursor. Coloured milestone markers jump to key moments in the incident.'],
  ['.zone', 'Read the time correctly', 'Switch between UTC and PDT for display. PDT means UTC minus seven hours. The camera time zone is an assumption: changing this display does not verify or synchronise the camera clocks.'],
  ['#panel-layers', 'Choose the evidence layers', 'Toggle the arrival reconstruction, satellite hotspots, final perimeter, projection and camera cones. Recent activity can cover the last 6, 12 or 24 hours. The final perimeter was published later and is not a snapshot of the fire at the cursor. Camera cones are hypotheses.'],
  ['.legend', 'Understand the colours', 'Expand the Data class legend with +. OBSERVED means recorded evidence, RECONSTRUCTED means an estimate derived from observations, and MODELLED means a calculated scenario. These categories have different levels of uncertainty.'],
  ['#panel-state', 'Read the state at the cursor', 'This panel reports the reconstructed area and satellite activity at the selected time. A satellite hotspot is a thermal detection, not a precise fire boundary. Gaps between satellite passes do not mean that the fire stopped.'],
  ['#panel-weather', 'Inspect historical weather', 'Review wind direction, speed and the available weather context for the selected hour. These are modelled historical conditions at one point, not measurements across the whole fire. Wind direction indicates where the wind comes from.'],
  ['#panel-video-model', 'Watch modelled growth with the real video', 'Press Play video + model. The real camera footage and the magenta simulated growth share the same incident clock. Orange is the satellite reconstruction; magenta is additional growth calculated from historical wind and terrain, starting at 23:00 UTC. Only recent reconstructed boundary cells start spreading. The layer is experimental, uses uniform assumed fuel and is not fitted to the video. Sources and comparison shows its known overprediction.'],
  ['#panel-forecast', 'Project from the selected front', 'Choose 6, 12 or 24 hours, then press Project from this front. The model starts from the reconstruction at the cursor. Moving the cursor or changing the horizon hides the old result. On the published website, saved projections use the nearest available whole hour and the cursor moves to that exact starting time.'],
  ['#panel-forecast', 'Compare the result honestly', 'After a projection loads, inspect the predicted and reference areas, overprediction, underprediction and IoU (overlap divided by combined area). Growth IoU focuses on new growth. The comparison uses a later reconstruction, not independent validation. This experimental model can substantially overpredict the fire.'],
  ['#panel-camera', 'Review the camera evidence', 'Select a camera card or map pin to see its nearest saved frame and NVIDIA Cosmos description. Check the actual frame time and its difference from the cursor. Go to its time moves the replay to that frame. Saved AI descriptions require review; the cameras do not currently correct the projection.'],
  ['#footage-open', 'Compare the camera footage and the model', 'Press Real footage to open a video in the right-hand corner of the map, or use Watch synced clip in a camera card. Start synced sequence plays the timestamped part and moves the timeline with the video. Moving the timeline seeks the video. Choose either camera in the player. Synchronisation is approximate between printed timestamps, with PDT assumed; no time is inferred beyond those anchors. Magenta growth comes from the wind-and-terrain model, not from measurements extracted from the video.'],
  ['.charts', 'Read the three histories', 'The charts show cumulative reconstructed area, observed fire radiative power (FRP) per satellite overpass, and modelled hourly wind. Click a chart to move the cursor and compare these histories at the same moment.'],
  ['#panel-events', 'Jump to a milestone', 'Select a milestone to pause the replay and inspect that moment. You can also use the coloured markers on the timeline. The panels and camera evidence update with the selected time.'],
  ['#panel-provenance', 'Check the sources and limits', 'Read the provenance, assumptions and known biases before interpreting a result. The reconstruction uses a later final perimeter; camera orientation and clock assumptions remain unverified. This is a research demonstration, not a validated forecast or evacuation tool. You can restart this tour at any time.']
];

export function initTour({pause}) {
  const trigger = document.getElementById('tour-start');
  const dialog = document.createElement('dialog');
  dialog.className = 'tour';
  dialog.setAttribute('aria-labelledby', 'tour-title');
  dialog.setAttribute('aria-describedby', 'tour-description');
  dialog.innerHTML = `<div class="tour-highlight" aria-hidden="true"></div>
    <section class="tour-card"><div class="tour-heading"><span id="tour-progress"></span><button class="tour-close" aria-label="Close tour">×</button></div>
    <div class="tour-copy" aria-live="polite" aria-atomic="true"><h2 id="tour-title"></h2><p id="tour-description"></p></div>
    <div class="tour-footer"><button class="tour-back">Back</button><span class="tour-hint">Esc to exit</span><button class="tour-next">Next</button></div></section>`;
  document.body.append(dialog);
  const card = dialog.querySelector('.tour-card');
  const highlight = dialog.querySelector('.tour-highlight');
  const next = dialog.querySelector('.tour-next');
  const back = dialog.querySelector('.tour-back');
  let index = 0, target, savedScroll = 0, frame;
  const position = () => {
    if (!dialog.open || !target) return;
    const r = target.getBoundingClientRect(), margin = 12, width = innerWidth, height = innerHeight;
    const left = Math.max(4, r.left - 4), top = Math.max(4, r.top - 4);
    Object.assign(highlight.style, {left: `${left}px`, top: `${top}px`, width: `${Math.max(0, Math.min(r.right + 4, width - 4) - left)}px`, height: `${Math.max(0, Math.min(r.bottom + 4, height - 4) - top)}px`});
    const ch = card.offsetHeight, cw = card.offsetWidth;
    let x = margin, y = margin;
    if (r.left >= cw + 2 * margin) {
      x = Math.min(r.left - cw - margin, width - cw - margin);
      y = Math.max(margin, Math.min(r.top, height - ch - margin));
    } else if (r.top >= ch + 2 * margin) {
      x = Math.max(margin, Math.min(r.left, width - cw - margin)); y = r.top - ch - margin;
    } else {
      x = Math.max(margin, Math.min(r.left, width - cw - margin));
      y = Math.min(r.bottom + margin, height - ch - margin);
    }
    Object.assign(card.style, {left: `${x}px`, top: `${Math.max(margin, y)}px`});
  };
  const show = () => {
    const [selector, title, description] = STEPS[index];
    target = document.querySelector(selector);
    target?.scrollIntoView({block: 'nearest', inline: 'nearest', behavior: 'instant'});
    dialog.querySelector('#tour-title').textContent = title;
    dialog.querySelector('#tour-description').textContent = description;
    dialog.querySelector('#tour-progress').textContent = `FEATURE TOUR · ${index + 1} OF ${STEPS.length}`;
    back.disabled = index === 0;
    next.textContent = index === STEPS.length - 1 ? 'Finish tour' : 'Next';
    cancelAnimationFrame(frame); frame = requestAnimationFrame(position);
  };
  const finish = () => dialog.close();
  trigger.addEventListener('click', () => {
    pause(); savedScroll = document.querySelector('.side').scrollTop; index = 0;
    dialog.showModal(); show(); next.focus();
  });
  next.addEventListener('click', () => { if (index === STEPS.length - 1) finish(); else { index++; show(); } });
  back.addEventListener('click', () => { if (index > 0) { index--; show(); if (back.disabled) next.focus(); } });
  dialog.querySelector('.tour-close').addEventListener('click', finish);
  dialog.addEventListener('close', () => { cancelAnimationFrame(frame); document.querySelector('.side').scrollTop = savedScroll; trigger.focus(); });
  dialog.addEventListener('keydown', e => {
    if (e.key === 'ArrowRight') { e.preventDefault(); next.click(); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); back.click(); }
    if (e.key === 'Tab') {
      const buttons = [...dialog.querySelectorAll('button:not(:disabled)')];
      const first = buttons[0], last = buttons.at(-1);
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
    e.stopPropagation();
  });
  window.addEventListener('resize', position);
  document.addEventListener('scroll', position, true);
}
