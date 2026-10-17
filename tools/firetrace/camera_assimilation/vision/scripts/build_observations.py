"""Assemble vision/observations.json (firetrace-camera-observations-v1) from the saved raw Cosmos responses.

One row per answered frame, method=cosmos only (no heuristic rows were produced: the phase was paused). Coordinates come
only from the model; hidden bases stay null. Printed time comes from the bar (never from video seconds): rows whose bar
was also transcribed by the agent are 'verified-by-agent' (whole seconds), all others would be 'uncertain'.
    python3 -I scripts/build_observations.py"""
import json, sys
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as v

cands = {c['id']: c for c in json.loads((v.HERE / 'data/candidates.json').read_text())['candidates']}
timeline = {r['frame']: r for r in json.loads((v.HERE / 'data/timeline.json').read_text())['rows']}
ledger = json.loads((v.HERE / 'cosmos/ledger.json').read_text())
EXTERNAL = {  # call executed by root, not by this pipeline; agent read the bar of the JPEG itself (contact: see report)
    'delilah-G2-ev134': dict(cameraId='delilah', poseId='G2', sourceVideoSecond=134, printedTime='2025-08-27T20:16:58.11', status='verified-by-agent',
                             imagePath='camera_assimilation/vision/frames/delilah-G2-ev134.jpg')}
rows, receipts, quality = [], {}, {'templateEchoIds': [], 'unparsedIds': []}
for raw in sorted((v.HERE / 'cosmos/raw').glob('*.json')):
    fid = raw.stem
    resp = json.loads(raw.read_text()); obs = resp.get('observation')
    if fid in EXTERNAL:
        e = EXTERNAL[fid]; path = v.TOOLS / e['imagePath']
        cam, pose, sec, printed, status, rel = e['cameraId'], e['poseId'], e['sourceVideoSecond'], e['printedTime'], e['status'], e['imagePath']
        ext = True
    else:
        c = cands[fid]; t = timeline[c['frame']]; path = v.TOOLS / c['imagePath']
        cam, pose, sec, printed, status, rel = c['cameraId'], c['pose'], c['videoSecond'], t['printedTime'], ('verified-by-agent' if t['status'] == 'verified-by-agent' else 'uncertain'), c['imagePath']
        ext = False
    sha = v.sha256_file(path)
    assert sha == resp['imageSha256'], f'{fid}: image SHA differs from the SHA the gateway analyzed'
    if obs is None:
        quality['unparsedIds'].append(fid); continue
    if obs['reason'].strip() == 'brief visible evidence and obstruction' or obs['confidence'] == 0.0:
        quality['templateEchoIds'].append(fid)
    utc = (datetime.fromisoformat(printed) + timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-4] + 'Z'
    rows.append(dict(id=f'{fid}-cosmos', cameraId=cam, poseId=pose, sourceVideoSecond=sec, imagePath=rel, imageSha256=sha,
                     frameWidth=640, frameHeight=360, printedTime=printed, printedTimeStatus=status, timeUtcAssumed=utc, clockStatus='assumed-PDT',
                     method='cosmos', smoke=obs['smoke'], base_visible=obs['base_visible'], x_base=obs['x_base'], y_base=obs['y_base'],
                     confidence=obs['confidence'], reason=obs['reason'], reviewStatus='pending-operator-review'))
    att = [a for a in ledger['attempts'] if a['id'] == fid]
    receipts[f'{fid}-cosmos'] = dict(raw=str((v.HERE / 'cosmos/raw' / raw.name).relative_to(v.TOOLS)), model=resp['model'], analyzedAt=resp['analyzedAt'],
                                      gatewayImageSha256=resp['imageSha256'], task=resp['task'], gatewayGeolocation=resp.get('geolocation'),
                                      executedBy='root (external, not counted in vision ledger)' if ext else 'vision pipeline', elapsedSeconds=att[0]['seconds'] if att else None)
rows.sort(key=lambda r: (r['cameraId'], r['printedTime']))
from collections import Counter
doc = {
    'schema': 'firetrace-camera-observations-v1',
    'status': 'paused-next-phase',
    'statusReason': f"{sum(not r['base_visible'] for r in rows)} of {len(rows)} real Cosmos answers report base_visible=false; no localizable base, so no camera correction can use these rows. Phase paused by the operator.",
    'source': {'video': '/tmp/firevids/garnet.ogg', 'videoSha256': json.loads((v.HERE / 'data/frame_scan.json').read_text())['videoSha256'],
               'attribution': 'ALERTCalifornia | UC San Diego, image courtesy of PG&E (credits are part of the saved frames)', 'ingestedIntoVast': False},
    'clock': 'printed time is the camera bar; timeUtcAssumed = print + 7 h (assumed-PDT hypothesis, not a historical clock receipt)',
    'counts': {'rows': len(rows), 'baseVisibleTrue': sum(r['base_visible'] for r in rows), 'baseVisibleFalse': sum(not r['base_visible'] for r in rows),
               'smokeTrue': sum(r['smoke'] for r in rows), 'printedTimeVerifiedByAgent': sum(r['printedTimeStatus'] == 'verified-by-agent' for r in rows),
               'printedTimeUncertain': sum(r['printedTimeStatus'] == 'uncertain' for r in rows), 'byPose': dict(Counter(r['poseId'] for r in rows)),
               'visionPipelineCosmosAttempts': len(ledger['attempts']), 'visionPipelineCosmosFailures': sum(not a['ok'] for a in ledger['attempts']),
               'externalRootCalls': sum(1 for r in receipts.values() if r['executedBy'].startswith('root'))},
    'quality': {**quality, 'note': 'templateEchoIds: the model returned the prompt placeholder text (confidence 0.0, reason "brief visible evidence and obstruction") instead of an inspection. They are kept as returned and carry no more information than base_visible=false by abstention.'},
    'methodPolicy': 'Only method=cosmos rows exist. No simple-detector rows were produced (the phase was paused before the heuristic comparison). Downstream calibration/assimilation must treat base_visible=false rows as non-localizing; confidence is uncalibrated.',
    'observations': rows,
    'receipts': receipts,
    'limitations': [
        'Agent visual reading of the printed bar is not human review; hundredths of a second are blurred and not verified. reviewStatus stays pending-operator-review.',
        'PDT is a hypothesis; a 2026-10-17 current-frame check (root, camera_assimilation/clock-check) does not verify the 2025 clock.',
        'Rows are single frames chosen at the printed times nearest the satellite passes (time only; no FIRMS geography informed any choice); 10 + 1 frames are not a statistical sample.',
        'Cosmos confidence is uncalibrated and some answers are template echoes. A hidden base is a null coordinate, never a forced point.',
        'The printed time of delilah-G2-ev134 comes from the already-saved evidence JPEG (root receipt) and the agent reading its bar; the video decode of that second could not be OCR-ed (bar truncated at the frame edge in decoded frames 126-134 s).'],
}
(v.HERE / 'observations.json').write_text(json.dumps(doc, indent=1) + '\n')
print(json.dumps(doc['counts']), doc['quality']['templateEchoIds'])
