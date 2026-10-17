"""Loaders and gates: Garnet satellite layers, camera observations, calibration poses.

Nothing here reads FIRMS for assimilation. Calibration sigma comes from the declared printed-X angular prior or, for a fitted
model, from FIT-ONLY components; fields that include held-out residuals (heldOut*, errors.heldOut, and suggestedAngularHalfWidthDeg
of a FITTED model) are never read.
"""
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from grid import to_xy

SOURCE_SHORT = {'VIIRS_SNPP_SP': 'SNPP', 'VIIRS_NOAA20_SP': 'NOAA20', 'VIIRS_NOAA21_NRT': 'NOAA21', 'MODIS_SP': 'MODIS'}
OBSERVATIONS_SCHEMA = 'firetrace-camera-observations-v1'
CALIBRATION_SCHEMA = 'firetrace-camera-calibration-v1'
NEGATIVE_STATUS = ('no-calibration', 'disabled', 'uncalibratable', 'rejected', 'failed', 'unavailable', 'pending')
# Components of B's uncertainty block that do NOT use held-out residuals (fit passes, position prior, FOV prior, tilt prior).
FIT_ONLY_COMPONENTS = ('fitPassSectorMaxHalfWidthDeg', 'positionShift100mMaxYaw0Deg', 'fovPriorMaxYaw0ShiftDeg', 'neglectedTiltBoundDeg')


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_iso(epoch):
    return datetime.fromtimestamp(float(epoch), timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_epoch(text):
    s = str(text)
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError('timestamp without timezone: %r' % text)
    return dt.timestamp()


def pass_id(source, t):
    return '%s@%s' % (SOURCE_SHORT.get(source, source), utc_iso(t))


# ------------------------------------------------------------------ satellite layers

def load_satellite(directory):
    d = Path(directory)
    hot = json.loads((d / 'hotspots.geojson').read_text())['features']
    lon = np.array([f['geometry']['coordinates'][0] for f in hot])
    lat = np.array([f['geometry']['coordinates'][1] for f in hot])
    props = [f['properties'] for f in hot]
    hotspots = {'lon': lon, 'lat': lat, 't': np.array([p['t'] for p in props], dtype=np.int64),
                'source': np.array([p['source'] for p in props]), 'pixelM': np.array([p['pixelM'] for p in props]),
                'frp': np.array([p['frpMW'] for p in props])}
    overpasses = json.loads((d / 'overpasses.json').read_text())['overpasses']
    weather = json.loads((d / 'weather-hourly.json').read_text())
    hours = weather['hours']
    wx = {'epoch': np.array([parse_epoch(h['timeUtc']) for h in hours]), 'from': np.array([h['windFromDeg'] for h in hours], float),
          'speed': np.array([h['windSpeedMps'] for h in hours], float), 'point': weather['point'], 'status': weather['status']}
    arrival = json.loads((d / 'arrival-reconstructed.geojson').read_text())['features']
    cl, cb, ct, ck = [], [], [], []
    for f in arrival:
        ring = np.array(f['geometry']['coordinates'][0])
        cl.append((ring[:, 0].min() + ring[:, 0].max()) / 2)
        cb.append((ring[:, 1].min() + ring[:, 1].max()) / 2)
        ct.append(f['properties']['t'])
        ck.append(f['properties']['kind'])
    arr = {'lon': np.array(cl), 'lat': np.array(cb), 't': np.array(ct, dtype=np.int64), 'kind': np.array(ck)}
    hashes = {n: sha256_file(d / n) for n in ('hotspots.geojson', 'overpasses.json', 'weather-hourly.json', 'arrival-reconstructed.geojson')}
    return {'hotspots': hotspots, 'overpasses': overpasses, 'weather': wx, 'arrival': arr, 'sha256': hashes}


def init_cells(grid, arrival, t0_epoch, mode):
    """Cells burned at t0 and their reconstructed arrival (minutes relative to t0, <= 0).
    mode 'support': kind == observed-support and own first detection <= t0 (no interpolated cells).
    mode 'with-interpolated': every arrival-reconstructed cell with t <= t0 (includes cells filled from neighbours)."""
    keep = arrival['t'] <= t0_epoch
    if mode == 'support':
        keep &= arrival['kind'] == 'observed-support'
    elif mode != 'with-interpolated':
        raise ValueError(mode)
    idx = grid.index_of_lonlat(arrival['lon'][keep], arrival['lat'][keep])
    rel = (arrival['t'][keep] - t0_epoch) / 60.0
    ok = idx >= 0
    idx, rel = idx[ok], rel[ok]
    order = np.argsort(rel)
    uniq, first = np.unique(idx[order], return_index=True)
    return uniq, rel[order][first]


def pass_detections(sat, source, t):
    h = sat['hotspots']
    m = (h['t'] == t) & (h['source'] == source)
    return {'lon': h['lon'][m], 'lat': h['lat'][m], 'pixelM': h['pixelM'][m], 'frp': h['frp'][m]}


def pass_table(sat):
    return {pass_id(o['source'], o['t']): {'source': o['source'], 't': int(o['t']), 'detections': o['detections'], 'totalFrpMW': o['totalFrpMW']}
            for o in sat['overpasses']}


# ------------------------------------------------------------------ observations

def load_observations(path):
    """Return (doc, status, detail). status: ok | missing | invalid."""
    p = Path(path)
    if not p.exists():
        return None, 'missing', 'file not found: %s' % path
    try:
        doc = json.loads(p.read_text())
    except (OSError, ValueError) as error:
        return None, 'invalid', str(error)
    if not isinstance(doc, dict) or doc.get('schema') != OBSERVATIONS_SCHEMA or not isinstance(doc.get('observations'), list):
        return None, 'invalid', 'expected schema %s with an observations array' % OBSERVATIONS_SCHEMA
    return doc, 'ok', None


def load_calibration(path):
    p = Path(path)
    if not p.exists():
        return None, 'missing', 'file not found: %s' % path
    try:
        doc = json.loads(p.read_text())
    except (OSError, ValueError) as error:
        return None, 'invalid', str(error)
    if (not isinstance(doc, dict) or not str(doc.get('schema', '')).startswith('firetrace-camera-calibration')
            or not isinstance(doc.get('poses'), list)):
        return None, 'invalid', 'expected a firetrace-camera-calibration* schema with a poses array'
    return doc, 'ok', None


def is_printed_basis(entry, cal=None):
    """Printed-X azimuth model: yaw is an ASSUMED prior (never fitted to FIRMS), so no pass is consumed by calibration."""
    basis = (entry or {}).get('calibrationBasis') or (cal or {}).get('calibrationBasis') or ''
    return str(basis).startswith('printed-x')


def calibration_basis(cal):
    if not cal:
        return None
    bases = {p.get('calibrationBasis') or cal.get('calibrationBasis') for p in cal.get('poses', []) if p.get('yaw0Deg') is not None}
    bases.discard(None)
    return sorted(bases)[0] if len(bases) == 1 else ('mixed' if bases else cal.get('calibrationBasis'))


def split_from_calibration(cal, cfg, all_pass_ids):
    """Pass roles for C. Printed-X model: nothing was fitted, so every pass after t0 is eligible for validation.
    Fitted model (contrast): B's frozen fit passes are never scored; its held-out passes are the validation set."""
    v = cfg['validation']
    entries = [p for p in (cal or {}).get('poses', []) if p.get('yaw0Deg') is not None]
    if cal is not None and entries and all(is_printed_basis(p, cal) for p in entries):
        fit = set()
        for p in entries:
            fit.update(p.get('trainingPassIds') or [])
        return {'fit': sorted(fit), 'heldOut': sorted(set(all_pass_ids) - fit), 'extraCheck': [], 'source': 'printed-x-model: no FIRMS pass fitted; all passes eligible'}
    fit, held, extra = set(), set(), set()
    poses = ((cal or {}).get('frozenSplit') or {}).get('poses') or {}
    for role in poses.values():
        fit.update(role.get('fit', []))
        held.update(role.get('heldOut', []))
        extra.update(role.get('extraCheck', []))
    if not (fit or held):
        fit, held, extra = set(v['defaultFitPassIds']), set(v['defaultHeldOutPassIds']), set(v['defaultExtraCheckPassIds'])
        source = 'config-default (contract split)'
    else:
        source = 'calibration.frozenSplit'
    held -= fit
    extra -= fit | held
    return {'fit': sorted(fit), 'heldOut': sorted(held), 'extraCheck': sorted(extra), 'source': source}


def find_pose(cal, camera_id, pose_id, method):
    for entry in cal['poses']:
        if entry.get('cameraId') == camera_id and entry.get('poseId') == pose_id and entry.get('method') in (method, None):
            return entry
    return None


def camera_position(cal, camera_id):
    pos = ((cal.get('positions') or {}).get(camera_id) or {})
    c = pos.get('coordinates') if isinstance(pos, dict) else pos
    if isinstance(c, (list, tuple)) and len(c) >= 2 and all(isinstance(v, (int, float)) for v in c[:2]):
        return float(c[0]), float(c[1]), pos.get('status', 'unknown') if isinstance(pos, dict) else 'unknown'
    return None


PRINTED_PRIOR_KEYS = ('priorAngularDeg', 'angularPriorDeg', 'priorAngularHalfWidthDeg', 'suggestedAngularHalfWidthDeg')


def pose_sigma_cal(entry, cal, cfg, override_deg=None):
    """Calibration angular sigma (deg) and its provenance, without ever reading a held-out-derived quantity.
    Printed-X model: the declared angular PRIOR (nothing was evaluated against FIRMS to produce it); config default if absent.
    Fitted model: half the fit-only envelope (fit sector, 100 m position shift, FOV prior shift, tilt bound)."""
    om = cfg['observationModel']
    if is_printed_basis(entry, cal):
        if override_deg is not None:
            return max(om['sigmaFloorDeg'], float(override_deg)), 'cli-override-prior', {}
        u = entry.get('uncertainty') if isinstance(entry.get('uncertainty'), dict) else {}
        if u.get('holdoutEvaluated') is True:  # the declared width may then include held-out results: do not read it
            u = {}
        for k in PRINTED_PRIOR_KEYS:
            if isinstance(u.get(k), (int, float)) and not isinstance(u.get(k), bool) and u[k] > 0:
                return max(om['sigmaFloorDeg'], float(u[k])), 'calibration.uncertainty.' + k, {k: float(u[k])}
        return max(om['sigmaFloorDeg'], om['printedPriorSigmaDeg']), 'config-default-prior', {}
    u = entry.get('uncertainty')
    if not isinstance(u, dict):
        return None, None, {}
    used = {k: float(u[k]) for k in FIT_ONLY_COMPONENTS if isinstance(u.get(k), (int, float)) and not isinstance(u.get(k), bool)}
    if 'fitPassSectorMaxHalfWidthDeg' not in used:
        return None, None, {}
    return max(om['sigmaFloorDeg'], om['calibrationSigmaFromEnvelope'] * max(used.values())), 'fit-only-envelope', used


def bearing_from_x(x, yaw0, fov):
    return (yaw0 + math.degrees(math.atan((2 * x - 1) * math.tan(math.radians(fov) / 2)))) % 360.0


def screen_and_bearing(obs, cal, cfg, method, allow_experimental, t_lo, t_hi, sigma_override=None):
    """Return (usable_row | None, excluded_row | None, reserved_flag). Pure function of the row and the calibration pose."""
    oid = obs.get('id')
    om = cfg['observationModel']

    def out(reason, detail=''):
        return None, {'id': oid, 'cameraId': obs.get('cameraId'), 'poseId': obs.get('poseId'), 'reason': reason, 'detail': detail}

    for key in ('id', 'cameraId', 'poseId', 'method', 'base_visible', 'timeUtcAssumed'):
        if key not in obs:
            return out('schema-missing-field', key)
    if obs['method'] != method:
        return out('method-not-selected', 'method=%r, selected=%r' % (obs['method'], method))
    if obs.get('printedTimeStatus') != 'verified-by-agent':
        return out('printed-time-uncertain', 'printedTimeStatus=%r' % obs.get('printedTimeStatus'))
    if obs.get('clockStatus') != 'assumed-PDT':
        return out('clock-not-assumed-pdt', 'clockStatus=%r' % obs.get('clockStatus'))
    if obs['base_visible'] is not True:
        if obs.get('x_base') is not None:
            return out('hidden-base-with-coordinate', 'a hidden base carries no coordinate; row rejected')
        return out('hidden-base', 'base_visible=%r' % obs['base_visible'])
    x = obs.get('x_base')
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not 0.0 <= x <= 1.0:
        return out('x-out-of-range', 'x_base=%r' % (x,))
    try:
        t = parse_epoch(obs['timeUtcAssumed'])
    except ValueError as error:
        return out('invalid-time', str(error))
    if cal is None:
        return out('pose-not-calibrated', 'no calibration document')
    entry = find_pose(cal, obs['cameraId'], obs['poseId'], obs['method'])
    if entry is None or entry.get('yaw0Deg') is None or entry.get('fovDeg') is None:
        return out('pose-not-calibrated', (entry or {}).get('reason') or 'no pose entry with non-null yaw0Deg/fovDeg')
    bound = entry.get('observationsBound', cal.get('observationsBound'))
    if bound is False:
        return out('pose-not-calibrated', 'observationsBound=false: the model is not bound to a real observations file; rejected even if the pose is experimental')
    status = str(entry.get('status', '')).lower()
    if status in NEGATIVE_STATUS:
        return out('pose-not-calibrated', 'status=%s' % status)
    printed = is_printed_basis(entry, cal)
    if status != 'calibrated' and not allow_experimental and not printed:
        return out('pose-experimental-not-allowed', 'status=%s; pass --allow-experimental to use it' % status)
    if not printed and (oid in (entry.get('heldOutIds') or []) or oid in (entry.get('extraCheckIds') or [])):
        return out('calibration-held-out-observation', 'reserved by the calibration split: never assimilated')
    pos = camera_position(cal, obs['cameraId'])
    if pos is None:
        return out('no-camera-position', 'calibration.positions has no coordinates for %s' % obs['cameraId'])
    sig_cal, sig_source, comps = pose_sigma_cal(entry, cal, cfg, sigma_override)
    if sig_cal is None:
        return out('no-fit-only-uncertainty', 'uncertainty lacks fit-only components; the held-out-inclusive envelope is not used')
    sig_pix = om['pixelSigmaX'] * float(entry['fovDeg'])
    sigma = math.hypot(sig_cal, sig_pix)
    if sigma > om['sigmaGateDeg']:
        return out('sigma-gate', 'sigma %.2f deg > gate %.2f deg' % (sigma, om['sigmaGateDeg']))
    if not t_lo < t <= t_hi:
        return out('outside-time-window', 'time %s outside (%s, %s]' % (utc_iso(t), utc_iso(t_lo), utc_iso(t_hi)))
    bearing = bearing_from_x(float(x), float(entry['yaw0Deg']), float(entry['fovDeg']))
    row = {'id': oid, 'cameraId': obs['cameraId'], 'poseId': obs['poseId'], 'method': obs['method'], 't': t, 'timeUtc': utc_iso(t),
           'x_base': float(x), 'bearingDeg': bearing, 'sigmaDeg': sigma, 'sigmaCalDeg': sig_cal, 'sigmaPixDeg': sig_pix,
           'sigmaSource': sig_source, 'sigmaComponents': dict(comps), 'calibrationBasis': entry.get('calibrationBasis') or cal.get('calibrationBasis'),
           'parameterOrigin': entry.get('parameterOrigin'), 'yaw0Deg': float(entry['yaw0Deg']), 'fovDeg': float(entry['fovDeg']), 'cameraLonLat': [pos[0], pos[1]], 'cameraPositionStatus': pos[2],
           'poseStatus': status, 'usedInCalibrationFit': oid in (entry.get('trainingIds') or []),
           'reviewStatus': obs.get('reviewStatus')}
    return row, None


def gate_observations(doc, cal, cfg, method, allow_experimental, t_lo, t_hi, sigma_override=None):
    usable, excluded = [], []
    for obs in (doc or {}).get('observations', []):
        if not isinstance(obs, dict):
            excluded.append({'id': None, 'reason': 'schema-missing-field', 'detail': 'row is not an object'})
            continue
        row, ex = screen_and_bearing(obs, cal, cfg, method, allow_experimental, t_lo, t_hi, sigma_override)
        (usable if row else excluded).append(row or ex)
    usable.sort(key=lambda r: (r['t'], r['id']))
    return usable, excluded
