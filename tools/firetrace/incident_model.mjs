export function printedClockSeconds(value) {
  const match = /^\d{4}-\d{2}-\d{2}T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?$/.exec(value);
  if (!match || Number(match[1]) > 23 || Number(match[2]) > 59 || Number(match[3]) > 59) throw Error('Hora impresa inválida.');
  return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]) + Number('0.' + (match[4] || '0'));
}
export function resolveMoment(bundle, index) {
  const moment = bundle.moments[index];
  if (!moment) throw Error('Momento no disponible.');
  const frames = moment.frameIds.map(id => {
    const frame = bundle.frames.find(f => f.id === id);
    if (!frame || !bundle.cameras.some(c => c.id === frame.cameraId)) throw Error('Fotograma o cámara no disponible.');
    return frame;
  });
  if (frames.length !== bundle.cameras.length || new Set(frames.map(f => f.cameraId)).size !== frames.length) throw Error('Cada vista necesita una cámara distinta.');
  const dates = new Set(frames.map(f => f.printedTime.slice(0, 10)));
  if (dates.size !== 1) throw Error('Las vistas deben pertenecer al mismo día impreso.');
  const times = frames.map(f => printedClockSeconds(f.printedTime));
  return {frames, printedOffsetSeconds: Math.max(...times) - Math.min(...times), synchronized: false};
}
