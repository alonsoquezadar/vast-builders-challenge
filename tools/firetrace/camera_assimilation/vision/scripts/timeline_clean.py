"""Merge OCR timeline rows (coarse + dense), reject misreads, and assign verification status.

Two OCR crops can agree on the same wrong digit (e.g. 13:59 read as 13:39 on both), so agreement alone is not
verification. Within each pose the printed time must be non-decreasing with decode order (frames are in
chronological order inside a pose); the longest non-decreasing subsequence is kept and every other row becomes
'uncertain' (reason recorded). A row that survives is 'ocr-consistent'; only rows whose bar crop was also inspected
by the agent (data/visual_bar_checks.json, whole-second precision; hundredths are never verified) are upgraded to 'verified-by-agent'.
    python3 -I scripts/timeline_clean.py
"""
import bisect, json, sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as v

def lnds(values):
    """indices of the longest non-decreasing subsequence."""
    tails, idx, prev = [], [], [-1] * len(values)
    for i, x in enumerate(values):
        k = bisect.bisect_right(tails, x)
        if k == len(tails): tails.append(x); idx.append(i)
        else: tails[k] = x; idx[k] = i
        prev[i] = idx[k - 1] if k else -1
    out, i = [], idx[-1] if idx else -1
    while i >= 0: out.append(i); i = prev[i]
    return set(out)

rows = {}
for name in ['timeline_ocr.json', 'timeline_dense.json']:
    p = v.HERE / 'data' / name
    if p.exists():
        for r in json.loads(p.read_text())['rows']: rows[r['frame']] = r
rows = [rows[k] for k in sorted(rows)]
for r in rows:
    r['status'] = 'uncertain'; r['statusReason'] = None
    if not r['timeReadsAgree']: r['statusReason'] = 'timestamp reads disagree or unparsable'
    elif not r['pose']: r['statusReason'] = 'camera/X/Y/Z not matching any registered pose (or other pose)'
for pid in v.POSES:
    rs = [r for r in rows if r['pose'] == pid and r['timeReadsAgree']]
    keep = lnds([r['printedTime'] for r in rs])
    for i, r in enumerate(rs):
        if i in keep: r['status'] = 'ocr-consistent'
        else: r['statusReason'] = 'violates chronological monotonicity inside pose (probable misread digit)'
visual = v.HERE / 'data/visual_bar_checks.json'
checks = json.loads(visual.read_text())['checks'] if visual.exists() else {}
for r in rows:
    c = checks.get(str(r['frame']))
    if c and r['status'] == 'ocr-consistent' and c['agentReadPrintedTime'] == r['printedTime'][:19]:
        r['status'] = 'verified-by-agent'
    elif c and c['agentReadPrintedTime'] != r['printedTime'][:19]:
        r['status'] = 'uncertain'; r['statusReason'] = f"agent visual read {c['agentReadPrintedTime']} differs from OCR {r['printedTime']}"
json.dump({'schema': 'firetrace-vision-timeline-v1', 'rows': rows}, open(v.HERE / 'data/timeline.json', 'w'), indent=1)
from collections import Counter
print(Counter((r['pose'], r['status']) for r in rows))
