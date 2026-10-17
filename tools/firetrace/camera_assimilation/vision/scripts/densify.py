"""OCR every 3rd decoded frame inside +/-WINDOW minutes of each VIIRS/MODIS pass (assumed-PDT printed time), so that
the frame nearest each pass is found at ~0.1 s of video resolution instead of 0.5 s. Reads data/timeline_ocr.json.
    python3 -I scripts/densify.py [WINDOW_MIN=5]"""
import json, sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as v
PASSES = {'G1': ['11:17', '12:49', '13:16', '13:38'], 'G3b': ['12:49', '13:16', '13:38'], 'G4': ['14:29', '14:57', '16:00']}
win = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
scan = json.loads((v.HERE / 'data/frame_scan.json').read_text()); pts = scan['framePtsSeconds']
coarse = json.loads((v.HERE / 'data/timeline_ocr.json').read_text())['rows']
need = set()
for pid, plist in PASSES.items():
    rs = [r for r in coarse if r['pose'] == pid]
    for p in plist:
        target = datetime.fromisoformat('2025-08-27T' + p + ':00')
        near = [r for r in rs if abs((datetime.fromisoformat(r['printedTime']) - target).total_seconds()) <= win * 60 + 180]
        if near:
            lo, hi = min(r['frame'] for r in near) - 15, max(r['frame'] for r in near) + 15
            need |= set(range(max(lo, 0), min(hi, scan['decodedFrames'] - 1) + 1, 3))
need -= {r['frame'] for r in coarse}
rows = v.read_rows(sorted(need), pts)
(v.HERE / 'data/timeline_dense.json').write_text(json.dumps({'schema': 'firetrace-vision-timeline-ocr-v1', 'windowMin': win, 'rows': rows}, indent=1) + '\n')
print(len(rows), 'dense frames OCR-ed')
