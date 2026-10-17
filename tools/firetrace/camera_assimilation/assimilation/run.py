#!/usr/bin/env python3
"""Camera-assisted fire-spread assimilation experiment (retrospective, Garnet Fire, 2025-08-27).

    python3 run.py --observations ../vision/observations.json --calibration ../calibration/printed_model.json \\
                   --output scenario.json [--allow-experimental] [--sensitivity]

Writes scenario.json (+ scenario.geojson next to it). Missing inputs -> status pending-inputs with the uncorrected baseline and
its FIRMS compatibility; unusable calibration / no usable camera row -> status disabled with reasons. Never fabricates a correction.
This is NOT an operational forecast: the initial state is reconstructed from detections and carries known retrospective leakage.
"""
import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from shapely.geometry import Point, Polygon, mapping, shape
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config as cfgmod  # noqa: E402
import data as dat  # noqa: E402
import dem as demmod  # noqa: E402
import experiment as exp  # noqa: E402
from grid import to_lonlat, to_xy  # noqa: E402

SCHEMA = 'firetrace-camera-assimilation-scenario-v1'
FIRETRACE = HERE.parents[1]
DEFAULT_SAT = FIRETRACE / 'evidence/garnet/satellite'
PREREG_FILE = HERE / 'preregistration.json'


def jdefault(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.bool_):
        return bool(o)
    raise TypeError(type(o))


def clean(o):
    """Recursively replace non-finite floats with None so the JSON is strict."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def preregistration_doc(cfg):
    return {'schema': 'firetrace-assimilation-preregistration-v1', 'configSha256': cfgmod.config_sha256(cfg), 'config': cfg,
            'rules': [
                'Camera rows enter a forecast cycle only if their timestamp is at or before the cycle issue time; the verified pass must be strictly after the issue time.',
                'FIRMS detections are never assimilated. Passes at or before t0 are initialization data and are never scored. A pass consumed by a calibration fit is never scored.',
                'Printed-X model (no FIRMS fitted): every FIRMS pass after t0 is validation-eligible. Fitted contrast model: only B held-out passes.',
                'No parameter, width, threshold or gate is chosen by looking at any validation score. Sensitivities are reported, not selected from.',
                'Baseline = same model, same initialization, neutral parameters, no camera. It is always retained and always scored at the same pass time.',
                'Verdict on the primary metric only (median nearest active-band distance, tolerance verdictDeltaM); worse results are reported as worse.'],
            'status': 'frozen in code before any camera observation (vision/observations.json) existed and before any real validation score was computed',
            'limitation': 'A hash in a file is not an external timestamp: commit this file before running the real data to make the order auditable.'}


def footprint(grid, idx):
    if len(idx) == 0:
        return None
    polys = [Polygon(grid.cell_polygon(i)) for i in idx]
    return mapping(unary_union(polys).simplify(0.00004))


def wedge_polygon(lon, lat, bearing, half_deg, radius_m=35000.0, n=24):
    pts = [(lon, lat)]
    for k in range(n + 1):
        b = math.radians(bearing - half_deg + 2 * half_deg * k / n)
        x, y = to_xy(lon, lat)
        lo, la = to_lonlat(float(x) + radius_m * math.sin(b), float(y) + radius_m * math.cos(b))
        pts.append((round(float(lo), 5), round(float(la), 5)))
    pts.append((lon, lat))
    return {'type': 'Polygon', 'coordinates': [[list(p) for p in pts]]}


def ray_line(lon, lat, bearing, radius_m=35000.0):
    x, y = to_xy(lon, lat)
    b = math.radians(bearing)
    lo, la = to_lonlat(float(x) + radius_m * math.sin(b), float(y) + radius_m * math.cos(b))
    return {'type': 'LineString', 'coordinates': [[lon, lat], [round(float(lo), 5), round(float(la), 5)]]}


def cycle_public(c, geoms_note=True):
    return {'cycleId': c['cycleId'], 'issueUtc': c['issueUtc'], 'status': c['status'], 'reason': c['reason'],
            'observationIds': c['observationIds'], 'ess': round(c['ess'], 2), 'essFraction': round(c['essFraction'], 4),
            'klNats': round(c['klNats'], 4), 'identifiedParameters': c['identifiedParameters'], 'wedgeCells': c['wedgeCells'],
            'likelihood': c['likelihood'],
            'parameters': [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in p.items()} for p in c['parameters']],
            'rows': [{k: r[k] for k in ('id', 'cameraId', 'poseId', 'timeUtc', 'x_base', 'bearingDeg', 'sigmaDeg', 'sigmaCalDeg', 'sigmaPixDeg',
                                        'sigmaSource', 'usedInCalibrationFit', 'cameraPositionStatus')} for r in c['rows']]}


def build(args):
    t_start = time.time()
    cfg = json.loads(json.dumps(cfgmod.CONFIG))
    if args.members:
        cfg['ensemble']['members'] = args.members
    if args.clock_sigma_min is not None:
        cfg['clock']['clockSigmaMin'] = args.clock_sigma_min
    if args.t0:
        cfg['t0']['primary'] = args.t0
    cfg_sha = cfgmod.config_sha256(cfg)
    prereg_match = None
    if PREREG_FILE.exists():
        prereg_match = json.loads(PREREG_FILE.read_text()).get('configSha256') == cfg_sha

    sat = dat.load_satellite(args.sat_dir)
    grid, elev, dem_receipt = demmod.load()
    t0 = dat.parse_epoch(cfg['t0']['primary'])
    obs_doc, obs_status, obs_detail = dat.load_observations(args.observations)
    cal, cal_status, cal_detail = dat.load_calibration(args.calibration)
    pass_table = dat.pass_table(sat)
    split = dat.split_from_calibration(cal if cal_status == 'ok' else None, cfg, list(pass_table))
    day_end = dat.parse_epoch('2025-08-28T00:00:00-07:00')

    usable, excluded = [], []
    if obs_status == 'ok' and cal_status == 'ok' and not args.paused_reason:
        usable, excluded = dat.gate_observations(obs_doc, cal, cfg, args.method, args.allow_experimental, t0, day_end, args.sigma_prior_deg)
    last_obs = max((r['t'] for r in usable), default=None)
    limit = max(t0 + cfg['validation']['maxEvalLeadFromT0Min'] * 60, (last_obs or 0) + cfg['validation']['maxEvalLeadFromLastObsMin'] * 60)

    if args.paused_reason:
        status, reason = 'paused-next-phase', args.paused_reason
    elif obs_status != 'ok' or cal_status != 'ok':
        status = 'pending-inputs' if 'missing' in (obs_status, cal_status) else 'disabled'
        reason = '; '.join(x for x in (
            None if obs_status == 'ok' else 'observations %s: %s' % (obs_status, obs_detail),
            None if cal_status == 'ok' else 'calibration %s: %s' % (cal_status, cal_detail)) if x)
    elif not usable:
        status, reason = 'disabled', 'no camera row passed the gates (see excludedObservations): corrections disabled, baseline kept'
    else:
        status, reason = 'completed', None

    passes_table, roles = exp.eval_passes(sat, split, t0, limit)
    cam_lonlat = {}
    for r in usable:
        cam_lonlat[r['cameraId']] = r['cameraLonLat']
    members, seed = cfg['ensemble']['members'], cfg['ensemble']['seed']
    primary = exp.run_variant(sat, grid, elev, cfg, cfg['t0']['primary'], cfg['initialization']['primary'] and 'support', usable, cam_lonlat,
                              passes_table, roles, members, seed)
    baseline_rows, verif_rows = exp.score(sat, grid, cfg, primary, passes_table, roles)
    aggregate = exp.aggregate(verif_rows)
    ctx = primary['ctx']

    # ---- sensitivities (summaries only)
    sens = []
    if args.sensitivity:
        variants = [('init-with-interpolated-cells', dict(init='with-interpolated')),
                    ('t0-04:00-PDT', dict(t0=cfg['t0']['sensitivity'][0])),
                    ('head-fraction-0.5', dict(head=0.5)), ('head-fraction-0.85', dict(head=0.85))]
        if usable and any(r.get('calibrationBasis', '').startswith('printed-x') for r in usable):
            variants += [('printed-sigma-%gdeg' % s, dict(sigma=s)) for s in cfg['observationModel']['printedPriorSensitivityDeg']]
        variants += [('clock-sigma-%gmin' % m, dict(clock=m)) for m in cfg['clock']['sensitivityMin']]
        for name, kw in variants:
            vcfg = json.loads(json.dumps(cfg))
            rows_v = usable
            if 'clock' in kw:
                vcfg['clock']['clockSigmaMin'] = kw['clock']
            if 'sigma' in kw:
                rows_v, _ = dat.gate_observations(obs_doc, cal, vcfg, args.method, args.allow_experimental, t0, day_end, kw['sigma'])
            t0v = kw.get('t0', cfg['t0']['primary'])
            run = exp.run_variant(sat, grid, elev, vcfg, t0v, kw.get('init', 'support'), rows_v, cam_lonlat, passes_table,
                                  exp.eval_passes(sat, split, dat.parse_epoch(t0v), limit)[1], members, seed, head_fraction=kw.get('head'))
            _, vrows = exp.score(sat, grid, vcfg, run, passes_table, exp.eval_passes(sat, split, dat.parse_epoch(t0v), limit)[1])
            sens.append({'variant': name, 'cyclesUpdated': sum(c['status'] == 'updated' for c in run['cycles']), 'cycles': len(run['cycles']),
                         'aggregate': exp.aggregate(vrows),
                         'baselineMedianNearestM': [r['metrics']['baseline']['medianNearestActiveBandM'] for r in vrows],
                         'correctedMedianNearestM': [r['metrics']['corrected']['medianNearestActiveBandM'] for r in vrows]})

    # ---- initialization block
    init_idx, init_rel = dat.init_cells(grid, sat['arrival'], t0, 'support')
    alt_idx, _ = dat.init_cells(grid, sat['arrival'], t0, 'with-interpolated')
    cells_all = dat.init_cells(grid, sat['arrival'], t0, 'with-interpolated')[0]
    init_block = {
        't0': cfg['t0']['primary'], 't0Utc': dat.utc_iso(t0), 'source': 'evidence/garnet/satellite/arrival-reconstructed.geojson',
        'mode': 'observed-support-le-t0', 'cells': int(len(init_idx)), 'cellAreaHaTotal': round(len(init_idx) * grid.cell ** 2 / 1e4, 1),
        'dataClass': 'reconstructed', 'retrospectiveLeakage': True, 'operationalForecast': False,
        'restrictedToSupportObservedLeT0': True,
        'leakage': [
            'The reconstruction exists only inside the FINAL WFIGS perimeter (known in hindsight) and hotspots.geojson only holds detections within ~1 km of it.',
            'Cells keep only their own first VIIRS detection <= t0 (kind=observed-support); interpolated cells (filled from neighbours, possibly later detections) are excluded from the primary run.',
            'Each detection burns a 400 m radius, so the footprint overestimates early extent (published-acre ratios 1.4-1.5).',
            'Initial front = every footprint cell with a free neighbour starts spreading at t0: activity is assumed uniform around the perimeter.'],
        'alternativeWithInterpolatedCells': {'cells': int(len(alt_idx)), 'extraCells': int(len(set(alt_idx.tolist()) - set(init_idx.tolist()))),
                                             'effect': 'reported in sensitivity[init-with-interpolated-cells]' if args.sensitivity else 'not run (use --sensitivity)'},
        'passesAtOrBeforeT0': [pid for pid, (role, _) in roles.items() if role == 'initialization-not-scored'],
        'daily extent reconstructed is not truth': True,
    }
    init_block.pop('daily extent reconstructed is not truth')
    init_block['dailyExtentNote'] = 'Daily reconstructed extent is not used as truth anywhere; validation is FIRMS only.'

    # ---- camera model block (UI)
    basis = dat.calibration_basis(cal) if cal_status == 'ok' else None
    printed = basis is not None and str(basis).startswith('printed-x')
    poses_ui = []
    if cal_status == 'ok':
        for p in cal['poses']:
            poses_ui.append({k: p.get(k) for k in ('cameraId', 'poseId', 'method', 'status', 'yaw0Deg', 'fovDeg', 'calibrationBasis',
                                                    'parameterOrigin', 'reason', 'fovStatus')})
    sig_src = sorted({r['sigmaSource'] for r in usable})
    camera_model = {
        'calibrationBasis': basis, 'parameterOrigin': sorted({p.get('parameterOrigin') for p in cal.get('poses', []) if p.get('parameterOrigin')}) if cal_status == 'ok' else None,
        'calibrationStatus': (cal or {}).get('status') if cal_status == 'ok' else cal_status, 'calibrationPath': str(args.calibration),
        'calibrationSha256': sha(args.calibration) if cal_status == 'ok' else None, 'poses': poses_ui,
        'angularSigmaDegByRow': {r['id']: round(r['sigmaDeg'], 3) for r in usable}, 'angularSigmaSource': sig_src,
        'clock': {'status': 'assumed-PDT', 'sigmaMin': cfg['clock']['clockSigmaMin'], 'verified': False,
                  'note': 'printed time read as PDT is a hypothesis; the clock uncertainty widens the model active window, it does not correct the clock'},
        'historicalXStatus': ('printed X is read as an ASSUMED azimuth from 2025 video overlays; it is unverified for 2025 and today\'s camera error is not historical precision'
                              if printed else 'not a printed-X model' if basis else None),
        'fittedToFirms': (not printed) and basis is not None,
        'bearingFormula': 'bearingDeg = (yaw0Deg + degrees(atan((2*x_base - 1) * tan(radians(fovDeg)/2)))) mod 360',
        'experimentalAccepted': ('printed-X basis accepted by design' if printed else ('--allow-experimental' if args.allow_experimental else 'no')),
    }

    # ---- forecasts + geojson
    features = []
    fid = [0]

    def add(geom, **props):
        if geom is None:
            return None
        fid[0] += 1
        props['featureId'] = 'F%04d' % fid[0]
        features.append({'type': 'Feature', 'geometry': geom, 'properties': props})
        return props['featureId']

    add(footprint(grid, init_idx), kind='initialization-footprint', dataClass='reconstructed', t0Utc=dat.utc_iso(t0),
        label='Footprint reconstruido ≤ t0 (soporte observado; fuga retrospectiva)')
    forecasts = []
    base = ctx.base_arr

    def new_cells(arr, rel):
        return np.where((arr > 0) & (arr <= rel))[0]

    for c in primary['cycles']:
        for lead in cfg['cycles']['forecastLeadsMin']:
            valid = c['issueEpoch'] + lead * 60
            rel = (valid - t0) / 60.0
            nb, nc = new_cells(base, rel), new_cells(c['corrected_arr'], rel)
            same = set(nb.tolist()) == set(nc.tolist())
            fb = add(footprint(grid, nb), kind='forecast-footprint', product='baseline', dataClass='modeled', cycleId=c['cycleId'],
                     issueUtc=c['issueUtc'], validUtc=dat.utc_iso(valid), leadMin=lead, cells=int(len(nb)))
            fc = fb if same else add(footprint(grid, nc), kind='forecast-footprint', product='corrected', dataClass='modeled', cycleId=c['cycleId'],
                                     issueUtc=c['issueUtc'], validUtc=dat.utc_iso(valid), leadMin=lead, cells=int(len(nc)))
            if not same:
                add(footprint(grid, np.setdiff1d(nc, nb)), kind='forecast-delta', product='corrected-added', dataClass='modeled',
                    cycleId=c['cycleId'], validUtc=dat.utc_iso(valid), leadMin=lead)
                add(footprint(grid, np.setdiff1d(nb, nc)), kind='forecast-delta', product='corrected-removed', dataClass='modeled',
                    cycleId=c['cycleId'], validUtc=dat.utc_iso(valid), leadMin=lead)
            forecasts.append({'cycleId': c['cycleId'], 'issueUtc': c['issueUtc'], 'validUtc': dat.utc_iso(valid), 'leadMin': lead,
                              'geometryTime': 'issue + lead (nominal); metrics are evaluated at the real pass time, not here',
                              'baseline': {'featureId': fb, 'newBurnedCells': int(len(nb))},
                              'corrected': {'featureId': fc, 'newBurnedCells': int(len(nc)), 'identicalToBaseline': same,
                                            'cellsChanged': int(len(set(nb.tolist()) ^ set(nc.tolist())))}, 'cycleStatus': c['status']})
    for v in verif_rows:
        p = passes_table[v['passId']]
        rel = (p['t'] - t0) / 60.0
        c = next(x for x in primary['cycles'] if x['cycleId'] == v['cycleId'])
        nb, nc = new_cells(base, rel), new_cells(c['corrected_arr'], rel)
        add(footprint(grid, nb), kind='verification-footprint', product='baseline', dataClass='modeled', passId=v['passId'],
            validUtc=v['passUtc'], cycleId=v['cycleId'], actualLeadMin=v['actualLeadMin'], cells=int(len(nb)))
        if set(nb.tolist()) != set(nc.tolist()):
            add(footprint(grid, nc), kind='verification-footprint', product='corrected', dataClass='modeled', passId=v['passId'],
                validUtc=v['passUtc'], cycleId=v['cycleId'], actualLeadMin=v['actualLeadMin'], cells=int(len(nc)))
    for r in baseline_rows:
        if r['passId'] not in {v['passId'] for v in verif_rows}:
            p = passes_table[r['passId']]
            add(footprint(grid, new_cells(base, (p['t'] - t0) / 60.0)), kind='verification-footprint', product='baseline', dataClass='modeled',
                passId=r['passId'], validUtc=r['passUtc'], cycleId=None, leadFromT0Min=r['leadFromT0Min'])
    for pid, p in primary['eval_list']:
        det = dat.pass_detections(sat, p['source'], p['t'])
        for lon, lat, frp, px in zip(det['lon'], det['lat'], det['frp'], det['pixelM']):
            add({'type': 'Point', 'coordinates': [float(lon), float(lat)]}, kind='validation-detection', dataClass='observed', passId=pid,
                role=roles[pid][0], source=p['source'], passUtc=dat.utc_iso(p['t']), frpMW=float(frp), pixelM=int(px))
    for cam, ll in cam_lonlat.items():
        add({'type': 'Point', 'coordinates': [ll[0], ll[1]]}, kind='camera', dataClass='candidate-position', cameraId=cam,
            positionStatus=next(r['cameraPositionStatus'] for r in usable if r['cameraId'] == cam))
    for c in primary['cycles']:
        for r in c['rows']:
            ll = r['cameraLonLat']
            sw = max(cfg['observationModel']['wedgeSigmaFactor'] * r['sigmaDeg'], cfg['observationModel']['wedgeMinSigmaDeg'])
            add(wedge_polygon(ll[0], ll[1], r['bearingDeg'], sw), kind='camera-bearing-wedge', dataClass='camera-observation-assumed-azimuth',
                observationId=r['id'], cycleId=c['cycleId'], timeUtc=r['timeUtc'], bearingDeg=round(r['bearingDeg'], 2), halfWidthDeg=round(sw, 2),
                sigmaDeg=round(r['sigmaDeg'], 2), meaning='angular compatibility sector; range along the ray is NOT inferred')
            add(ray_line(ll[0], ll[1], r['bearingDeg']), kind='camera-bearing-ray', dataClass='camera-observation-assumed-azimuth',
                observationId=r['id'], cycleId=c['cycleId'], timeUtc=r['timeUtc'])

    used_ids = sorted({i for c in primary['cycles'] for i in c['observationIds']})
    eff_ids = sorted({i for c in primary['cycles'] if c['status'] == 'updated' for i in c['observationIds']})
    id_list = {
        't0Id': 't0-' + cfg['t0']['primary'], 'configSha256': cfg_sha,
        'assimilatedObservationIds': used_ids, 'effectiveObservationIds': eff_ids,
        'excludedObservations': excluded,
        'reservedByCalibrationSplit': [e['id'] for e in excluded if e['reason'] == 'calibration-held-out-observation'],
        'observationsUsedInCalibrationFit': sorted(r['id'] for r in usable if r['usedInCalibrationFit']),
        'cycles': [{'cycleId': c['cycleId'], 'issueUtc': c['issueUtc'], 'observationIds': c['observationIds'], 'status': c['status']} for c in primary['cycles']],
        'passRoles': {pid: {'role': role, 'reason': why, 'utc': dat.utc_iso(passes_table[pid]['t'])} for pid, (role, why) in roles.items()
                      if passes_table[pid]['t'] >= t0 - 24 * 3600},
        'splitSource': split['source'], 'calibrationFitPassIds': split['fit'],
        'validationPassIds': sorted(pid for pid, (role, _) in roles.items() if role == 'validation'),
        'diagnosticPassIds': sorted(pid for pid, (role, _) in roles.items() if role == 'diagnostic'),
        'unmatchedNominalLeads': primary['unmatched']}

    n_updated = sum(c['status'] == 'updated' for c in primary['cycles'])
    if status == 'completed':
        outcome = ('no-camera-effect' if n_updated == 0 else
                   'corrected-worsened' if aggregate['worsened'] > aggregate['improved'] else
                   'corrected-improved' if aggregate['improved'] > aggregate['worsened'] else 'mixed-or-unchanged')
    else:
        outcome = 'disabled'
    dc = [
        {'name': 'FIRMS detections', 'class': 'observed', 'use': 'validation only (never assimilated); passes <= t0 initialization only', 'source': 'hotspots.geojson'},
        {'name': 'Open-Meteo wind', 'class': 'modeled-reanalysis', 'use': 'hourly wind of ONE grid point, nearest hour', 'source': 'weather-hourly.json'},
        {'name': 'arrival-reconstructed', 'class': 'reconstructed', 'use': 'initial footprint <= t0 (support-only); retrospective leakage', 'source': 'arrival-reconstructed.geojson'},
        {'name': 'DEM', 'class': 'observed-terrain-model', 'use': '200 m mean of AWS Terrarium z12', 'source': 'assimilation/dem/receipt.json'},
        {'name': 'camera observations', 'class': 'camera-observation (pending operator review)', 'use': 'bearing intervals only', 'source': str(args.observations)},
        {'name': 'camera azimuth model', 'class': 'assumed' if printed else 'experimental-fit', 'use': 'x_base -> bearing', 'source': str(args.calibration)},
        {'name': 'baseline / corrected / neutral ensemble', 'class': 'modeled', 'use': 'heuristic minimum-travel-time spread; uniform fuel assumed', 'source': 'run.py'}]
    limitations = [
        'Retrospective research, not an operational forecast: the initial state is reconstructed from detections inside the final perimeter (retrospective leakage).',
        'Heuristic spread law from simulation.py (not Rothermel/FARSITE); coefficients and the 4 m/min base rate are unvalidated and were not tuned to this fire.',
        'Fuel is uniform and hypothetical; humidity is not fuel moisture; wind is one reanalysis point ~15 km from the fire; no spotting, suppression, plume dynamics.',
        'A single bearing is a set-valued angular constraint, not a location: range along the line of sight is unidentified; two different plumes are never triangulated.',
        'Camera clock (assumed PDT) is a hypothesis; clock sigma widens the model active window but does not verify the clock.',
        ('Printed X read as an assumed azimuth is unverified for 2025; the angular prior (default 3 deg) is declared, not measured.' if printed else
         'The fitted yaw is a 1-DOF experimental fit with an unverified FOV prior; B held-out residuals are never used to size uncertainty here.'),
        'FIRMS pixel centres are not fire area/front/speed; absence of a detection is not absence of fire. Precision is dominated by pass sparsity: read only baseline-vs-corrected differences.',
        'Passes are not independent of each other or of the cameras (same fire, same day). Few verifications: no statistical significance is claimed.',
        'Baseline and corrected both integrate from t0; the camera changes ensemble parameters retroactively. Lead is time from camera issue to the pass, not from t0.',
        'Camera cadence in this footage is irregular; the experiment does not show corrections every minute.',
        'Agent-read camera rows are not human review (reviewStatus pending-operator-review).']

    scenario = {
        'schema': SCHEMA, 'status': status, 'statusReason': reason, 'outcome': outcome, 'retrospective': True, 'operationalForecast': False,
        'generatedBy': 'camera_assimilation/assimilation/run.py', 'runSeconds': round(time.time() - t_start, 1),
        'dataClasses': dc, 'initialization': init_block, 'cameraModel': camera_model,
        'cameraUseCount': len(used_ids), 'cameraEffectiveCount': len(eff_ids),
        'cameraUseNote': 'cameraUseCount = distinct observation ids that entered a cycle likelihood; cameraEffectiveCount = ids of cycles that passed the ESS/information/identifiability gates and changed parameters',
        'idList': id_list,
        'preregistration': {'configSha256': cfg_sha, 'matchesPreregistrationFile': prereg_match, 'file': 'assimilation/preregistration.json',
                            'config': cfg, 'causalRule': 'rows with timestamp <= cycle issue time; pass strictly after issue time',
                            'noTuningOnValidation': True,
                            'statement': 'Configuration is fixed in code; no value was chosen after seeing any validation score. A file hash is not an external timestamp.'},
        'model': {'grid': grid.spec(), 'dem': {k: dem_receipt[k] for k in ('source', 'status', 'stats', 'npzSha256')},
                  'demTiles': len(dem_receipt['tiles']), 'weather': {'point': sat['weather']['point'], 'status': sat['weather']['status']},
                  'members': members, 'seed': seed, 'baselineTheta': 'windBias 0, speedMult 1, all sector multipliers 1',
                  'inputSha256': sat['sha256'], 'observationsSha256': sha(args.observations) if obs_status == 'ok' else None},
        'baseline': {'description': 'same initialization and model, neutral parameters, no camera; scored at every eligible pass time (lead measured from t0)',
                     'leadFromT0': 'see rows', 'passes': baseline_rows},
        'corrected': ({'status': 'disabled', 'reason': reason} if status != 'completed' else
                      {'status': 'completed', 'cycles': [cycle_public(c) for c in primary['cycles']],
                       'note': 'corrected = baseline outside the camera viewing wedge; inside it the posterior-ensemble median arrival'}),
        'forecasts': forecasts,
        'metrics': {'primaryMetric': cfg['validation']['primaryMetric'], 'verdictDeltaM': cfg['validation']['verdictDeltaM'],
                    'toleranceM': cfg['validation']['tolM'], 'activeBandMin': cfg['validation']['activeBandMin'],
                    'definitions': {
                        'medianNearestActiveBandM': 'median distance from each FIRMS detection of the pass to the nearest modelled cell that burned in the last 60 min before the pass',
                        'recallGrowth': 'fraction of detections farther than tol from the initial footprint that lie within tol of a modelled newly burned cell',
                        'precisionActive/recallActive': 'active-band cells with a detection within tol / detections within tol of an active-band cell',
                        'lead': 'actualLeadMin = pass time - cycle issue time (issue = latest camera frame in the cycle)'},
                    'verifications': verif_rows, 'aggregate': aggregate,
                    'unmatchedNominalLeads': primary['unmatched'],
                    'worsenedDisclosure': [r['passId'] + ' @' + r['cycleId'] for r in verif_rows if r['verdictCorrectedVsBaseline'] == 'worsened']},
        'sensitivity': sens if args.sensitivity else 'not run (use --sensitivity)',
        'excludedObservations': excluded, 'limitations': limitations,
        'geojson': 'scenario.geojson'}
    geo = {'type': 'FeatureCollection', 'properties': {
        'schema': 'firetrace-camera-assimilation-map-v1', 'scenarioSchema': SCHEMA, 'status': status, 'retrospective': True,
        'operationalForecast': False, 'featureKinds': ['initialization-footprint', 'forecast-footprint', 'forecast-delta', 'verification-footprint',
                                                       'validation-detection', 'camera', 'camera-bearing-wedge', 'camera-bearing-ray'],
        'note': 'modeled footprints list cells that burn after t0 (union with initialization-footprint for total); none is an observed perimeter'},
        'features': features}
    return clean(scenario), clean(geo)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--observations')
    ap.add_argument('--calibration')
    ap.add_argument('--output')
    ap.add_argument('--allow-experimental', action='store_true', help='accept experimental FITTED calibrations (printed-X basis is accepted by design)')
    ap.add_argument('--method', default='cosmos', choices=['cosmos', 'simple-detector'])
    ap.add_argument('--sensitivity', action='store_true')
    ap.add_argument('--members', type=int, default=0)
    ap.add_argument('--sigma-prior-deg', type=float, default=None, help='override the printed-X angular prior (deg, treated as 1 sigma)')
    ap.add_argument('--clock-sigma-min', type=float, default=None)
    ap.add_argument('--t0', default=None)
    ap.add_argument('--sat-dir', default=str(DEFAULT_SAT))
    ap.add_argument('--paused-reason', default=None, help='pause camera assimilation (status paused-next-phase): baseline kept, zero camera use')
    ap.add_argument('--write-preregistration', action='store_true')
    args = ap.parse_args(argv)
    if args.write_preregistration:
        PREREG_FILE.write_text(json.dumps(preregistration_doc(cfgmod.CONFIG), indent=1) + '\n')
        print('wrote', PREREG_FILE, cfgmod.config_sha256())
        return 0
    if not (args.observations and args.calibration and args.output):
        ap.error('--observations, --calibration and --output are required')
    scenario, geo = build(args)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(scenario, indent=1, allow_nan=False, default=jdefault) + '\n')
    gj = out.with_suffix('.geojson')
    gj.write_text(json.dumps(geo, separators=(',', ':'), allow_nan=False, default=jdefault) + '\n')
    print('status=%s outcome=%s cameraUse=%d cycles=%d -> %s (%d bytes), %s (%d bytes)' % (
        scenario['status'], scenario['outcome'], scenario['cameraUseCount'], len(scenario['corrected'].get('cycles', [])),
        out, out.stat().st_size, gj, gj.stat().st_size))
    return 0


if __name__ == '__main__':
    sys.exit(main())
