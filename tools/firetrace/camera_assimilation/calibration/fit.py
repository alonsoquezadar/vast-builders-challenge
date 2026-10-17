"""Experimental one-degree-of-freedom horizontal camera calibration (yaw0 per camera/pose).

Reads camera observations (contract: firetrace-camera-observations-v1) and FIRMS passes, fits one
unknown per pose (the true azimuth of the image centre, ``yaw0Deg``) with the field of view FIXED to an
explicit, unverified prior, and reports held-out compatibility with independent satellite passes.

This is NOT calibration.py (no pixel-to-world pairs, no pose/FOV/position fit) and NOT absolute
geolocation. Errors are angular and "cross-track at the independent satellite range".

Usage:
    python3 fit.py --observations ../vision/observations.json --output calibration.json [--report report.md]

C can import this file by path (no relative imports, no dataclasses) and use
``observation_bearing(observation, pose)`` with a pose entry from calibration.json.
"""
import argparse
import hashlib
import json
import math
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIRETRACE = HERE.parents[1]
DEFAULT_SATELLITE_DIR = FIRETRACE / 'evidence/garnet/satellite'
DEFAULT_REFERENCES = FIRETRACE / 'calibration/garnet-references-sonnet-r2.json'

SCHEMA = 'firetrace-camera-calibration-v1'
OBSERVATIONS_SCHEMA = 'firetrace-camera-observations-v1'
DAY = '2025-08-27'
EARTH_RADIUS_M = 6371008.8
FOV_PRIOR_ZOOM1_DEG = 65.1  # catalog value (unverified); mapping of printed Z to zoom is also unverified
GAP_LIMIT_S = 300  # contract: nearest frame at most 5 min from the pass
POSE_WINDOW_TOLERANCE_MIN = 2  # pose bounds in feasibility.py are approximate
GROUP_GAP_DEG = 2.0  # detections closer than this in azimuth belong to the same group
WIDE_SECTOR_DEG = 10.0
KM_SCALE_M = 1000.0
POSITION_RADII_M = (30, 100, 500)
CLOCK_OFFSETS_MIN = (-10, -5, -2, 0, 2, 5, 10)
FOV_PRIORS_DEG = (55.0, 65.1, 75.0)
HYPOTHESES_HOURS = {'assumed-PDT': 7, 'PST': 8, 'UTC': 0}
PRIMARY_HYPOTHESIS = 'assumed-PDT'
METHODS = ('cosmos', 'simple-detector')

# Frozen BEFORE any observation was read or any parameter fitted (see tests: SPLIT_SHA256 is pinned).
# Roles are by whole pass, never by pixel: a pass is fit, heldOut or an extra check, never two.
# Times are the FIRMS overpass epoch (UTC); PDT labels are the hypothesis, not a verified clock.
PASSES = {
    'MODIS@2025-08-27T18:17:00Z': ('MODIS_SP', 1756318620),         # 11:17 PDT
    'NOAA21@2025-08-27T19:49:00Z': ('VIIRS_NOAA21_NRT', 1756324140),  # 12:49 PDT
    'SNPP@2025-08-27T20:16:00Z': ('VIIRS_SNPP_SP', 1756325760),      # 13:16 PDT
    'NOAA20@2025-08-27T20:38:00Z': ('VIIRS_NOAA20_SP', 1756327080),  # 13:38 PDT
    'NOAA21@2025-08-27T21:29:00Z': ('VIIRS_NOAA21_NRT', 1756330140),  # 14:29 PDT
    'SNPP@2025-08-27T21:57:00Z': ('VIIRS_SNPP_SP', 1756331820),      # 14:57 PDT
    'MODIS@2025-08-27T23:00:00Z': ('MODIS_SP', 1756335600),         # 16:00 PDT
}
_G1_G3B = {'fit': ['NOAA21@2025-08-27T19:49:00Z'],
           'heldOut': ['SNPP@2025-08-27T20:16:00Z', 'NOAA20@2025-08-27T20:38:00Z'],
           'extraCheck': ['MODIS@2025-08-27T18:17:00Z']}
SPLIT = {
    'G1': dict(_G1_G3B),
    'G3b': dict(_G1_G3B),
    'G4': {'fit': ['NOAA21@2025-08-27T21:29:00Z'],
           'heldOut': ['SNPP@2025-08-27T21:57:00Z', 'MODIS@2025-08-27T23:00:00Z'],
           'extraCheck': []},
    'G2': {'fit': [], 'heldOut': [], 'extraCheck': []},
    'G3': {'fit': [], 'heldOut': [], 'extraCheck': []},
}
POSES = {
    'G1': dict(cameraId='delilah', printedStart='10:30', printedEnd='13:44', zoom=1.2),
    'G2': dict(cameraId='delilah', printedStart='16:11', printedEnd='20:16', zoom=1.0),
    'G3': dict(cameraId='buckrock', printedStart='10:32', printedEnd='10:41', zoom=1.0),
    'G3b': dict(cameraId='buckrock', printedStart='11:27', printedEnd='13:59', zoom=1.0),
    'G4': dict(cameraId='buckrock', printedStart='14:08', printedEnd='20:54', zoom=1.4),
}
# Printed pose-overlay X per pose (agent-read from the frames; planning/video-selection-shared-r1.md). It is NEVER an input of
# the fit: it is only compared afterwards, as an external, non-circular check of the satellite-based yaw0.
PRINTED_X_DEG = {'G1': 26.27, 'G2': 25.27, 'G3b': -39.19, 'G4': -26.13}
PRINTED_X_SOURCE = 'planning/video-selection-shared-r1.md pose table (agent-read, not operator-reviewed)'
DEFAULT_CLOCK_CHECK = HERE.parent / 'clock-check/comparison.json'
NO_PASS_REASON = 'no FIRMS pass inside this pose window under the PDT hypothesis; poses are not transferred (printed pan X is not a validated azimuth)'
# Fallback copies of the candidate positions in garnet-references-sonnet-r2.json (lon, lat, elevation m).
FALLBACK_POSITIONS = {'delilah': [-119.1175, 36.80417, 1570], 'buckrock': [-118.86067, 36.73727, 2578]}
MANIFEST_POSITIONS = {'delilah': [-119.12, 36.80, 1570], 'buckrock': [-118.86, 36.74, 2578]}


def split_sha256():
    return hashlib.sha256(json.dumps({'passes': PASSES, 'split': SPLIT, 'gapLimitS': GAP_LIMIT_S},
                                     sort_keys=True).encode()).hexdigest()


# ---------------------------------------------------------------- geometry

def wrap180(angle):
    return (angle + 180.0) % 360.0 - 180.0


def wrap360(angle):
    return angle % 360.0


def bearing_deg(origin, target):
    lon, lat = map(math.radians, origin[:2])
    x, y = map(math.radians, target[:2])
    return math.degrees(math.atan2(math.sin(x - lon) * math.cos(y),
                                   math.cos(lat) * math.sin(y) - math.sin(lat) * math.cos(y) * math.cos(x - lon))) % 360.0


def distance_m(origin, target):
    lon, lat = map(math.radians, origin[:2])
    x, y = map(math.radians, target[:2])
    a = math.sin((y - lat) / 2) ** 2 + math.cos(lat) * math.cos(y) * math.sin((x - lon) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def shift_position(position, east_m, north_m):
    lon, lat = position[:2]
    return [lon + east_m / (111320.0 * math.cos(math.radians(lat))), lat + north_m / 110574.0] + list(position[2:])


def effective_fov_deg(zoom, fov1=FOV_PRIOR_ZOOM1_DEG):
    """Horizontal FOV at ``zoom`` by focal scaling of the zoom-1 prior (both unverified)."""
    return math.degrees(2 * math.atan(math.tan(math.radians(fov1) / 2) / zoom))


def relative_angle_deg(x, fov_deg):
    """Azimuth of normalized image column x relative to the optical axis (pinhole, no roll, tilt ignored)."""
    return math.degrees(math.atan((2 * x - 1) * math.tan(math.radians(fov_deg) / 2)))


def bearing_from_x(x, yaw0_deg, fov_deg):
    """Absolute bearing (deg clockwise from true north) of image column x."""
    return wrap360(yaw0_deg + relative_angle_deg(x, fov_deg))


def tilt_azimuth_effect_deg(rel_deg, tilt_deg):
    """How much a neglected camera tilt could bend the azimuth of a horizon-level ray at column ``rel_deg``."""
    return math.degrees(math.atan(math.tan(math.radians(rel_deg)) / math.cos(math.radians(tilt_deg)))) - rel_deg


def design_condition(xs, fov_deg):
    """Condition number of the (yaw0, fov) design matrix at these columns; None when rank deficient."""
    half = math.radians(fov_deg) / 2
    rows = []
    for x in xs:
        u = (2 * x - 1) * math.tan(half)
        rows.append((1.0, (2 * x - 1) * 0.5 / math.cos(half) ** 2 / (1 + u * u)))
    if len(rows) < 2:
        return None
    n1 = math.sqrt(sum(r[0] ** 2 for r in rows))
    n2 = math.sqrt(sum(r[1] ** 2 for r in rows))
    if n2 < 1e-12:
        return None
    a = sum((r[0] / n1) ** 2 for r in rows)
    b = sum((r[0] / n1) * (r[1] / n2) for r in rows)
    d = sum((r[1] / n2) ** 2 for r in rows)
    tr, det = a + d, a * d - b * b
    disc = math.sqrt(max(0.0, tr * tr / 4 - det))
    low, high = tr / 2 - disc, tr / 2 + disc
    if low <= 1e-12 * high:
        return None
    return round(math.sqrt(high / low), 3)


# ---------------------------------------------------------------- satellite passes

def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_passes(satellite_dir=DEFAULT_SATELLITE_DIR):
    """Load the pre-registered passes: {passId: {source, t, acquiredUtc, points:[(lon,lat,frpMW,pixelM)]}}."""
    satellite_dir = Path(satellite_dir)
    overpasses = json.loads((satellite_dir / 'overpasses.json').read_text())['overpasses']
    by_key = {(row['source'], row['t']): row for row in overpasses}
    wanted = {tuple(key): pid for pid, key in PASSES.items()}
    out = {}
    for key, pid in wanted.items():
        row = by_key.get(key)
        if row is None:
            raise ValueError('pre-registered pass %s missing from overpasses.json' % pid)
        out[pid] = {'id': pid, 'source': key[0], 't': key[1], 'acquiredUtc': row['acquiredUtc'],
                    'declaredDetections': row['detections'], 'points': []}
    for feature in json.loads((satellite_dir / 'hotspots.geojson').read_text())['features']:
        p = feature['properties']
        pid = wanted.get((p['source'], p['t']))
        if pid:
            lon, lat = feature['geometry']['coordinates'][:2]
            out[pid]['points'].append((lon, lat, p.get('frpMW') or 0.0, p.get('pixelM') or 375))
    for entry in out.values():
        if len(entry['points']) != entry['declaredDetections']:
            raise ValueError('pass %s: %d points but overpasses.json declares %d' %
                             (entry['id'], len(entry['points']), entry['declaredDetections']))
    return out


def pass_geometry(a_pass, camera):
    """Centroid, groups and sector of a pass as seen from ``camera`` (lon, lat). Angles are offsets
    (deg, wrapped to +-180) from the centroid bearing so nothing breaks across north."""
    pts = a_pass['points']
    centroid = [sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)]
    theta_c = bearing_deg(camera, centroid)
    rows = []
    for lon, lat, frp, pixel in pts:
        rng = distance_m(camera, (lon, lat))
        half = math.degrees(math.atan((pixel / 2.0) / max(rng, 1.0)))  # the satellite pixel is not a point
        off = wrap180(bearing_deg(camera, (lon, lat)) - theta_c)
        rows.append((off, half, rng, frp))
    rows.sort()
    groups, current = [], [rows[0]]
    for row in rows[1:]:
        if row[0] - current[-1][0] > GROUP_GAP_DEG:
            groups.append(current)
            current = []
        current.append(row)
    groups.append(current)
    out_groups = []
    for g in groups:
        lo = min(r[0] - r[1] for r in g)
        hi = max(r[0] + r[1] for r in g)
        out_groups.append({'offsetLoDeg': lo, 'offsetHiDeg': hi, 'n': len(g), 'frpMW': sum(r[3] for r in g),
                           'meanRangeM': sum(r[2] for r in g) / len(g)})
    return {'passId': a_pass['id'], 'nDetections': len(pts), 'centroidBearingDeg': theta_c,
            'centroidRangeM': distance_m(camera, centroid), 'groups': out_groups,
            'sectorLoDeg': min(g['offsetLoDeg'] for g in out_groups),
            'sectorHiDeg': max(g['offsetHiDeg'] for g in out_groups)}


# ---------------------------------------------------------------- observations

def load_observations(path, verify_frames=True):
    doc = json.loads(Path(path).read_text())
    if not isinstance(doc, dict) or doc.get('schema') != OBSERVATIONS_SCHEMA or not isinstance(doc.get('observations'), list):
        raise ValueError('expected an object with schema %s and an observations array' % OBSERVATIONS_SCHEMA)
    ids = set()
    for row in doc['observations']:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or row['id'] in ids:
            raise ValueError('observation IDs must be unique strings')
        ids.add(row['id'])
        if verify_frames:
            try:
                image = (FIRETRACE / row['imagePath']).resolve()
                if not image.is_relative_to((FIRETRACE / 'camera_assimilation/vision').resolve()):
                    raise ValueError('observation image outside the vision directory')
                if sha256_file(image) != row['imageSha256']:
                    raise ValueError('observation image SHA-256 mismatch')
            except (KeyError, OSError, TypeError) as error:
                raise ValueError('observation has no verifiable source frame') from error
    return doc


def printed_datetime(obs):
    return datetime.fromisoformat(str(obs['printedTime'])).replace(tzinfo=timezone.utc)  # naive print, tagged UTC


def _minute_of_day(dt):
    return dt.hour * 60 + dt.minute + dt.second / 60.0


def screen_observation(obs):
    """Return (None, None) when usable, else (reasonCode, detail). Independent of the clock hypothesis."""
    pose = POSES.get(obs.get('poseId'))
    if pose is None:
        return 'unknown-pose', 'poseId=%r' % obs.get('poseId')
    if obs.get('cameraId') != pose['cameraId']:
        return 'camera-pose-mismatch', 'cameraId=%r but pose %s belongs to %s' % (obs.get('cameraId'), obs['poseId'], pose['cameraId'])
    if obs.get('base_visible') is not True:
        if obs.get('x_base') is not None:
            return 'hidden-base-with-coordinate', 'base_visible is not true but x_base is set; a hidden base has no coordinate'
        return 'base-hidden', 'base_visible=%r' % obs.get('base_visible')
    x = obs.get('x_base')
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return 'x-null-while-visible', 'x_base=%r' % x
    if not (0.0 <= x <= 1.0) or math.isnan(x):
        return 'x-out-of-range', 'x_base=%r' % x
    if obs.get('printedTimeStatus') != 'verified-by-agent':
        return 'printed-time-uncertain', 'printedTimeStatus=%r' % obs.get('printedTimeStatus')
    if obs.get('clockStatus') != 'assumed-PDT':
        return 'clock-status-not-assumed-pdt', 'clockStatus=%r' % obs.get('clockStatus')
    try:
        printed = printed_datetime(obs)
    except (KeyError, ValueError, TypeError):
        return 'printed-time-unparseable', 'printedTime=%r' % obs.get('printedTime')
    if not str(obs['printedTime']).startswith(DAY):
        return 'wrong-date', 'printedTime=%s' % obs['printedTime']
    start_h, start_m = map(int, pose['printedStart'].split(':'))
    end_h, end_m = map(int, pose['printedEnd'].split(':'))
    minute = _minute_of_day(printed)
    if minute < start_h * 60 + start_m - POSE_WINDOW_TOLERANCE_MIN or minute > end_h * 60 + end_m + 1 + POSE_WINDOW_TOLERANCE_MIN:
        return 'outside-pose-window', 'printed %s outside %s %s-%s (+-%d min)' % (
            obs['printedTime'], obs['poseId'], pose['printedStart'], pose['printedEnd'], POSE_WINDOW_TOLERANCE_MIN)
    if obs.get('timeUtcAssumed') is not None:
        try:
            claimed = datetime.fromisoformat(str(obs['timeUtcAssumed']).replace('Z', '+00:00'))
            if claimed.tzinfo is None:
                return 'time-utc-inconsistent', 'timeUtcAssumed requires an explicit timezone'
        except (ValueError, TypeError):
            return 'time-utc-inconsistent', 'timeUtcAssumed is not parseable'
        if abs((claimed - (printed + timedelta(hours=7))).total_seconds()) > 1.0:
            return 'time-utc-inconsistent', 'timeUtcAssumed=%s but printedTime+7h=%s' % (obs['timeUtcAssumed'], (printed + timedelta(hours=7)).isoformat())
    return None, None


def match_pass(obs, pose_id, hypothesis_hours, clock_offset_min):
    """Nearest pre-registered pass of this pose and its role, or (None, detail). Signed gap = frame - pass."""
    split = SPLIT[pose_id]
    nominal = printed_datetime(obs) + timedelta(hours=hypothesis_hours) + timedelta(minutes=clock_offset_min)
    best = None
    for role in ('fit', 'heldOut', 'extraCheck'):
        for pid in split[role]:
            gap = nominal.timestamp() - PASSES[pid][1]
            if best is None or abs(gap) < abs(best[2]):
                best = (role, pid, gap)
    if best is None:
        return None, 'pose has no pre-registered pass'
    if abs(best[2]) > GAP_LIMIT_S:
        return None, 'nearest pre-registered pass %s is %.1f min away (limit %d min)' % (best[1], best[2] / 60.0, GAP_LIMIT_S // 60)
    return best, None


# ---------------------------------------------------------------- fitting and evaluation

def _circular_mean(angles, ref=None):
    ref = angles[0] if ref is None else ref
    return wrap360(ref + sum(wrap180(a - ref) for a in angles) / len(angles))


def _stats(values):
    if not values:
        return None
    return {'mean': sum(values) / len(values), 'median': statistics.median(values), 'max': max(values), 'n': len(values)}


def evaluate_rows(rows, geometry_by_pass, yaw0, fov_deg):
    """Per-pass residuals of predicted bearings. Centroid and nearest-group residuals are kept separate."""
    per_pass = {}
    for row in rows:
        geom = geometry_by_pass[row['passId']]
        rel = relative_angle_deg(row['x'], fov_deg)
        predicted = wrap360(yaw0 + rel)
        offset = wrap180(predicted - geom['centroidBearingDeg'])
        best = None
        for index, g in enumerate(geom['groups']):
            dist = 0.0 if g['offsetLoDeg'] <= offset <= g['offsetHiDeg'] else min(abs(offset - g['offsetLoDeg']), abs(offset - g['offsetHiDeg']))
            if best is None or dist < best[0]:
                best = (dist, index, g)
        signed_group = 0.0
        if best[0] > 0:
            nearest_edge = best[2]['offsetLoDeg'] if abs(offset - best[2]['offsetLoDeg']) < abs(offset - best[2]['offsetHiDeg']) else best[2]['offsetHiDeg']
            signed_group = offset - nearest_edge
        entry = {'id': row['id'], 'gapSeconds': round(row['gap'], 1), 'x': row['x'], 'predictedBearingDeg': predicted,
                 'centroidResidualDeg': offset,
                 'centroidCrossTrackM': geom['centroidRangeM'] * math.sin(math.radians(abs(offset))),
                 'nearestGroupIndex': best[1], 'groupDistanceDeg': best[0], 'groupSignedResidualDeg': signed_group,
                 'groupCrossTrackM': best[2]['meanRangeM'] * math.sin(math.radians(best[0])),
                 'insideAnySector': best[0] == 0.0}
        per_pass.setdefault(row['passId'], []).append(entry)
    out = []
    for pid, entries in per_pass.items():
        geom = geometry_by_pass[pid]
        width = geom['sectorHiDeg'] - geom['sectorLoDeg']
        union = sum(g['offsetHiDeg'] - g['offsetLoDeg'] for g in geom['groups'])
        out.append({
            'passId': pid, 'source': PASSES[pid][0], 'nObservations': len(entries),
            'minAbsGapSeconds': min(abs(e['gapSeconds']) for e in entries),
            'centroid': {'bearingDeg': geom['centroidBearingDeg'], 'rangeM': geom['centroidRangeM'],
                         'meanSignedResidualDeg': sum(e['centroidResidualDeg'] for e in entries) / len(entries),
                         'absResidualDeg': _stats([abs(e['centroidResidualDeg']) for e in entries]),
                         'crossTrackM': _stats([e['centroidCrossTrackM'] for e in entries]),
                         'note': 'centroid of all detections in the pass; it is not an observed smoke base'},
            'nearestGroup': {'distanceDeg': _stats([e['groupDistanceDeg'] for e in entries]),
                             'crossTrackM': _stats([e['groupCrossTrackM'] for e in entries]),
                             'insideGroupFraction': sum(1 for e in entries if e['groupDistanceDeg'] == 0.0) / len(entries)},
            'sector': {'loOffsetDeg': geom['sectorLoDeg'], 'hiOffsetDeg': geom['sectorHiDeg'], 'widthDeg': width,
                       'groupUnionWidthDeg': union, 'fractionOfFov': min(1.0, union / fov_deg),
                       'insideFraction': sum(1 for e in entries if e['insideAnySector']) / len(entries),
                       'nGroups': len(geom['groups']), 'nDetections': geom['nDetections'],
                       'groups': [dict(g, bearingLoDeg=wrap360(geom['centroidBearingDeg'] + g['offsetLoDeg']),
                                       bearingHiDeg=wrap360(geom['centroidBearingDeg'] + g['offsetHiDeg'])) for g in geom['groups']]},
            'observations': entries})
    return sorted(out, key=lambda r: r['passId'])


def fit_pose(pose_id, observations, passes, camera, *, method=None, hypothesis_hours=7, clock_offset_min=0,
             fov1=FOV_PRIOR_ZOOM1_DEG, zoom=None, with_details=True, external_yaw0=None):
    """One-DOF fit of yaw0 for a pose from observations assigned to the frozen fit pass(es).

    ``camera`` is (lon, lat[, elevation]). Observations assigned to heldOut / extraCheck passes never
    influence yaw0; they are only evaluated afterwards.
    """
    pose = POSES[pose_id]
    zoom = pose['zoom'] if zoom is None else zoom
    fov = effective_fov_deg(zoom, fov1)
    result = {'poseId': pose_id, 'cameraId': pose['cameraId'], 'method': method, 'zoom': zoom, 'fovDeg': fov,
              'yaw0Deg': None, 'status': 'no-calibration', 'reason': None, 'excluded': [], 'matched': []}
    split = SPLIT[pose_id]
    if not (split['fit'] or split['heldOut'] or split['extraCheck']):
        result['reason'] = NO_PASS_REASON
        return result
    rows = {'fit': [], 'heldOut': [], 'extraCheck': []}
    # method None selects nothing: cosmos and simple-detector rows are never pooled into one fit.
    candidates = [o for o in observations if o.get('poseId') == pose_id and method is not None and o.get('method') == method]
    for obs in candidates:
        bad, detail = screen_observation(obs)
        if bad:
            result['excluded'].append({'id': obs.get('id'), 'reason': bad, 'detail': detail})
            continue
        hit, why = match_pass(obs, pose_id, hypothesis_hours, clock_offset_min)
        if hit is None:
            result['excluded'].append({'id': obs.get('id'), 'reason': 'no-pass-within-5min', 'detail': why})
            continue
        role, pid, gap = hit
        rows[role].append({'id': obs['id'], 'x': float(obs['x_base']), 'passId': pid, 'gap': gap, 'role': role})
    result['trainingIds'] = [r['id'] for r in rows['fit']]
    result['heldOutIds'] = [r['id'] for r in rows['heldOut']]
    result['extraCheckIds'] = [r['id'] for r in rows['extraCheck']]
    result['trainingPassIds'] = sorted({r['passId'] for r in rows['fit']})
    result['heldOutPassIds'] = sorted({r['passId'] for r in rows['heldOut']})
    result['extraCheckPassIds'] = sorted({r['passId'] for r in rows['extraCheck']})
    result['matched'] = [dict(r, relativeDeg=relative_angle_deg(r['x'], fov)) for k in rows for r in rows[k]]
    geometry = {pid: pass_geometry(passes[pid], camera) for pid in {r['passId'] for k in rows for r in rows[k]}}
    if not rows['fit']:
        result['reason'] = ('no usable observation matched the pre-registered fit pass %s within %d min; '
                            'no parameters are fitted' % (', '.join(split['fit']), GAP_LIMIT_S // 60))
        result['evaluation'] = {'heldOut': evaluate_rows([], geometry, 0, fov), 'note': 'not evaluated without a fit'}
        return result
    per_pass_yaw = {}
    per_obs_yaw = {}
    for r in rows['fit']:
        y = wrap360(geometry[r['passId']]['centroidBearingDeg'] - relative_angle_deg(r['x'], fov))
        per_obs_yaw[r['id']] = y
        per_pass_yaw.setdefault(r['passId'], []).append(y)
    pass_yaws = [_circular_mean(v) for v in per_pass_yaw.values()]
    yaw0 = _circular_mean(pass_yaws)
    # Feasible interval if the visible base is anywhere inside the pass' groups (pixel half widths included).
    lo, hi = -1e9, 1e9
    for r in rows['fit']:
        g = geometry[r['passId']]
        d = wrap180(per_obs_yaw[r['id']] - yaw0)
        lo, hi = max(lo, d + g['sectorLoDeg']), min(hi, d + g['sectorHiDeg'])
    empty = lo > hi
    spread = [wrap180(y - yaw0) for y in per_obs_yaw.values()]
    result.update({
        'status': 'experimental', 'yaw0Deg': yaw0,
        'estimator': 'one-DOF: circular mean over fit observations of (pass centroid bearing - relative angle), equal weight per pass',
        'yaw0FeasibleSector': None if empty else {'loOffsetDeg': lo, 'hiOffsetDeg': hi, 'widthDeg': hi - lo,
                                                   'meaning': 'yaw0 offsets for which every fit frame base lies inside some pass group (pixel half widths included)'},
        'sectorIntersectionEmpty': empty,
        'fitFrameSpreadDeg': {'min': min(spread), 'max': max(spread)},
    })
    if with_details:
        xs = [r['x'] for r in rows['fit']]
        distinct = sorted({round(x / 0.02) for x in xs})
        result['identifiability'] = {
            'fitObservations': len(xs), 'fitPasses': len(per_pass_yaw), 'distinctXColumns': len(distinct),
            'xRange': [min(xs), max(xs)], 'relativeAngleRangeDeg': [min(relative_angle_deg(x, fov) for x in xs), max(relative_angle_deg(x, fov) for x in xs)],
            'designConditionYawFov': design_condition(xs, fov),
            'independentFitDirections': len(per_pass_yaw),
            'fovFitted': False,
            'fovIdentifiable': False,
            'note': 'one fit direction (pass) cannot identify yaw0 and FOV together; FOV stays at the explicit prior; frames of one pass sample one direction, their x spread is not independent angular support'}
    result['evaluation'] = {k: evaluate_rows(rows[k], geometry, yaw0, fov) for k in ('fit', 'heldOut', 'extraCheck')}
    if external_yaw0 is not None:  # evaluation only; external_yaw0 never reaches the estimator above
        result['externalEvaluation'] = {k: evaluate_rows(rows[k], geometry, wrap360(external_yaw0), fov) for k in ('fit', 'heldOut', 'extraCheck')}
    result['_geometry'] = geometry
    return result


def _compact(result):
    """Small fingerprint of a fit used by the sensitivity tables."""
    if result['yaw0Deg'] is None:
        return {'yaw0Deg': None, 'reason': result['reason'], 'nFit': 0, 'nHeldOut': len(result.get('heldOutIds', []))}
    held = {}
    for entry in result['evaluation']['heldOut']:
        held[entry['passId']] = {'centroidAbsMeanDeg': entry['centroid']['absResidualDeg']['mean'],
                                 'groupDistanceMeanDeg': entry['nearestGroup']['distanceDeg']['mean'],
                                 'centroidCrossTrackMeanM': entry['centroid']['crossTrackM']['mean']}
    return {'yaw0Deg': result['yaw0Deg'], 'nFit': len(result['trainingIds']), 'nHeldOut': len(result['heldOutIds']),
            'heldOutByPass': held, 'sectorIntersectionEmpty': result['sectorIntersectionEmpty']}


def sensitivities(pose_id, observations, passes, camera, camera_id, method, primary):
    """Re-run the whole fit under alternative positions, clocks and FOV priors. Nothing is selected from it."""
    def run(**kw):
        cam = kw.pop('camera', camera)
        return _compact(fit_pose(pose_id, observations, passes, cam, method=method, with_details=False, **kw))

    positions = []
    compass = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]
    for radius in POSITION_RADII_M:
        runs = []
        for de, dn in compass:
            norm = math.hypot(de, dn)
            runs.append(run(camera=shift_position(camera, radius * de / norm, radius * dn / norm)))
        yaws = [r['yaw0Deg'] for r in runs if r['yaw0Deg'] is not None]
        held = [v['centroidAbsMeanDeg'] for r in runs if r['yaw0Deg'] is not None for v in r['heldOutByPass'].values()]
        positions.append({'radiusM': radius, 'scenarios': len(runs), 'directions': 8, 'yaw0Values': yaws,
                          'yaw0RangeDeg': [min(yaws), max(yaws)] if yaws else None,
                          'maxYaw0ShiftDeg': max(abs(wrap180(y - primary['yaw0Deg'])) for y in yaws) if yaws and primary['yaw0Deg'] is not None else None,
                          'heldOutCentroidAbsMeanDegRange': [min(held), max(held)] if held else None,
                          'meaning': 'scenario sweep (8 compass shifts), not a claimed sigma bound'})
    manifest = run(camera=MANIFEST_POSITIONS[camera_id])
    clocks = []
    for offset in CLOCK_OFFSETS_MIN:
        clocks.append(dict(offsetMin=offset, **run(clock_offset_min=offset)))
    hypotheses = []
    for label, hours in HYPOTHESES_HOURS.items():
        hypotheses.append(dict(hypothesis=label, offsetHours=hours, **run(hypothesis_hours=hours)))
    fovs = []
    for prior in FOV_PRIORS_DEG:
        fovs.append(dict(fovPriorZoom1Deg=prior, **run(fov1=prior)))
    fovs.append(dict(fovPriorZoom1Deg=FOV_PRIOR_ZOOM1_DEG, zoomIgnored=True, **run(zoom=1.0)))
    return {'position': positions, 'manifestRoundedPosition': dict(position=MANIFEST_POSITIONS[camera_id], **manifest),
            'clockOffsetMin': clocks, 'clockHypothesis': hypotheses, 'fov': fovs}


def pose_flags(entry):
    flags = []
    if entry['yaw0Deg'] is None:
        return ['no-fit']
    if len(entry['trainingPassIds']) < 2:
        flags.append('single-fit-pass: yaw0 equals one pass-centroid direction')
    if entry['sectorIntersectionEmpty']:
        flags.append('fit frames incompatible with a single group-sector yaw0 (ambiguous or inconsistent correspondence)')
    for e in entry['evaluation']['fit'] + entry['evaluation']['heldOut'] + entry['evaluation']['extraCheck']:
        if e['sector']['widthDeg'] > WIDE_SECTOR_DEG:
            flags.append('%s: detection sector %.1f deg wide (> %.0f deg); a compatibility hit is weak evidence' % (e['passId'], e['sector']['widthDeg'], WIDE_SECTOR_DEG))
        if e['sector']['nGroups'] > 1:
            flags.append('%s: %d separated detection groups; the visible base cannot be assigned to one' % (e['passId'], e['sector']['nGroups']))
    for e in entry['evaluation']['heldOut']:
        if e['centroid']['crossTrackM']['max'] >= KM_SCALE_M:
            flags.append('%s: held-out centroid cross-track error reaches %.1f km' % (e['passId'], e['centroid']['crossTrackM']['max'] / 1000))
        if e['sector']['fractionOfFov'] > 0.5:
            flags.append('%s: detection groups cover %.0f%% of the FOV; held-out hit is not discriminating' % (e['passId'], 100 * e['sector']['fractionOfFov']))
    if not entry['heldOutIds']:
        flags.append('no held-out observation matched: parameters unvalidated')
    return flags


def load_clock_check(path):
    """Context only: today's frames show printed X mod 360 ~ catalog azimuth. Says nothing about 2025 poses."""
    try:
        doc = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    return {'file': 'camera_assimilation/clock-check/comparison.json', 'sha256': sha256_file(path), 'scope': doc.get('scope'),
            'historicalClockVerified': doc.get('historicalClockVerified'), 'historicalPoseVerified': doc.get('historicalPoseVerified'),
            'results': [{k: r.get(k) for k in ('cameraId', 'printedXWrappedDeg', 'catalogAzimuthDeg', 'azimuthResidualDeg', 'reviewStatus')} for r in doc.get('results', [])],
            'limitations': doc.get('limitations')}


def external_printed_x_check(entry, base, sens):
    """Compare fitted yaw0 with the printed X of the same pose. Printed X was not used to fit anything."""
    x = PRINTED_X_DEG[entry['poseId']]
    diff = wrap180(entry['yaw0Deg'] - x)
    sector = entry['yaw0FeasibleSector']
    envelope = entry['uncertainty']['suggestedAngularHalfWidthDeg']
    diffs = {'position500m': [wrap180(y - x) for p in sens['position'] if p['radiusM'] == 500 for y in p['yaw0Values']],
             'positionManifestRounded': [wrap180(sens['manifestRoundedPosition']['yaw0Deg'] - x)] if sens['manifestRoundedPosition']['yaw0Deg'] is not None else [],
             'fovPriors': [wrap180(f['yaw0Deg'] - x) for f in sens['fov'] if f['yaw0Deg'] is not None],
             'clockOffsets': [wrap180(c['yaw0Deg'] - x) for c in sens['clockOffsetMin'] if c['yaw0Deg'] is not None]}
    ext = base['externalEvaluation']
    return {
        'source': PRINTED_X_SOURCE, 'printedXDeg': x, 'printedXWrappedDeg': wrap360(x), 'usedInFit': False,
        'hypothesis': 'printed X is the pan azimuth (true-north datum) of the image centre in 2025; tested, not assumed',
        'yaw0MinusPrintedXDeg': diff,
        'printedXInsideFeasibleYawSector': None if sector is None else sector['loOffsetDeg'] <= wrap180(x - entry['yaw0Deg']) <= sector['hiOffsetDeg'],
        'withinSuggestedEnvelope': abs(diff) <= envelope,
        'envelopeHalfWidthDeg': envelope,
        'scenarioDiffRangeDeg': {k: ([min(v), max(v)] if v else None) for k, v in diffs.items()},
        'printedXAsZeroParameterYaw0': {
            'meaning': 'printed X used directly as yaw0 (no fit) and scored on the same frames/passes against FIRMS',
            'fitPassesInSample': ext['fit'], 'heldOut': ext['heldOut'], 'extraCheck': ext['extraCheck']},
        'limits': ['Agreement does not confirm the 2025 clock, the 2025 pose or the FOV prior; disagreement does not say which of X, yaw0 or the PDT hypothesis is wrong.',
                   'yaw0 inherits the centroid/sector ambiguity of a single FIRMS pass: an agreement inside a wide sector is weak evidence.',
                   'Transfer between poses is not tested: each pose is compared with its own printed X only.']}


def build_pose_entry(pose_id, method, observations, passes, camera, camera_id):
    base = fit_pose(pose_id, observations, passes, camera, method=method, external_yaw0=PRINTED_X_DEG.get(pose_id))
    geometry = base.pop('_geometry', {})
    entry = {k: base[k] for k in ('cameraId', 'poseId', 'method', 'status', 'yaw0Deg', 'zoom', 'fovDeg')}
    entry['reason'] = base['reason']
    entry['fovStatus'] = 'explicit-prior-unverified: %.1f deg at zoom 1, focal scaling (printed Z read as zoom: unverified)' % FOV_PRIOR_ZOOM1_DEG
    entry['frozenSplit'] = SPLIT[pose_id]
    for key in ('trainingIds', 'heldOutIds', 'extraCheckIds', 'trainingPassIds', 'heldOutPassIds', 'extraCheckPassIds'):
        entry[key] = base.get(key, [])
    entry['excluded'] = base['excluded']
    entry['matched'] = base['matched']
    if base['yaw0Deg'] is None:
        entry['errors'] = None
        entry['uncertainty'] = None
        entry['flags'] = ['no-fit'] if base['reason'] != NO_PASS_REASON else ['no-pass-in-pose-window']
        return entry
    for key in ('estimator', 'yaw0FeasibleSector', 'sectorIntersectionEmpty', 'fitFrameSpreadDeg', 'identifiability'):
        entry[key] = base[key]
    entry['errors'] = {'unit': 'degrees (azimuth) and metres cross-track at the independent FIRMS range; NOT absolute geographic error',
                       'fitInSample': base['evaluation']['fit'], 'heldOut': base['evaluation']['heldOut'],
                       'extraCheck': base['evaluation']['extraCheck']}
    entry['evaluation'] = base['evaluation']
    entry['flags'] = pose_flags(entry)
    entry.pop('evaluation')
    sens = sensitivities(pose_id, observations, passes, camera, camera_id, method, base)
    entry['sensitivity'] = sens
    held_max = [e['centroid']['absResidualDeg']['max'] for e in entry['errors']['heldOut']]
    sector_half = (entry['yaw0FeasibleSector']['widthDeg'] / 2) if entry['yaw0FeasibleSector'] else None
    fit_sector_half = max(max(abs(e['sector']['loOffsetDeg']), abs(e['sector']['hiOffsetDeg'])) for e in entry['errors']['fitInSample'])
    pos100 = next(p for p in sens['position'] if p['radiusM'] == 100)['maxYaw0ShiftDeg'] or 0.0
    fov_shift = max((abs(wrap180(f['yaw0Deg'] - base['yaw0Deg'])) for f in sens['fov'] if f['yaw0Deg'] is not None), default=0.0)
    envelope = max(fit_sector_half, pos100, fov_shift)
    entry['uncertainty'] = {
        'fitPassSectorMaxHalfWidthDeg': fit_sector_half,
        'feasibleYawHalfWidthDeg': sector_half,
        'heldOutMaxAbsCentroidResidualDeg': max(held_max) if held_max else None,
        'positionShift100mMaxYaw0Deg': pos100,
        'fovPriorMaxYaw0ShiftDeg': fov_shift,
        'suggestedAngularHalfWidthDeg': envelope,
        'suggestedAngularHalfWidthBasis': 'prior/fit envelope: max(fit sector half-width, 100 m position shift, FOV prior shift); excludes held-out errors; NOT a confidence interval',
        'validated': False,
        'holdoutEvaluated': bool(held_max),
        'neglectedTiltBoundDeg': abs(tilt_azimuth_effect_deg(relative_angle_deg(1.0, base['fovDeg']), 7.33)),
        'neglectedTiltNote': 'bound for tilt 7.33 deg (printed Y, not verified as geometric tilt) at the image edge'}
    entry['bearingModel'] = {
        'formula': 'bearingDeg = (yaw0Deg + degrees(atan((2*x_base - 1) * tan(radians(fovDeg)/2)))) mod 360',
        'yaw0Deg': entry['yaw0Deg'], 'fovDeg': entry['fovDeg'], 'cameraId': entry['cameraId'], 'poseId': pose_id, 'method': method,
        'angularHalfWidthDeg': envelope, 'usable': True,
        'validOnlyFor': 'observations of this pose and method with base_visible and verified printed time; a bearing alone is not a location'}
    if pose_id in PRINTED_X_DEG:
        entry['externalCheck'] = external_printed_x_check(entry, base, sens)
    return entry


# ---------------------------------------------------------------- output document

def x_column_for_bearing(bearing, yaw0, fov_deg):
    """Normalized column a direction would occupy for a given yaw0; outside [0, 1] means outside the frame."""
    rel = math.radians(wrap180(bearing - yaw0))
    if abs(rel) >= math.pi / 2:
        return None
    return (math.tan(rel) / math.tan(math.radians(fov_deg) / 2) + 1) / 2


def satellite_targets(passes, positions):
    """Measured FIRMS geometry per pose and pre-registered pass from the candidate tower: what an observed base
    must be compatible with. The x columns are a testable prediction if printed X were the azimuth, not a result."""
    rows = []
    for pose_id, pose in POSES.items():
        for role in ('fit', 'heldOut', 'extraCheck'):
            for pid in SPLIT[pose_id][role]:
                g = pass_geometry(passes[pid], positions[pose['cameraId']])
                fov = effective_fov_deg(pose['zoom'])
                x = PRINTED_X_DEG.get(pose_id)
                predicted = None
                if x is not None:
                    predicted = {'ifYaw0EqualsPrintedXDeg': x, 'centroidX': x_column_for_bearing(g['centroidBearingDeg'], x, fov),
                                 'sectorLoX': x_column_for_bearing(wrap360(g['centroidBearingDeg'] + g['sectorLoDeg']), x, fov),
                                 'sectorHiX': x_column_for_bearing(wrap360(g['centroidBearingDeg'] + g['sectorHiDeg']), x, fov)}
                rows.append({'poseId': pose_id, 'cameraId': pose['cameraId'], 'role': role, 'passId': pid, 'source': PASSES[pid][0],
                             'nDetections': g['nDetections'], 'centroidBearingDeg': g['centroidBearingDeg'], 'centroidRangeM': g['centroidRangeM'],
                             'sectorBearingDeg': [wrap360(g['centroidBearingDeg'] + g['sectorLoDeg']), wrap360(g['centroidBearingDeg'] + g['sectorHiDeg'])],
                             'sectorWidthDeg': g['sectorHiDeg'] - g['sectorLoDeg'], 'nGroups': len(g['groups']),
                             'groupsBearingDeg': [[wrap360(g['centroidBearingDeg'] + q['offsetLoDeg']), wrap360(g['centroidBearingDeg'] + q['offsetHiDeg'])] for q in g['groups']],
                             'fovDeg': fov, 'predictionIfPrintedXIsAzimuth': predicted})
    return rows


def load_positions(references_path):
    positions, source = {}, {}
    try:
        doc = json.loads(Path(references_path).read_text())
        for cam in doc['cameras']:
            cand = cam['refinedPositionCandidate']
            positions[cam['id']] = cand['coordinates']
            source[cam['id']] = {'status': cand['status'], 'shiftFromManifest': cand.get('shiftFromManifest'),
                                 'assumption': cand.get('assumption'), 'file': 'calibration/garnet-references-sonnet-r2.json',
                                 'sha256': sha256_file(references_path)}
    except (OSError, KeyError, ValueError):
        pass
    for cam, coords in FALLBACK_POSITIONS.items():
        if cam not in positions:
            positions[cam] = coords
            source[cam] = {'status': 'candidate (embedded fallback copy; references file not readable)'}
    return positions, source


def assumptions():
    return [
        'Clock: printed time is read as PDT (UTC = print + 7 h). This is a hypothesis; PST and UTC are shown for sensitivity only and the error minimum is never used to choose a clock.',
        'Camera positions are candidates (tower coordinates from public lookout sources), not surveyed; CAL FIRE incident point is not used anywhere.',
        'Horizontal FOV = 65.1 deg at zoom 1 (catalog value, unverified) scaled by focal length for zoom 1.2/1.4 (printed Z read as zoom: unverified). FOV is never fitted.',
        'Pinhole model, zero roll, tilt neglected (bound in uncertainty.neglectedTiltBoundDeg); lens distortion ignored.',
        'yaw0Deg = true azimuth of the image centre. Printed pan X is never an input of the fit; it is compared afterwards as an external check (externalCheck). Poses are never transferred (G1 is not G2).',
        'FIRMS time is the overpass time; the per-pixel scan time inside a granule can differ by minutes.',
        'FIRMS detections of a pass are several pixels in several groups: the pass centroid is not an observed smoke base. Centroid residual and nearest-group distance are reported separately.',
        'Cross-track metres = satellite range x sin(angular error): compatibility with an independent satellite direction, not 2D fire localization and not absolute geographic error.',
        'Temporal holdout (other overpasses of the same fire) is not independent physical truth: the fire front moves, and the detections may not include the visible base.',
        'One-degree-of-freedom experiment with a prior; it is not equivalent to calibration.py with verified pixel-to-world pairs.']


def build(observations_path, satellite_dir=DEFAULT_SATELLITE_DIR, references_path=DEFAULT_REFERENCES, clock_check_path=DEFAULT_CLOCK_CHECK, verify_frames=True):
    positions, position_source = load_positions(references_path)
    out = {'schema': SCHEMA, 'status': 'no-calibration', 'statusDetail': None,
           'description': 'Experimental one-DOF horizontal camera calibration (yaw0 per camera/pose); not a verified calibration.',
           'assumptions': assumptions(),
           'frozenSplit': {'sha256': split_sha256(), 'gapLimitSeconds': GAP_LIMIT_S, 'passes': {k: {'source': v[0], 'epoch': v[1]} for k, v in PASSES.items()},
                           'poses': SPLIT,
                           'rule': 'Split by whole source/time pass, registered in code before any observation was read; roles are never reassigned from results. PDT assumed.'},
           'positions': {cam: {'coordinates': coords, **position_source[cam]} for cam, coords in positions.items()},
           'fovPrior': {'zoom1Deg': FOV_PRIOR_ZOOM1_DEG, 'status': 'unverified catalog value', 'scaling': 'focal length / zoom'},
           'currentFrameCheck': load_clock_check(clock_check_path),
           'inputs': {}, 'poses': [], 'excluded': [], 'limitations': []}
    out['limitations'] = [
        'Not an operational or absolute geolocation product; errors are angular / cross-track at FIRMS range.',
        'PDT is not verified; clock sensitivity does not prove any clock.',
        'G2 and G3 have no FIRMS pass in their windows: null parameters by design.']
    try:
        out['satelliteTargets'] = satellite_targets(load_passes(satellite_dir), positions)
    except (OSError, ValueError, KeyError) as error:
        out['satelliteTargets'] = {'error': str(error)}
    path = Path(observations_path)
    if not path.exists():
        out['statusDetail'] = 'pending-observations'
        out['inputs']['observations'] = {'path': str(observations_path), 'present': False}
        out['limitations'].append('vision/observations.json not available when this file was generated: every pose is uncalibrated.')
        out['poses'] = [empty_entry(pid, 'observations file missing (pending-observations)') for pid in POSES]
        return out
    try:
        doc = load_observations(path, verify_frames=verify_frames)
    except (OSError, ValueError) as error:
        out['statusDetail'] = 'invalid-observations'
        out['inputs']['observations'] = {'path': str(observations_path), 'present': True, 'error': str(error)}
        out['poses'] = [empty_entry(pid, 'observations file invalid: %s' % error) for pid in POSES]
        return out
    observations = doc['observations']
    passes = load_passes(satellite_dir)  # also loaded for satelliteTargets; cheap enough
    out['inputs'] = {'observations': {'path': str(observations_path), 'present': True, 'sha256': sha256_file(path), 'count': len(observations),
                                      'frameIntegrity': 'verified' if verify_frames else 'not-verified-test-only', 'receipts': doc.get('receipts'), 'limitations': doc.get('limitations')},
                     'satellite': {name: sha256_file(Path(satellite_dir) / name) for name in ('overpasses.json', 'hotspots.geojson')}}
    methods_present = sorted({o.get('method') for o in observations if o.get('method')})
    for pose_id, pose in POSES.items():
        use = [m for m in methods_present if any(o.get('poseId') == pose_id and o.get('method') == m for o in observations)] or [None]
        for method in use:
            out['poses'].append(build_pose_entry(pose_id, method, observations, passes, positions[pose['cameraId']], pose['cameraId']))
    for obs in observations:  # rows that can never reach a pose entry
        if obs.get('poseId') not in POSES:
            out['excluded'].append({'id': obs.get('id'), 'reason': 'unknown-pose', 'detail': 'poseId=%r' % obs.get('poseId')})
        elif obs.get('method') not in METHODS:
            out['excluded'].append({'id': obs.get('id'), 'reason': 'method-unknown', 'detail': 'method=%r' % obs.get('method')})
    fitted = [p for p in out['poses'] if p['yaw0Deg'] is not None]
    out['status'] = 'experimental' if fitted else 'no-calibration'
    out['statusDetail'] = ('%d pose/method entries fitted (1-DOF yaw0 with FOV prior)' % len(fitted)) if fitted else 'no pose could be fitted from the supplied observations'
    return out


def empty_entry(pose_id, reason):
    pose = POSES[pose_id]
    if not (SPLIT[pose_id]['fit'] or SPLIT[pose_id]['heldOut']):
        reason = NO_PASS_REASON
    return {'cameraId': pose['cameraId'], 'poseId': pose_id, 'method': None, 'status': 'no-calibration', 'yaw0Deg': None, 'zoom': pose['zoom'],
            'fovDeg': effective_fov_deg(pose['zoom']), 'reason': reason, 'frozenSplit': SPLIT[pose_id], 'trainingIds': [], 'heldOutIds': [],
            'extraCheckIds': [], 'excluded': [], 'matched': [], 'errors': None, 'uncertainty': None, 'flags': ['no-fit']}


# ---------------------------------------------------------------- bearing API for C

def observation_bearing(observation, pose):
    """Bearing of one camera observation under a pose entry of calibration.json.

    Returns a dict. ``usable`` is False (with ``reason``) for hidden bases, null/out-of-range x, pose or
    camera mismatch, method mismatch or an uncalibrated pose. A bearing alone is not a location.
    """
    def refuse(reason):
        return {'usable': False, 'reason': reason, 'bearingDeg': None, 'angularHalfWidthDeg': None}

    if not pose or pose.get('yaw0Deg') is None or pose.get('fovDeg') is None:
        return refuse('pose is not calibrated (null yaw0Deg/fovDeg)')
    if observation.get('poseId') != pose.get('poseId') or observation.get('cameraId') != pose.get('cameraId'):
        return refuse('observation pose/camera does not match the calibration pose (poses are never mixed)')
    if pose.get('method') and observation.get('method') != pose['method']:
        return refuse('observation method %r differs from the pose method %r' % (observation.get('method'), pose['method']))
    invalid, detail = screen_observation(observation)
    if invalid:
        return refuse(invalid + ': ' + detail)
    x = observation.get('x_base')
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not 0.0 <= x <= 1.0:
        return refuse('x_base missing or outside [0, 1]')
    half = (pose.get('uncertainty') or {}).get('suggestedAngularHalfWidthDeg')
    rel = relative_angle_deg(x, pose['fovDeg'])
    return {'usable': True, 'reason': None, 'bearingDeg': wrap360(pose['yaw0Deg'] + rel), 'relativeDeg': rel,
            'angularHalfWidthDeg': half, 'halfWidthBasis': 'empirical envelope, not a confidence interval',
            'validated': False, 'holdoutEvaluated': bool((pose.get('uncertainty') or {}).get('holdoutEvaluated'))}


# ---------------------------------------------------------------- report

def fmt(v, digits=2):
    return 'n/a' if v is None else ('%.*f' % (digits, v))


def _rng(values):
    return 'n/a' if not values else '[%s, %s]°' % (fmt(values[0]), fmt(values[1]))


def render_report(doc):
    lines = ['# Calibración horizontal experimental (1 GDL) por cámara/pose', '',
             'Generado por `fit.py` a partir de `calibration.json` (estado: **%s** — %s). Reproducir:' % (doc['status'], doc['statusDetail']), '',
             '```sh', 'python3 tools/firetrace/camera_assimilation/calibration/fit.py \\',
             '  --observations tools/firetrace/camera_assimilation/vision/observations.json \\',
             '  --output tools/firetrace/camera_assimilation/calibration/calibration.json \\',
             '  --report tools/firetrace/camera_assimilation/calibration/report.md', '```', '',
             'Split congelado antes de leer observaciones (SHA-256 `%s`). Reloj PDT = hipótesis. FOV = %.1f° a zoom 1 (supuesto no verificado), escalado focal para zoom 1.2/1.4. Solo se ajusta `yaw0`.' % (doc['frozenSplit']['sha256'][:16] + '…', FOV_PRIOR_ZOOM1_DEG), '']
    obs_in = doc['inputs'].get('observations', {})
    if not obs_in.get('present'):
        lines += ['## Estado: pending-observations', '', 'No existía `%s` al generar este informe. Ninguna pose está calibrada; no hay resultados medidos. El CLI está listo y las funciones están probadas con datos sintéticos (que no son medición real).' % obs_in.get('path'), '']
    else:
        lines += ['Entrada: `%s` (%s observaciones, SHA-256 `%s…`).' % (obs_in.get('path'), obs_in.get('count', 'n/a'), (obs_in.get('sha256') or '')[:12]), '']
    cf = doc.get('currentFrameCheck')
    if cf:
        lines += ['Contexto (solo fotogramas actuales, 2026-10-17; no verifica reloj ni pose de 2025): ' + '; '.join(
            '%s X mod 360 = %s° vs azimut de catálogo %s° (residuo %s°)' % (r['cameraId'], fmt(r['printedXWrappedDeg']), fmt(r['catalogAzimuthDeg']), fmt(r['azimuthResidualDeg'])) for r in cf['results']), '']
    targets = doc.get('satelliteTargets')
    if isinstance(targets, list) and targets:
        lines += ['## Geometría FIRMS medida desde la torre candidata', '',
                  'Con posición candidata; rangos y sectores incluyen el semiancho del píxel. Las columnas x son una predicción comprobable **si** X impreso fuera el azimut (fuera de [0,1] = fuera de cuadro); no son un resultado.', '',
                  '| Pose | Rol | Pasada | Det. | Azimut centroide (°) | Rango (km) | Sector (°) | Ancho (°) | Grupos | x centroide (si yaw0=X) | x sector |', '|---|---|---|---|---|---|---|---|---|---|---|']
        for t in targets:
            p = t['predictionIfPrintedXIsAzimuth']
            lines.append('| %s | %s | %s | %d | %s | %s | %s–%s | %s | %d | %s | %s–%s |' % (
                t['poseId'], t['role'], t['passId'], t['nDetections'], fmt(t['centroidBearingDeg']), fmt(t['centroidRangeM'] / 1000.0),
                fmt(t['sectorBearingDeg'][0], 1), fmt(t['sectorBearingDeg'][1], 1), fmt(t['sectorWidthDeg'], 1), t['nGroups'],
                fmt(p['centroidX']) if p else 'n/a', fmt(p['sectorLoX']) if p else 'n/a', fmt(p['sectorHiX']) if p else 'n/a'))
        lines += ['']
    for pose in doc['poses']:
        title = '%s / %s%s' % (pose['cameraId'], pose['poseId'], (' / ' + pose['method']) if pose.get('method') else '')
        lines += ['## %s' % title, '']
        if pose['yaw0Deg'] is None:
            lines += ['- Sin parámetros: %s' % pose['reason'], '- Excluidas: %d' % len(pose['excluded']), '']
            for e in pose['excluded']:
                lines.append('  - `%s`: %s — %s' % (e['id'], e['reason'], e['detail']))
            lines.append('')
            continue
        lines += ['- yaw0 = **%s°** (azimut verdadero del centro de imagen), FOV = %s° (zoom %s, prior), estimador 1 GDL por centroide.' % (fmt(pose['yaw0Deg']), fmt(pose['fovDeg']), pose['zoom']),
                  '- Ajuste: %s; reserva: %s; comprobación extra: %s.' % (pose['trainingIds'] or '—', pose['heldOutIds'] or '—', pose['extraCheckIds'] or '—'),
                  '- Soporte angular: %d observaciones, %d columnas x distintas, ángulo relativo %s°, condición (yaw,FOV) = %s → FOV no identificable, no se ajusta.' % (
                      pose['identifiability']['fitObservations'], pose['identifiability']['distinctXColumns'],
                      [round(v, 1) for v in pose['identifiability']['relativeAngleRangeDeg']], pose['identifiability']['designConditionYawFov']),
                  '- Sector factible de yaw0 (base dentro de algún grupo): %s' % (
                      'vacío (inconsistente)' if pose['sectorIntersectionEmpty'] else '[%s°, %s°] ancho %s°' % (
                          fmt(pose['yaw0FeasibleSector']['loOffsetDeg']), fmt(pose['yaw0FeasibleSector']['hiOffsetDeg']), fmt(pose['yaw0FeasibleSector']['widthDeg']))),
                  '', '| Rol | Pasada | Obs | Brecha mín (s) | Resid. centroide medio (°) | |resid| máx (°) | Cross-track centroide medio (m) | Dist. a grupo medio (°) | Cross-track grupo medio (m) | Ancho sector (°) | Grupos |',
                  '|---|---|---|---|---|---|---|---|---|---|---|']
        for role, key in (('ajuste (in-sample)', 'fitInSample'), ('reserva', 'heldOut'), ('extra', 'extraCheck')):
            for e in pose['errors'][key]:
                lines.append('| %s | %s | %d | %s | %s | %s | %s | %s | %s | %s | %d |' % (
                    role, e['passId'], e['nObservations'], fmt(e['minAbsGapSeconds'], 0), fmt(e['centroid']['meanSignedResidualDeg']),
                    fmt(e['centroid']['absResidualDeg']['max']), fmt(e['centroid']['crossTrackM']['mean'], 0),
                    fmt(e['nearestGroup']['distanceDeg']['mean']), fmt(e['nearestGroup']['crossTrackM']['mean'], 0),
                    fmt(e['sector']['widthDeg'], 1), e['sector']['nGroups']))
        lines += ['']
        u = pose['uncertainty']
        lines += ['- Envolvente angular sugerida: ±%s° (**no** es intervalo de confianza)%s. Desglose: sector de ajuste ±%s°, posición 100 m ±%s°, prior FOV ±%s°, residuo reservado máx %s°.' % (
            fmt(u['suggestedAngularHalfWidthDeg']), '' if u['validated'] else ' — SIN validación reservada', fmt(u['fitPassSectorMaxHalfWidthDeg']),
            fmt(u['positionShift100mMaxYaw0Deg']), fmt(u['fovPriorMaxYaw0ShiftDeg']), fmt(u['heldOutMaxAbsCentroidResidualDeg']))]
        s = pose['sensitivity']
        lines += ['- Posición candidata (barrido de 8 desplazamientos): ' + '; '.join('%d m → yaw0 ±%s°' % (p['radiusM'], fmt(p['maxYaw0ShiftDeg'])) for p in s['position']) + '. Posición redondeada del catálogo: yaw0 %s°.' % fmt(s['manifestRoundedPosition']['yaw0Deg']),
                  '- Reloj ±min (yaw0, nº ajuste/reserva): ' + '; '.join('%+d → %s (%d/%d)' % (c['offsetMin'], fmt(c['yaw0Deg']), c['nFit'], c['nHeldOut']) for c in s['clockOffsetMin']),
                  '- Hipótesis de reloj (sin elegir por error mínimo): ' + '; '.join('%s → yaw0 %s (%d/%d)' % (c['hypothesis'], fmt(c['yaw0Deg']), c['nFit'], c['nHeldOut']) for c in s['clockHypothesis']),
                  '- Prior FOV: ' + '; '.join('%s%s° → yaw0 %s' % (f['fovPriorZoom1Deg'], ' (zoom ignorado)' if f.get('zoomIgnored') else '', fmt(f['yaw0Deg'])) for f in s['fov']), '']
        ext = pose.get('externalCheck')
        if ext:
            rng = ext['scenarioDiffRangeDeg']
            lines += ['- **Comprobación externa con X impreso** (%s°, no usado en el ajuste): yaw0 − X = **%s°**; X dentro del sector factible de yaw0: %s; dentro de la envolvente ±%s°: %s. Rango de la diferencia en escenarios: posición 500 m %s, prior FOV %s, reloj ±10 min %s.' % (
                fmt(ext['printedXDeg']), fmt(ext['yaw0MinusPrintedXDeg']), ext['printedXInsideFeasibleYawSector'], fmt(ext['envelopeHalfWidthDeg']), ext['withinSuggestedEnvelope'],
                _rng(rng['position500m']), _rng(rng['fovPriors']), _rng(rng['clockOffsets']))]
            for key, label in (('heldOut', 'reserva'), ('fitPassesInSample', 'pasada de ajuste'), ('extraCheck', 'extra')):
                for e in ext['printedXAsZeroParameterYaw0'][key]:
                    lines.append('  - X impreso como yaw0 sin ajuste, %s %s: resid. centroide %s° (|max| %s°, %s m cross-track), dist. a grupo %s°.' % (
                        label, e['passId'], fmt(e['centroid']['meanSignedResidualDeg']), fmt(e['centroid']['absResidualDeg']['max']),
                        fmt(e['centroid']['crossTrackM']['mean'], 0), fmt(e['nearestGroup']['distanceDeg']['mean'])))
            lines += ['']
        if pose['flags']:
            lines += ['**Avisos:**'] + ['- ' + f for f in pose['flags']] + ['']
        if pose['excluded']:
            lines += ['Excluidas (%d): ' % len(pose['excluded']) + '; '.join('%s (%s)' % (e['id'], e['reason']) for e in pose['excluded']), '']
    lines += ['## Límites', ''] + ['- ' + a for a in doc['assumptions'] + doc['limitations']] + ['']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--observations', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--report', type=Path, help='optional Markdown report generated from the same data')
    parser.add_argument('--satellite-dir', type=Path, default=DEFAULT_SATELLITE_DIR)
    parser.add_argument('--references', type=Path, default=DEFAULT_REFERENCES)
    parser.add_argument('--clock-check', type=Path, default=DEFAULT_CLOCK_CHECK, help='optional root clock-check/comparison.json (context only)')
    parser.add_argument('--strict', action='store_true', help='exit 2 if observations are missing/invalid or nothing was fitted')
    args = parser.parse_args(argv)
    doc = build(args.observations, args.satellite_dir, args.references, args.clock_check)
    args.output.write_text(json.dumps(doc, indent=2, sort_keys=True) + '\n')
    if args.report:
        args.report.write_text(render_report(doc))
    fitted = sum(1 for p in doc['poses'] if p['yaw0Deg'] is not None)
    print('status=%s (%s); fitted pose entries=%d/%d -> %s' % (doc['status'], doc['statusDetail'], fitted, len(doc['poses']), args.output))
    return 2 if args.strict and fitted == 0 else 0


if __name__ == '__main__':
    sys.exit(main())
