"""Choose candidate frames and save the ORIGINAL decoded frames as JPEG (credits/logos/bar untouched).

Selection uses only the printed time read from the bar and the pass times from evidence/garnet/satellite/overpasses.json
(time only: no FIRMS geography is used, so no pixel/azimuth choice is informed by the hotspots).
  * pass frames: per pose and pass (assumed PDT = print +7 h = UTC), the ocr-consistent frame nearest in printed time;
    gap recorded, flagged if > 5 min;
  * sample frames: roughly every SAMPLE_S video seconds inside each pose (cadence is irregular, so spacing is in video
    seconds and the printed-time gap between samples is reported, never assumed);
  * G2 night: frames from the G2 night segment (printed >= 19:50) for the hypothetical-bearing experiment.
    python3 -I scripts/make_candidates.py [SAMPLE_S=4]
"""
import json, shutil, sys
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as v

SAMPLE_S = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
rows = [r for r in json.loads((v.HERE / 'data/timeline.json').read_text())['rows'] if r['pose'] and r['status'] == 'ocr-consistent']
over = json.loads((v.TOOLS / 'evidence/garnet/satellite/overpasses.json').read_text())['overpasses']
passes = [o for o in over if o['acquiredPdt'].startswith('2025-08-27')]
def pt(r): return datetime.fromisoformat(r['printedTime'])
cands = {}
def add(r, role, **extra):
    c = cands.setdefault(r['frame'], dict(frame=r['frame'], roles=[], pose=r['pose'], printedTime=r['printedTime'], videoSecond=r['videoSecond'], xyz=r['xyz']))
    c['roles'].append({'role': role, **extra})

PASS_POSES = {'G1': True, 'G3b': True, 'G4': True}
for pid in PASS_POSES:
    rs = [r for r in rows if r['pose'] == pid]
    lo, hi = pt(rs[0]), pt(rs[-1])
    for o in passes:
        local = datetime.fromisoformat(o['acquiredPdt'][:19])           # printed-time hypothesis (assumed PDT)
        if not (lo - timedelta(minutes=5) <= local <= hi + timedelta(minutes=5)):
            continue
        best = min(rs, key=lambda r: abs((pt(r) - local).total_seconds()))
        gap = (pt(best) - local).total_seconds()
        add(best, 'pass-nearest', passSource=o['source'], passUtc=o['acquiredUtc'], passPrintedAssumedPdt=local.isoformat(),
            gapSeconds=round(gap, 1), within5min=abs(gap) <= 300)
for pid, p in v.POSES.items():
    rs = [r for r in rows if r['pose'] == pid]
    nxt = None
    for r in rs:
        if nxt is None or r['videoSecond'] >= nxt:
            add(r, 'sample'); nxt = r['videoSecond'] + SAMPLE_S
g2 = [r for r in rows if r['pose'] == 'G2' and r['printedTime'][11:16] >= '19:50']
ref = datetime.fromisoformat('2025-08-27T20:16:58.11')   # printed time of the earlier reviewed evidence/garnet/delilah-134.jpg
for r in {x['frame']: x for x in (min(g2, key=lambda r: abs((pt(r) - ref).total_seconds())), g2[len(g2) // 3], g2[-1])}.values():
    add(r, 'g2-night')
out = []
jp = v.extract_frames(list(cands), v.SCRATCH / 'frames_jpg', 'jpg', quality=2)
for n in sorted(cands):
    c = cands[n]
    cam = v.POSES[c['pose']]['cameraId']
    cid = f"{cam}-{c['pose']}-f{n:05d}"
    dst = v.HERE / 'frames' / f'{cid}.jpg'
    shutil.copyfile(jp[n], dst)
    c.update(id=cid, cameraId=cam, imagePath=str(dst.relative_to(v.TOOLS)), imageSha256=v.sha256_file(dst))
    out.append(c)
(v.HERE / 'data/candidates.json').write_text(json.dumps({'schema': 'firetrace-vision-candidates-v1', 'sampleSeconds': SAMPLE_S, 'candidates': out}, indent=1) + '\n')
from collections import Counter
print(len(out), 'candidates;', Counter(r['role'] for c in out for r in c['roles']))
for c in out:
    for r in c['roles']:
        if r['role'] == 'pass-nearest': print(c['id'], c['printedTime'][11:19], r['passSource'], r['passPrintedAssumedPdt'][11:16], r['gapSeconds'], 'OK' if r['within5min'] else 'GAP>5min')
