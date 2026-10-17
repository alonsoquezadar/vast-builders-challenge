export function printedClockSeconds(value) {
  const match = /^\d{4}-\d{2}-\d{2}T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?$/.exec(value);
  if (!match || Number(match[1]) > 23 || Number(match[2]) > 59 || Number(match[3]) > 59) throw Error('Invalid printed time.');
  return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]) + Number('0.' + (match[4] || '0'));
}
export function resolveMoment(bundle, index) {
  const moment = bundle.moments[index];
  if (!moment) throw Error('Moment not available.');
  const frames = moment.frameIds.map(id => {
    const frame = bundle.frames.find(f => f.id === id);
    if (!frame || !bundle.cameras.some(c => c.id === frame.cameraId)) throw Error('Frame or camera not available.');
    return frame;
  });
  if (frames.length !== bundle.cameras.length || new Set(frames.map(f => f.cameraId)).size !== frames.length) throw Error('Each view needs a different camera.');
  const dates = new Set(frames.map(f => f.printedTime.slice(0, 10)));
  if (dates.size !== 1) throw Error('The views must belong to the same printed day.');
  const times = frames.map(f => printedClockSeconds(f.printedTime));
  return {frames, printedOffsetSeconds: Math.max(...times) - Math.min(...times), synchronized: false};
}
export class InferenceError extends Error {}
// Apply the target when metadata is ready; a later call replaces an earlier pending target.
export function seekWhenReady(video, seconds) {
  if (video.readyState >= 1) video.currentTime = seconds;
  else video.onloadedmetadata = () => { video.currentTime = seconds; };
}
// Keep the reviewed response alongside a new one so the export never loses it.
export function acceptLiveAnalysis(frame, data) {
  if (!data || typeof data.content !== 'string' || !data.content || data.imageSha256 !== frame.imageSha256) throw new InferenceError('The response does not match the selected frame.');
  if (!('savedAnalysis' in frame)) frame.savedAnalysis = frame.analysis;
  frame.analysis = data;
  frame.presentationMode = 'live';
}
export async function requestAnalysis(frame, image, fetchFn = fetch) {
  let result, data = null;
  try { result = await fetchFn('./api/analyze', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({image})}); }
  catch { throw new InferenceError('Could not reach the analysis service.'); }
  try { data = await result.json(); } catch { /* non-JSON error body */ }
  if (!result.ok) throw new InferenceError(typeof data?.error === 'string' && data.error ? data.error : `The analysis service responded with HTTP ${result.status}.`);
  acceptLiveAnalysis(frame, data);
}
export function inferenceFailureNotice(error, frame) {
  const detail = error instanceof InferenceError ? error.message : 'The inference could not be completed.';
  return `The inference was not completed. ${/[.!?]$/.test(detail) ? detail : detail + '.'}${frame.analysis ? ' The previous response has been kept.' : ''}`;
}
// Review notes correct the saved response; they must not be attached to a new one.
export function reviewNotesFor(frame) {
  const notes = frame.reviewNotes || [];
  if (!notes.length) return '';
  return frame.presentationMode === 'live' ? 'This new response has not been reviewed. The provenance corrections refer to the saved response, which is kept in the export.' : notes.join(' ');
}
