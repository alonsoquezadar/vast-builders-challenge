"""Render sheets of enlarged printed-bar crops (left: camera + X/Y/Z, right: timestamp) for visual verification.
The sheet shows only the frame index and the crops, NOT the OCR value, so the agent's reading is independent.
Output: contact/bars-N.jpg (N = 1..) and data/bar_sheet_index.json (sheet -> row -> frame).   python3 -I scripts/bar_sheets.py"""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as v
cands = json.loads((v.HERE / 'data/candidates.json').read_text())['candidates']
ONLY = None
if len(sys.argv) > 1 and sys.argv[1] == '--answered':        # only the frames that have a Cosmos answer
    ONLY = {p.stem for p in (v.HERE / 'cosmos/raw').glob('*.json')}
    cands = [c for c in cands if c['id'] in ONLY]
ROWS = 16
index = {}
for s in range(0, len(cands), ROWS):
    chunk = cands[s:s + ROWS]
    sheet = Image.new('RGB', (1500, 66 * len(chunk)), 'white'); d = ImageDraw.Draw(sheet)
    for i, c in enumerate(chunk):
        im = Image.open(v.SCRATCH / 'frames_png' / f"f{c['frame']:05d}.png").convert('RGB'); end = v.bar_end(im)  # lossless decode of the same frame (JPEG ringing breaks the bar-edge detector)
        left = im.crop((0, v.BAR_Y0, min(v.CAM_WIDTH, end), v.BAR_Y1)); left = left.resize((int(left.width * 2.6), 60), Image.LANCZOS)
        right = im.crop((max(end - v.TS_WIDTH, 0), v.BAR_Y0, end + 2, v.BAR_Y1)); right = right.resize((int(right.width * 4), 60), Image.LANCZOS)
        d.text((2, i * 66 + 22), f'{i + 1:02d}', fill='red')
        sheet.paste(left, (24, i * 66)); sheet.paste(right, (24 + left.width + 12, i * 66))
        index.setdefault(s // ROWS + 1, []).append({'row': i + 1, 'frame': c['frame'], 'id': c['id']})
    sheet.save(v.HERE / (f'contact/bars-answered-{s // ROWS + 1}.jpg' if ONLY else f'contact/bars-{s // ROWS + 1}.jpg'), quality=90)
(v.HERE / ('data/bar_sheet_index_answered.json' if ONLY else 'data/bar_sheet_index.json')).write_text(json.dumps(index, indent=1))
print(len(index), 'sheets')
