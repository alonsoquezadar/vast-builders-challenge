"""Read the printed bar (camera id, X/Y/Z, date/time) of frames across the whole video with macOS Vision.

Method: decode every STEP-th frame exactly (default 15 = ~0.5 s of video), crop the black bar, upscale, OCR it
three ways (full bar, timestamp-only crop, camera/XYZ-only crop). A time is kept only when the two timestamp
reads (full bar and timestamp crop) agree after parsing; otherwise the row is 'uncertain'. Video seconds are
never used to infer printed time.   python3 -I scripts/ocr_timeline.py [STEP]
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as v

step = int(sys.argv[1]) if len(sys.argv) > 1 else 15
scan = json.loads((v.HERE / 'data/frame_scan.json').read_text())
n_frames = scan['decodedFrames']; pts = scan['framePtsSeconds']
numbers = list(range(0, n_frames, step)) + [n_frames - 1]
rows = v.read_rows(numbers, pts)
out = {'schema': 'firetrace-vision-timeline-ocr-v1', 'videoSha256': scan['videoSha256'], 'ocr': 'macOS Vision VNRecognizeTextRequest accurate, languageCorrection=false',
       'step': step, 'rows': rows}
(v.HERE / 'data/timeline_ocr.json').write_text(json.dumps(out, indent=1) + '\n')
ok = sum(r['timeReadsAgree'] for r in rows)
print(f'{len(rows)} frames OCR-ed, {ok} with agreeing time reads, {sum(1 for r in rows if r["pose"])} assigned to a pose')
