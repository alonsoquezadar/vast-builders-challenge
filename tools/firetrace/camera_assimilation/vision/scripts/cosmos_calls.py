"""Sequential Cosmos smoke-base-v1 calls on selected frames through the local gateway.

  python3 -I scripts/cosmos_calls.py FRAME_ID [FRAME_ID ...]      (ids from data/candidates.json)

Hard budget: the ledger cosmos/ledger.json counts EVERY attempt (success or failure); the script refuses to
exceed BUDGET (30) in total. Full raw responses are written to cosmos/raw/<id>.json (not printed); stdout shows
one summary line per call. A call that fails is recorded and never retried silently. Frames already answered
are skipped (no double spend).
"""
import base64, json, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as v

BUDGET = 30
URL = 'http://localhost:5173/api/analyze'
TASK = 'smoke-base-v1'
ledger_path = v.HERE / 'cosmos/ledger.json'
ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {'budget': BUDGET, 'attempts': []}
cands = {c['id']: c for c in json.loads((v.HERE / 'data/candidates.json').read_text())['candidates']}

for fid in sys.argv[1:]:
    if len(ledger['attempts']) >= BUDGET:
        print('BUDGET EXHAUSTED; stopping'); break
    raw_path = v.HERE / f'cosmos/raw/{fid}.json'
    if raw_path.exists():
        print(fid, 'already answered, skipped'); continue
    c = cands[fid]
    jpg = v.TOOLS / c['imagePath']
    sha = v.sha256_file(jpg)
    body = json.dumps({'image': 'data:image/jpeg;base64,' + base64.b64encode(jpg.read_bytes()).decode(), 'task': TASK}).encode()
    t0 = time.time(); started = datetime.now(timezone.utc).isoformat()
    entry = {'id': fid, 'imageSha256': sha, 'startedUtc': started, 'url': URL, 'task': TASK}
    try:
        req = urllib.request.Request(URL, body, {'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=200) as r:
            resp = json.loads(r.read())
        entry.update(ok=True, seconds=round(time.time() - t0, 2), httpOk=True)
        assert resp.get('imageSha256') == sha, 'gateway echoed a different image SHA'
        raw_path.write_text(json.dumps(resp, indent=1) + '\n')
        obs = resp.get('observation')
        entry['parsed'] = obs is not None
        print(f"{fid}: {entry['seconds']}s smoke={obs and obs['smoke']} base_visible={obs and obs['base_visible']} parsed={obs is not None}")
    except Exception as e:                                  # recorded, not retried
        entry.update(ok=False, seconds=round(time.time() - t0, 2), error=f'{type(e).__name__}: {str(e)[:300]}')
        print(f'{fid}: FAILED {entry["error"]}')
    ledger['attempts'].append(entry)
    ledger_path.write_text(json.dumps(ledger, indent=1) + '\n')
print('attempts used:', len(ledger['attempts']), '/', BUDGET)
