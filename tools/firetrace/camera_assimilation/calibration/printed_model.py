"""Primary azimuth model: the historical printed pan X is ASSUMED to be the pose azimuth. Nothing is fitted.

yaw0 for each pose is the printed X read from that pose's frames (pose table of planning/video-selection-shared-r1.md,
agent-read, not operator-reviewed). FOV is the explicit unverified 65.1 deg prior at zoom 1 with focal scaling for the
printed zoom. The angular band is a predefined prior (3 deg) with a fixed sensitivity list; FIRMS detections never enter
yaw0, FOV or the band. FIRMS passes are only a compatibility CHECK of the visible-base bearings, reported per pass.

Today's agreement between printed X and the catalog azimuth (< 0.3 deg on 2026-10-17 frames) shows the overlay
convention matched the catalog today. It does not prove the 2025 pose, clock, zoom mapping or FOV.

Output uses the firetrace-camera-calibration-v1 pose entries, so ``observation_bearing`` below (and fit.observation_bearing)
work on it. fit.py's satellite-fitted yaw (calibration.json) is only a contrast column, never an input.

Usage:
    python3 printed_model.py --observations ../vision/observations.json --output printed_model.json [--report printed-model-report.md]
"""
import argparse
import importlib.util
import json
import math
import sys
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_fit():
    spec = importlib.util.spec_from_file_location('firetrace_calibration_fit_for_printed_model', HERE / 'fit.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fit = _load_fit()

CALIBRATION_BASIS = 'printed-x-unverified-historical'
PARAMETER_ORIGIN = 'printed-X-prior-not-fitted'
CONDITION = 'historical-x-unverified'
PRIMARY_METHOD = 'cosmos'
PRIOR_HALF_WIDTH_DEG = 3.0
SENSITIVITY_HALF_WIDTHS_DEG = (0.3, 1.0, 3.0, 5.0, 10.0)
# Printed X per pose, degrees, as read from the pose frames (review values supplied by root). Only source of yaw0.
PRINTED_X_DEG = {'G1': 26.27, 'G2': 25.27, 'G3': -52.81, 'G3b': -39.19, 'G4': -26.13}
PRINTED_X_SOURCE = 'planning/video-selection-shared-r1.md pose table, agent-read (not operator-reviewed); G3 from root review'
DEFAULT_CALIBRATION = HERE / 'calibration.json'
NOT_OBSERVED = 'not-observed-in-pose-window'


def pose_passes(pose_id):
    """Every pre-registered FIRMS pass inside this pose window (all of them are check-only here)."""
    split = fit.SPLIT[pose_id]
    ids = split['fit'] + split['heldOut'] + split['extraCheck']
    return sorted(ids, key=lambda pid: fit.PASSES[pid][1])


def frozen_split():
    return {pose_id: {'fit': [], 'heldOut': pose_passes(pose_id), 'extraCheck': []} for pose_id in fit.POSES}


def yaw0_deg(pose_id):
    return fit.wrap360(PRINTED_X_DEG[pose_id])


def assumptions():
    return [
        'Printed pan X is ASSUMED to be the true-north azimuth of the image centre in 2025. This is an assumption: it is not fitted to FIRMS and not verified for 2025.',
        'Printed X comes from agent-read frames and is not operator-reviewed; poses are never transferred (each pose uses only its own X).',
        'Today (2026-10-17) printed X mod 360 agreed with the public catalog azimuth within 0.28 and 0.16 deg and the printed clock matched PDT; this does not prove the 2025 pose, clock, zoom mapping or FOV.',
        'Horizontal FOV = 65.1 deg at zoom 1 (catalog value, unverified) scaled by focal length for the printed zoom (zoom reading unverified). Not fitted.',
        'Camera positions are candidates (same as fit.py); CAL FIRE incident point is not used. PDT is a hypothesis for frame/pass matching only.',
        'The angular band is a predefined prior (%.1f deg half-width) with sensitivity %s deg; it is not a confidence interval and not a measured historical error. FIRMS never selects it.' % (PRIOR_HALF_WIDTH_DEG, list(SENSITIVITY_HALF_WIDTHS_DEG)),
        'FIRMS passes are a compatibility check only: detections form several groups, the pass centroid is not an observed smoke base, and temporal agreement is not independent physical truth.',
        'Cross-track metres = satellite range x sin(angle): compatibility with a satellite direction, not 2D localization nor absolute geographic error.']


def prior_block():
    return {'priorAngularHalfWidthDeg': PRIOR_HALF_WIDTH_DEG, 'suggestedAngularHalfWidthDeg': PRIOR_HALF_WIDTH_DEG,
            'sensitivityHalfWidthsDeg': list(SENSITIVITY_HALF_WIDTHS_DEG),
            'basis': 'predefined prior; no FIRMS pass, held-out error or fitted value contributes. Not a confidence interval; not a measured historical error.',
            'validated': False, 'holdoutEvaluated': False,
            'todayAgreementNote': 'Agreement of printed X with the catalog azimuth today (< 0.3 deg) does not prove the 2025 pose; the prior is not derived from it.'}


def evaluate_pose(pose_id, observations, passes, camera, method):
    """Check-only evaluation of visible observations against ALL passes of the pose. Never feeds back into yaw0."""
    pose = fit.POSES[pose_id]
    excluded, evaluated_ids, rows, not_matched = [], [], [], []
    for obs in observations:
        if obs.get('poseId') != pose_id or obs.get('method') != method:
            continue
        bad, detail = fit.screen_observation(obs)
        if bad:
            excluded.append({'id': obs.get('id'), 'reason': bad, 'detail': detail})
            continue
        nominal = fit.printed_datetime(obs) + timedelta(hours=7)
        near = [(pid, nominal.timestamp() - fit.PASSES[pid][1]) for pid in pose_passes(pose_id)]
        near = [(pid, gap) for pid, gap in near if abs(gap) <= fit.GAP_LIMIT_S]
        if not near:
            not_matched.append(obs['id'])
            continue
        for pid, gap in near:
            rows.append({'id': obs['id'], 'x': float(obs['x_base']), 'passId': pid, 'gap': gap})
        evaluated_ids.append(obs['id'])
    geometry = {pid: fit.pass_geometry(passes[pid], camera) for pid in {r['passId'] for r in rows}}
    fov = fit.effective_fov_deg(pose['zoom'])
    per_pass = fit.evaluate_rows(rows, geometry, yaw0_deg(pose_id), fov) if rows else []
    diagnostics = None
    if per_pass:
        entries = [e for p in per_pass for e in p['observations']]
        ranges = [p['centroid']['rangeM'] for p in per_pass]
        median_range = sorted(ranges)[len(ranges) // 2]
        diagnostics = {'meaning': 'compatibility counts only; they do not select or change the prior band',
                       'evaluations': len(entries), 'medianRangeM': median_range,
                       'byHalfWidth': [{'halfWidthDeg': w, 'lateralAtMedianRangeM': median_range * math.sin(math.radians(w)),
                                        'withinGroupDistance': sum(1 for e in entries if e['groupDistanceDeg'] <= w),
                                        'withinCentroidResidual': sum(1 for e in entries if abs(e['centroidResidualDeg']) <= w)}
                                       for w in SENSITIVITY_HALF_WIDTHS_DEG]}
    return {'excluded': excluded, 'evaluatedIds': evaluated_ids, 'notNearAnyPassIds': not_matched, 'rows': rows,
            'perPass': per_pass, 'diagnostics': diagnostics}


def validation_status(pose_id, observations_present, evaluation):
    if not fit.SPLIT[pose_id]['heldOut'] and not fit.SPLIT[pose_id]['fit']:
        return NOT_OBSERVED
    if not observations_present:
        return 'pending-observations'
    if not evaluation['perPass']:
        return 'no-visible-observation-within-5min-of-any-pass'
    return 'compatibility-evaluated-no-fit-not-validation'


def comparison_with_fit(pose_id, method, yaw, calibration, observations_sha):
    """Contrast column: printed-X yaw minus the satellite-fitted yaw of fit.py, when one exists. Never feeds the model."""
    if calibration is None:
        return {'status': 'no-calibration-json'}
    if observations_sha is None:
        return {'status': 'pending-observations'}
    if (calibration.get('inputs', {}).get('observations', {}) or {}).get('sha256') != observations_sha:
        return {'status': 'calibration-json-not-bound-to-these-observations'}
    for entry in calibration.get('poses', []):
        if entry.get('poseId') == pose_id and entry.get('method') == method:
            if entry.get('yaw0Deg') is None:
                return {'status': 'no-fitted-yaw', 'fitReason': entry.get('reason')}
            return {'status': 'compared', 'fitYaw0Deg': entry['yaw0Deg'], 'fitFovDeg': entry.get('fovDeg'),
                    'printedMinusFitDeg': fit.wrap180(yaw - entry['yaw0Deg']),
                    'fitHeldOutEvaluated': bool(entry.get('heldOutIds')),
                    'note': 'contrast only; the fitted yaw uses FIRMS fit-pass centroids and shares neither inputs nor outputs with this model'}
    return {'status': 'no-fit-entry-for-pose-method'}


def build_pose_entry(pose_id, method, observations, passes, camera, observations_present, calibration, observations_sha):
    pose = fit.POSES[pose_id]
    evaluation = evaluate_pose(pose_id, observations, passes, camera, method) if observations_present else \
        {'excluded': [], 'evaluatedIds': [], 'notNearAnyPassIds': [], 'rows': [], 'perPass': [], 'diagnostics': None}
    yaw = yaw0_deg(pose_id)
    status = validation_status(pose_id, observations_present, evaluation)
    uncertainty = prior_block()
    uncertainty['holdoutEvaluated'] = bool(evaluation['perPass'])  # a diagnostic exists; the band is untouched
    split = frozen_split()[pose_id]
    flags = ['assumed-historical-azimuth-not-validated']
    if status == NOT_OBSERVED:
        flags.append('no FIRMS pass inside this pose window: parameters are an unvalidated assumption')
    for p in evaluation['perPass']:
        if p['sector']['widthDeg'] > fit.WIDE_SECTOR_DEG:
            flags.append('%s: detection sector %.1f deg wide; a compatibility hit is weak evidence' % (p['passId'], p['sector']['widthDeg']))
        if p['centroid']['crossTrackM']['max'] >= fit.KM_SCALE_M:
            flags.append('%s: centroid cross-track residual reaches %.1f km' % (p['passId'], p['centroid']['crossTrackM']['max'] / 1000))
    errors = {'unit': 'degrees (azimuth) and metres cross-track at FIRMS range; NOT absolute geographic error',
              'note': 'check only: no pass is a fit pass; heldOut lists every pose pass that had a visible observation within 5 min',
              'fitInSample': [], 'heldOut': evaluation['perPass'], 'extraCheck': []}
    return {
        'cameraId': pose['cameraId'], 'poseId': pose_id, 'method': method,
        'role': 'primary' if method == PRIMARY_METHOD else 'contrast-heuristic',
        'status': 'experimental', 'calibrationBasis': CALIBRATION_BASIS, 'parameterOrigin': PARAMETER_ORIGIN, 'condition': CONDITION,
        'observationsBound': bool(observations_present),
        'reason': None,
        'yaw0Deg': yaw, 'printedXDeg': PRINTED_X_DEG[pose_id], 'printedXSource': PRINTED_X_SOURCE,
        'zoom': pose['zoom'], 'fovDeg': fit.effective_fov_deg(pose['zoom']),
        'fovStatus': 'explicit-prior-unverified: %.1f deg at zoom 1, focal scaling (printed Z read as zoom: unverified)' % fit.FOV_PRIOR_ZOOM1_DEG,
        'satelliteValidationStatus': status,
        'frozenSplit': split, 'trainingIds': [], 'trainingPassIds': [],
        'heldOutIds': evaluation['evaluatedIds'], 'heldOutPassIds': [p['passId'] for p in evaluation['perPass']],
        'extraCheckIds': [], 'extraCheckPassIds': [],
        'excluded': evaluation['excluded'], 'visibleNotNearAnyPassIds': evaluation['notNearAnyPassIds'],
        'matched': [dict(r, role='heldOut', relativeDeg=fit.relative_angle_deg(r['x'], fit.effective_fov_deg(pose['zoom']))) for r in evaluation['rows']],
        'errors': errors, 'uncertainty': uncertainty, 'diagnostics': evaluation['diagnostics'],
        'comparisonWithFit': comparison_with_fit(pose_id, method, yaw, calibration, observations_sha),
        'flags': flags,
        'bearingModel': {'formula': 'bearingDeg = (yaw0Deg + degrees(atan((2*x_base - 1) * tan(radians(fovDeg)/2)))) mod 360',
                         'yaw0Deg': yaw, 'fovDeg': fit.effective_fov_deg(pose['zoom']), 'cameraId': pose['cameraId'], 'poseId': pose_id,
                         'method': method, 'angularHalfWidthDeg': PRIOR_HALF_WIDTH_DEG, 'usable': bool(observations_present),
                         'calibrationBasis': CALIBRATION_BASIS, 'parameterOrigin': PARAMETER_ORIGIN,
                         'validOnlyFor': 'visible-base observations of this pose and method; a bearing alone is not a location; assumption, not validated'}}


def load_calibration(path):
    try:
        return json.loads(Path(path).read_text()), fit.sha256_file(path)
    except (OSError, ValueError):
        return None, None


def build(observations_path, satellite_dir=fit.DEFAULT_SATELLITE_DIR, references_path=fit.DEFAULT_REFERENCES,
          clock_check_path=fit.DEFAULT_CLOCK_CHECK, calibration_path=DEFAULT_CALIBRATION, verify_frames=True, passes=None):
    positions, position_source = fit.load_positions(references_path)
    calibration, calibration_sha = load_calibration(calibration_path)
    out = {'schema': fit.SCHEMA, 'status': 'pending-observations', 'statusDetail': None,
           'calibrationBasis': CALIBRATION_BASIS, 'parameterOrigin': PARAMETER_ORIGIN, 'condition': CONDITION, 'primaryMethod': PRIMARY_METHOD,
           'description': 'Primary azimuth model: historical printed pan X assumed to be the pose azimuth. Nothing fitted to FIRMS. Contrast with calibration.json is a separate column.',
           'assumptions': assumptions(),
           'frozenSplit': {'sha256': fit.split_sha256(), 'gapLimitSeconds': fit.GAP_LIMIT_S,
                           'passes': {k: {'source': v[0], 'epoch': v[1]} for k, v in fit.PASSES.items()},
                           'poses': frozen_split(),
                           'rule': 'No pass is a fit pass: every pass of a pose is check-only (heldOut). PDT assumed for matching. Pass sources/epochs are those of fit.py.'},
           'positions': {cam: dict(coordinates=coords, **position_source[cam]) for cam, coords in positions.items()},
           'fovPrior': {'zoom1Deg': fit.FOV_PRIOR_ZOOM1_DEG, 'status': 'unverified catalog value', 'scaling': 'focal length / zoom'},
           'angularPrior': prior_block(),
           'currentFrameCheck': fit.load_clock_check(clock_check_path),
           'contrast': {'file': 'camera_assimilation/calibration/calibration.json', 'sha256': calibration_sha,
                        'meaning': 'satellite-fitted yaw (fit.py) shown as printedMinusFit only; never an input'},
           'inputs': {}, 'poses': [], 'excluded': [],
           'limitations': ['The azimuth is an assumption (historical printed X); no FIRMS fit or held-out validation supports it.',
                           'Compatibility with FIRMS is angular / cross-track at satellite range, not geographic error; sectors can be many degrees wide.',
                           'PDT is not verified; a 2026 clock/azimuth agreement does not carry to 2025.',
                           'G2 and G3 have no FIRMS pass in their windows (not-observed-in-pose-window): their parameters are assumptions without any satellite check.']}
    observations, present, sha = [], False, None
    path = Path(observations_path)
    if not path.exists():
        out['inputs']['observations'] = {'path': str(observations_path), 'present': False}
        out['statusDetail'] = 'pending-observations'
    else:
        try:
            doc = fit.load_observations(path, verify_frames=verify_frames)
            observations, present, sha = doc['observations'], True, fit.sha256_file(path)
            out['inputs']['observations'] = {'path': str(observations_path), 'present': True, 'sha256': sha, 'count': len(observations),
                                             'frameIntegrity': 'verified' if verify_frames else 'not-verified-test-only',
                                             'receipts': doc.get('receipts'), 'limitations': doc.get('limitations')}
            out['status'] = 'experimental'
            out['statusDetail'] = 'printed-X assumed azimuth; visible observations checked against all pose passes without fitting'
        except (OSError, ValueError) as error:
            out['inputs']['observations'] = {'path': str(observations_path), 'present': True, 'error': str(error)}
            out['status'], out['statusDetail'] = 'invalid-observations', 'observations file invalid: %s' % error
    if present:
        passes = passes if passes is not None else fit.load_passes(satellite_dir)
        out['inputs']['satellite'] = {name: fit.sha256_file(Path(satellite_dir) / name) for name in ('overpasses.json', 'hotspots.geojson')}
    for pose_id, pose in fit.POSES.items():
        methods = [PRIMARY_METHOD] + [m for m in fit.METHODS if m != PRIMARY_METHOD and any(
            o.get('poseId') == pose_id and o.get('method') == m for o in observations)]
        for method in methods:
            out['poses'].append(build_pose_entry(pose_id, method, observations, passes, positions[pose['cameraId']], present, calibration, sha))
    for obs in observations:
        if obs.get('poseId') not in fit.POSES:
            out['excluded'].append({'id': obs.get('id'), 'reason': 'unknown-pose', 'detail': 'poseId=%r' % obs.get('poseId')})
        elif obs.get('method') not in fit.METHODS:
            out['excluded'].append({'id': obs.get('id'), 'reason': 'method-unknown', 'detail': 'method=%r' % obs.get('method')})
    return out


def observation_bearing(observation, pose):
    """fit.observation_bearing plus the model labels. Hidden, unknown, uncertain or mismatched observations are refused."""
    if not pose or pose.get('observationsBound') is not True:
        return {'usable': False, 'reason': 'printed model is not bound to checked observations', 'bearingDeg': None, 'angularHalfWidthDeg': None}
    result = fit.observation_bearing(observation, pose)
    if result['usable']:
        result.update(calibrationBasis=pose.get('calibrationBasis', CALIBRATION_BASIS), parameterOrigin=pose.get('parameterOrigin', PARAMETER_ORIGIN),
                      bearingSemantics='assumed historical azimuth from printed X; not fitted, not validated')
    return result


def _f(v, digits=2):
    return fit.fmt(v, digits)


def render_report(doc):
    inp = doc['inputs'].get('observations', {})
    lines = ['# Modelo principal: X impreso histórico como azimut supuesto', '',
             'Estado: **%s** — %s. `calibrationBasis = %s`, `parameterOrigin = %s`. Reproducir:' % (doc['status'], doc['statusDetail'], doc['calibrationBasis'], doc['parameterOrigin']), '',
             '```sh', 'python3 tools/firetrace/camera_assimilation/calibration/printed_model.py \\',
             '  --observations tools/firetrace/camera_assimilation/vision/observations.json \\',
             '  --output tools/firetrace/camera_assimilation/calibration/printed_model.json \\',
             '  --report tools/firetrace/camera_assimilation/calibration/printed-model-report.md', '```', '',
             '`yaw0` es **solo** el X impreso de la pose; ninguna detección FIRMS entra en yaw0, FOV ni banda. FOV = %.1f° a zoom 1 (no verificado) con escalado focal. Banda predefinida ±%.1f° (sensibilidad %s°): **no** es intervalo de confianza ni error histórico medido.' % (
                 fit.FOV_PRIOR_ZOOM1_DEG, PRIOR_HALF_WIDTH_DEG, list(SENSITIVITY_HALF_WIDTHS_DEG)), '',
             'Hoy (2026-10-17) X impreso y azimut de catálogo difieren menos de 0.3°; eso **no** prueba la pose, el reloj ni el FOV de 2025. Todas las pasadas FIRMS son solo comprobación (sin ajuste).', '']
    if not inp.get('present'):
        lines += ['## Pendiente de observaciones', '', 'No existía `%s` al generar este informe: los parámetros (supuestos) existen, pero no hay comprobación satelital ni resultados medidos.' % inp.get('path'), '']
    elif inp.get('error'):
        lines += ['## Observaciones inválidas', '', inp['error'], '']
    else:
        lines += ['Entrada: `%s` (%s observaciones, SHA-256 `%s…`, integridad de fotogramas: %s).' % (inp['path'], inp['count'], inp['sha256'][:12], inp['frameIntegrity']), '']
    lines += ['## Parámetros por pose', '', '| Pose | Método | Rol | X impreso (°) | yaw0 (°) | Zoom | FOV (°) | Estado satélite | Obs. evaluadas | Sesgo vs ajuste FIRMS (°) |', '|---|---|---|---|---|---|---|---|---|---|']
    for p in doc['poses']:
        c = p['comparisonWithFit']
        lines.append('| %s | %s | %s | %s | %s | %s | %s | %s | %d | %s |' % (
            p['poseId'], p['method'], p['role'], _f(p['printedXDeg']), _f(p['yaw0Deg']), p['zoom'], _f(p['fovDeg']), p['satelliteValidationStatus'],
            len(p['heldOutIds']), _f(c.get('printedMinusFitDeg')) if c['status'] == 'compared' else c['status']))
    lines += ['']
    for p in doc['poses']:
        if not p['errors']['heldOut']:
            continue
        lines += ['## %s / %s — comprobación contra todas las pasadas (sin ajuste)' % (p['poseId'], p['method']), '',
                  '| Pasada | Obs | Brecha mín (s) | Resid. centroide medio (°) | \\|resid\\| máx (°) | Cross-track centroide medio (m) | Dist. a grupo medio (°) | Ancho sector (°) | Grupos |', '|---|---|---|---|---|---|---|---|---|']
        for e in p['errors']['heldOut']:
            lines.append('| %s | %d | %s | %s | %s | %s | %s | %s | %d |' % (
                e['passId'], e['nObservations'], _f(e['minAbsGapSeconds'], 0), _f(e['centroid']['meanSignedResidualDeg']), _f(e['centroid']['absResidualDeg']['max']),
                _f(e['centroid']['crossTrackM']['mean'], 0), _f(e['nearestGroup']['distanceDeg']['mean']), _f(e['sector']['widthDeg'], 1), e['sector']['nGroups']))
        d = p['diagnostics']
        lines += ['', 'Sensibilidad (solo diagnóstico, no cambia la banda): ' + '; '.join(
            '±%s° → %s m a %.1f km, %d/%d evaluaciones con dist. a grupo ≤ ese valor' % (b['halfWidthDeg'], _f(b['lateralAtMedianRangeM'], 0), d['medianRangeM'] / 1000.0, b['withinGroupDistance'], d['evaluations']) for b in d['byHalfWidth']), '']
        for f in p['flags'][1:]:
            lines.append('- ' + f)
        lines.append('')
    absent = [p for p in doc['poses'] if p['satelliteValidationStatus'] == NOT_OBSERVED]
    if absent:
        lines += ['## Poses sin pasada en su ventana', '', ', '.join('%s (X %s°)' % (p['poseId'], _f(p['printedXDeg'])) for p in absent) + ': parámetros disponibles como supuesto no validado; errores medidos vacíos.', '']
    cf = doc.get('currentFrameCheck')
    if cf:
        lines += ['## Contexto: fotogramas actuales (solo 2026-10-17)', ''] + ['- %s: X mod 360 = %s° vs azimut de catálogo %s° (residuo %s°)' % (
            r['cameraId'], _f(r['printedXWrappedDeg']), _f(r['catalogAzimuthDeg']), _f(r['azimuthResidualDeg'])) for r in cf['results']] + ['']
    lines += ['## Límites', ''] + ['- ' + a for a in doc['assumptions'] + doc['limitations']] + ['']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--observations', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--satellite-dir', type=Path, default=fit.DEFAULT_SATELLITE_DIR)
    parser.add_argument('--references', type=Path, default=fit.DEFAULT_REFERENCES)
    parser.add_argument('--clock-check', type=Path, default=fit.DEFAULT_CLOCK_CHECK)
    parser.add_argument('--calibration', type=Path, default=DEFAULT_CALIBRATION, help='fit.py calibration.json used only as a contrast column')
    parser.add_argument('--strict', action='store_true', help='exit 2 unless observations were loaded and verified')
    args = parser.parse_args(argv)
    doc = build(args.observations, args.satellite_dir, args.references, args.clock_check, args.calibration)
    args.output.write_text(json.dumps(doc, indent=2, sort_keys=True) + '\n')
    if args.report:
        args.report.write_text(render_report(doc))
    evaluated = sum(1 for p in doc['poses'] if p['heldOutIds'])
    print('status=%s (%s); pose/method entries=%d, with checked observations=%d -> %s' % (doc['status'], doc['statusDetail'], len(doc['poses']), evaluated, args.output))
    return 2 if args.strict and doc['status'] != 'experimental' else 0


if __name__ == '__main__':
    sys.exit(main())
