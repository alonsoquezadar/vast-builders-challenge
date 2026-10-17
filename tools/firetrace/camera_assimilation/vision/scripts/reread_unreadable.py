"""Re-read only the rows whose timestamp reads did not agree (e.g. night frames where the bar-edge detector failed),
after the bar-width fallback in vcommon.read_rows was added. Valid rows are left untouched; no full OCR rerun."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as v
pts = json.loads((v.HERE / 'data/frame_scan.json').read_text())['framePtsSeconds']
for name in ['timeline_ocr.json', 'timeline_dense.json']:
    p = v.HERE / 'data' / name
    doc = json.loads(p.read_text())
    bad = [r['frame'] for r in doc['rows'] if not r['timeReadsAgree']]
    if not bad: continue
    # include a few valid neighbours on the left so the width fallback has a reference
    ref = sorted({max(b - 15, 0) for b in bad} | set(bad))
    new = {r['frame']: r for r in v.read_rows(ref, pts)}
    fixed = 0
    for i, r in enumerate(doc['rows']):
        if not r['timeReadsAgree'] and new[r['frame']]['timeReadsAgree']:
            doc['rows'][i] = new[r['frame']]; fixed += 1
    p.write_text(json.dumps(doc, indent=1) + '\n')
    print(name, 'unreadable', len(bad), 'recovered', fixed)
