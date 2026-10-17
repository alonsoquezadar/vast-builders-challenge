"""Cheap tests for printed_model.py. Synthetic data checks the code; it is NOT a measurement.

Run: python3 -B -m unittest discover -s tools/firetrace/camera_assimilation/calibration -p 'test_printed_model.py'
"""
import copy
import importlib.util
import json
import math
import random
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location('printed_model_under_test', HERE / 'printed_model.py')
pm = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = pm
_spec.loader.exec_module(pm)
fit = pm.fit

CAMERAS = {'delilah': [-119.1175, 36.80417, 1570], 'buckrock': [-118.86067, 36.73727, 2578]}
G1_FIT_ROLE = 'NOAA21@2025-08-27T19:49:00Z'  # a "fit" pass in fit.py; here it is check-only
G1_HELD = 'SNPP@2025-08-27T20:16:00Z'
G4_PASS = 'NOAA21@2025-08-27T21:29:00Z'


def destination(origin, bearing, distance_m):
    lon, lat, brg, d = math.radians(origin[0]), math.radians(origin[1]), math.radians(bearing), distance_m / fit.EARTH_RADIUS_M
    lat2 = math.asin(math.sin(lat) * math.cos(d) + math.cos(lat) * math.sin(d) * math.cos(brg))
    lon2 = lon + math.atan2(math.sin(brg) * math.sin(d) * math.cos(lat), math.cos(d) - math.sin(lat) * math.sin(lat2))
    return [math.degrees(lon2), math.degrees(lat2)]


def synthetic_passes(centres):
    out = {}
    for pid, (camera, bearing) in centres.items():
        source, epoch = fit.PASSES[pid]
        pts = [tuple(destination(camera, bearing + d, 14000.0)) + (10.0, 375) for d in (-0.3, 0.0, 0.3)]
        out[pid] = {'id': pid, 'source': source, 't': epoch, 'acquiredUtc': '', 'declaredDetections': 3, 'points': pts}
    return out


def all_passes():
    delilah, buck = CAMERAS['delilah'], CAMERAS['buckrock']
    centres = {pid: (delilah, 20.0) for pid in fit.SPLIT['G1']['fit'] + fit.SPLIT['G1']['heldOut'] + fit.SPLIT['G1']['extraCheck']}
    centres.update({pid: (buck, 320.0) for pid in fit.SPLIT['G4']['fit'] + fit.SPLIT['G4']['heldOut']})
    return synthetic_passes(centres)


def make_obs(oid, pose_id, pass_id, x, minutes=0.0, method='cosmos', **extra):
    printed = datetime.fromtimestamp(fit.PASSES[pass_id][1], timezone.utc) - timedelta(hours=7) + timedelta(minutes=minutes)
    row = {'id': oid, 'cameraId': fit.POSES[pose_id]['cameraId'], 'poseId': pose_id, 'method': method, 'base_visible': True, 'x_base': x, 'y_base': 0.5,
           'printedTime': printed.replace(tzinfo=None).isoformat(), 'printedTimeStatus': 'verified-by-agent',
           'timeUtcAssumed': (printed + timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%SZ'), 'clockStatus': 'assumed-PDT',
           'smoke': True, 'reviewStatus': 'pending-operator-review'}
    row.update(extra)
    return row


def build_with(rows, passes=None, calibration=None):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'o.json'
        path.write_text(json.dumps({'schema': fit.OBSERVATIONS_SCHEMA, 'observations': rows}))
        cal = Path(tmp) / 'cal.json'
        if calibration is not None:
            cal.write_text(json.dumps(calibration))
        return pm.build(path, calibration_path=cal, verify_frames=False, passes=passes or all_passes()), path


def entry(doc, pose_id, method='cosmos'):
    return next(p for p in doc['poses'] if p['poseId'] == pose_id and p['method'] == method)


class Parameters(unittest.TestCase):
    def test_yaw0_is_only_the_historical_printed_x_per_pose(self):
        doc, _ = build_with([])
        self.assertEqual({p['poseId']: p['printedXDeg'] for p in doc['poses']}, {'G1': 26.27, 'G2': 25.27, 'G3': -52.81, 'G3b': -39.19, 'G4': -26.13})
        for p in doc['poses']:
            self.assertAlmostEqual(p['yaw0Deg'], (p['printedXDeg'] % 360.0))
            self.assertAlmostEqual(p['fovDeg'], fit.effective_fov_deg(fit.POSES[p['poseId']]['zoom']))
        self.assertAlmostEqual(entry(doc, 'G3b')['yaw0Deg'], 320.81)
        self.assertAlmostEqual(entry(doc, 'G1')['fovDeg'], 56.018, places=2)
        self.assertAlmostEqual(entry(doc, 'G2')['fovDeg'], 65.1)

    def test_labels_prior_and_no_training(self):
        doc, _ = build_with([])
        self.assertEqual(doc['calibrationBasis'], 'printed-x-unverified-historical')
        for p in doc['poses']:
            self.assertEqual(p['status'], 'experimental')
            self.assertEqual(p['parameterOrigin'], 'printed-X-prior-not-fitted')
            self.assertEqual(p['condition'], 'historical-x-unverified')
            self.assertEqual((p['trainingIds'], p['trainingPassIds'], p['extraCheckIds']), ([], [], []))
            self.assertEqual(p['frozenSplit']['fit'], [])
            self.assertEqual(p['frozenSplit']['heldOut'], pm.pose_passes(p['poseId']))
            u = p['uncertainty']
            self.assertEqual((u['priorAngularHalfWidthDeg'], u['suggestedAngularHalfWidthDeg']), (3.0, 3.0))
            self.assertEqual(u['sensitivityHalfWidthsDeg'], [0.3, 1.0, 3.0, 5.0, 10.0])
            self.assertFalse(u['validated'])
            self.assertIn('Not a confidence interval', u['basis'])
            self.assertIn('Not a measured historical error', u['basis'].replace('not a measured', 'Not a measured'))
        self.assertTrue(any('does not prove the 2025 pose' in a for a in doc['assumptions']))

    def test_frozen_split_matches_fit_passes_and_has_no_fit_pass(self):
        doc, _ = build_with([])
        self.assertEqual(doc['frozenSplit']['passes'], {k: {'source': v[0], 'epoch': v[1]} for k, v in fit.PASSES.items()})
        for pose_id, roles in doc['frozenSplit']['poses'].items():
            self.assertEqual(roles['fit'] + roles['extraCheck'], [])
            union = fit.SPLIT[pose_id]['fit'] + fit.SPLIT[pose_id]['heldOut'] + fit.SPLIT[pose_id]['extraCheck']
            self.assertEqual(sorted(roles['heldOut']), sorted(union))

    def test_never_calls_the_fit(self):
        source = (HERE / 'printed_model.py').read_text()
        self.assertNotIn('fit_pose(', source.replace('fit_pose` ', ''))
        original = fit.fit_pose
        fit.fit_pose = lambda *a, **k: (_ for _ in ()).throw(AssertionError('fit_pose must not be called'))
        try:
            doc, _ = build_with([make_obs('a', 'G1', G1_FIT_ROLE, 0.4)])
        finally:
            fit.fit_pose = original
        self.assertEqual(entry(doc, 'G1')['heldOutIds'], ['a'])


class FirmsIndependence(unittest.TestCase):
    def test_changing_every_firms_coordinate_changes_neither_yaw_fov_nor_band(self):
        rows = [make_obs('a', 'G1', G1_FIT_ROLE, 0.4), make_obs('b', 'G4', G4_PASS, 0.3)]
        base_passes = all_passes()
        moved = copy.deepcopy(base_passes)
        rng = random.Random(7)
        for p in moved.values():
            p['points'] = [(lon + rng.uniform(-0.3, 0.3), lat + rng.uniform(-0.3, 0.3), frp, px) for lon, lat, frp, px in p['points']]
        a, _ = build_with(rows, passes=base_passes)
        b, _ = build_with(rows, passes=moved)
        for pa, pb in zip(a['poses'], b['poses']):
            for key in ('yaw0Deg', 'fovDeg', 'uncertainty', 'printedXDeg', 'frozenSplit', 'bearingModel', 'trainingIds'):
                self.assertEqual(pa[key], pb[key], key)
        self.assertNotEqual(entry(a, 'G1')['errors'], entry(b, 'G1')['errors'])  # only the diagnostic moved

    def test_observation_x_does_not_change_the_model_only_the_check(self):
        a, _ = build_with([make_obs('a', 'G1', G1_FIT_ROLE, 0.1)])
        b, _ = build_with([make_obs('a', 'G1', G1_FIT_ROLE, 0.9)])
        self.assertEqual(entry(a, 'G1')['yaw0Deg'], entry(b, 'G1')['yaw0Deg'])
        self.assertEqual(entry(a, 'G1')['uncertainty']['suggestedAngularHalfWidthDeg'], entry(b, 'G1')['uncertainty']['suggestedAngularHalfWidthDeg'])
        self.assertNotEqual(entry(a, 'G1')['errors'], entry(b, 'G1')['errors'])

    def test_band_ignores_a_terrible_check(self):
        far = [make_obs('a', 'G1', G1_HELD, 0.99)]
        doc, _ = build_with(far)
        p = entry(doc, 'G1')
        self.assertEqual(p['uncertainty']['suggestedAngularHalfWidthDeg'], 3.0)
        self.assertTrue(p['uncertainty']['holdoutEvaluated'])
        self.assertFalse(p['uncertainty']['validated'])
        self.assertGreater(p['errors']['heldOut'][0]['centroid']['absResidualDeg']['max'], 3.0)  # error stays visible, band untouched


class Evaluation(unittest.TestCase):
    def test_every_pass_is_check_only_including_fit_role_passes(self):
        doc, _ = build_with([make_obs('a', 'G1', G1_FIT_ROLE, 0.4), make_obs('b', 'G1', G1_HELD, 0.45)])
        p = entry(doc, 'G1')
        self.assertEqual(sorted(p['heldOutIds']), ['a', 'b'])
        self.assertEqual(sorted(p['heldOutPassIds']), sorted([G1_FIT_ROLE, G1_HELD]))
        self.assertEqual(p['trainingPassIds'], [])
        self.assertEqual(p['satelliteValidationStatus'], 'compatibility-evaluated-no-fit-not-validation')
        self.assertEqual(p['errors']['fitInSample'], [])
        self.assertEqual({r['role'] for r in p['matched']}, {'heldOut'})

    def test_five_minute_limit(self):
        doc, _ = build_with([make_obs('near', 'G1', G1_HELD, 0.4, minutes=4.9), make_obs('far', 'G1', G1_HELD, 0.4, minutes=5.5)])
        p = entry(doc, 'G1')
        self.assertEqual(p['heldOutIds'], ['near'])
        self.assertEqual(p['visibleNotNearAnyPassIds'], ['far'])

    def test_residual_matches_hand_computation(self):
        # Delilah G1: predicted bearing = 26.27 + rel(x); pass centroid direction is 20 deg (synthetic).
        x = 0.4
        doc, _ = build_with([make_obs('a', 'G1', G1_HELD, x)])
        e = entry(doc, 'G1')['errors']['heldOut'][0]
        expected = 26.27 + fit.relative_angle_deg(x, fit.effective_fov_deg(1.2)) - 20.0
        self.assertAlmostEqual(e['centroid']['meanSignedResidualDeg'], expected, delta=0.05)

    def test_g2_and_g3_available_but_not_validated(self):
        rows = [make_obs('g2', 'G2', G1_HELD, 0.5)]
        doc, _ = build_with(rows)
        for pose_id, x in (('G2', 25.27), ('G3', -52.81)):
            p = entry(doc, pose_id)
            self.assertEqual(p['satelliteValidationStatus'], 'not-observed-in-pose-window')
            self.assertAlmostEqual(p['yaw0Deg'], x % 360)
            self.assertEqual((p['errors']['fitInSample'], p['errors']['heldOut'], p['errors']['extraCheck']), ([], [], []))
            self.assertEqual(p['heldOutIds'], [])
            self.assertEqual(p['frozenSplit'], {'fit': [], 'heldOut': [], 'extraCheck': []})
            self.assertFalse(p['uncertainty']['validated'])

    def test_unknown_hidden_or_bad_integrity_rows_are_inactive(self):
        bad = [make_obs('hid', 'G1', G1_HELD, None, base_visible=False), make_obs('inv', 'G1', G1_HELD, 0.9, base_visible=False),
               make_obs('unc', 'G1', G1_HELD, 0.4, printedTimeStatus='uncertain'), make_obs('clk', 'G1', G1_HELD, 0.4, clockStatus='unknown'),
               make_obs('utc', 'G1', G1_HELD, 0.4, timeUtcAssumed='2025-08-27T10:00:00Z'), make_obs('cam', 'G1', G1_HELD, 0.4, cameraId='buckrock'),
               dict(make_obs('unk', 'G1', G1_HELD, 0.4), poseId='G9'), make_obs('met', 'G1', G1_HELD, 0.4, method='mystery'),
               make_obs('late', 'G1', G1_HELD, 0.4, printedTime='2025-08-27T17:30:00', timeUtcAssumed='2025-08-28T00:30:00Z')]
        good = make_obs('ok', 'G1', G1_HELD, 0.4)
        doc, _ = build_with(bad + [good])
        p = entry(doc, 'G1')
        self.assertEqual(p['heldOutIds'], ['ok'])
        reasons = {e['id']: e['reason'] for e in p['excluded']}
        self.assertEqual(reasons, {'hid': 'base-hidden', 'inv': 'hidden-base-with-coordinate', 'unc': 'printed-time-uncertain', 'clk': 'clock-status-not-assumed-pdt',
                                   'utc': 'time-utc-inconsistent', 'cam': 'camera-pose-mismatch', 'late': 'outside-pose-window'})
        self.assertEqual({e['id'] for e in doc['excluded']}, {'unk', 'met'})
        for row in bad:
            self.assertFalse(pm.observation_bearing(row, p)['usable'], row['id'])
        self.assertTrue(pm.observation_bearing(good, p)['usable'])

    def test_methods_stay_separate_cosmos_primary(self):
        rows = [make_obs('c', 'G1', G1_HELD, 0.4), make_obs('s', 'G1', G1_HELD, 0.9, method='simple-detector')]
        doc, _ = build_with(rows)
        self.assertEqual(doc['primaryMethod'], 'cosmos')
        cosmos, simple = entry(doc, 'G1'), entry(doc, 'G1', 'simple-detector')
        self.assertEqual((cosmos['role'], simple['role']), ('primary', 'contrast-heuristic'))
        self.assertEqual((cosmos['heldOutIds'], simple['heldOutIds']), (['c'], ['s']))
        self.assertEqual(cosmos['yaw0Deg'], simple['yaw0Deg'])
        self.assertFalse(pm.observation_bearing(rows[1], cosmos)['usable'])
        self.assertEqual(len([p for p in doc['poses'] if p['poseId'] == 'G2']), 1)


class BearingApi(unittest.TestCase):
    def test_bearing_formula_labels_and_prior(self):
        doc, _ = build_with([])
        p = entry(doc, 'G4')
        obs = make_obs('o', 'G4', G4_PASS, 0.25)
        out = pm.observation_bearing(obs, p)
        expected = (p['yaw0Deg'] + math.degrees(math.atan(-0.5 * math.tan(math.radians(p['fovDeg']) / 2)))) % 360
        self.assertAlmostEqual(out['bearingDeg'], expected)
        self.assertEqual(out['angularHalfWidthDeg'], 3.0)
        self.assertEqual(out['calibrationBasis'], 'printed-x-unverified-historical')
        self.assertFalse(out['validated'])
        self.assertFalse(pm.observation_bearing(obs, dict(p, poseId='G3b'))['usable'])  # poses are never mixed

    def test_unbound_prior_never_supplies_a_usable_bearing(self):
        doc, _ = build_with([])
        p = dict(entry(doc, 'G4'), observationsBound=False)
        obs = make_obs('o', 'G4', G4_PASS, 0.25)
        self.assertFalse(pm.observation_bearing(obs, p)['usable'])

    def test_wraps_across_north(self):
        p = entry(build_with([])[0], 'G3b')
        out = pm.observation_bearing(make_obs('o', 'G3b', 'NOAA21@2025-08-27T19:49:00Z', 1.0), p)
        self.assertTrue(0 <= out['bearingDeg'] < 360)


class ContrastWithFit(unittest.TestCase):
    def calibration(self, sha, yaw=22.0):
        return {'inputs': {'observations': {'sha256': sha}},
                'poses': [{'poseId': 'G1', 'method': 'cosmos', 'yaw0Deg': yaw, 'fovDeg': 56.0, 'heldOutIds': ['h']},
                          {'poseId': 'G4', 'method': 'cosmos', 'yaw0Deg': None, 'reason': 'no usable observation'}]}

    def test_table_when_fit_exists_and_not_an_input(self):
        rows = [make_obs('a', 'G1', G1_HELD, 0.4)]
        with tempfile.TemporaryDirectory() as tmp:
            path, cal = Path(tmp) / 'o.json', Path(tmp) / 'c.json'
            path.write_text(json.dumps({'schema': fit.OBSERVATIONS_SCHEMA, 'observations': rows}))
            sha = fit.sha256_file(path)
            cal.write_text(json.dumps(self.calibration(sha)))
            with_cal = pm.build(path, calibration_path=cal, verify_frames=False, passes=all_passes())
            cal.write_text(json.dumps(self.calibration(sha, yaw=200.0)))
            other = pm.build(path, calibration_path=cal, verify_frames=False, passes=all_passes())
            none = pm.build(path, calibration_path=Path(tmp) / 'missing.json', verify_frames=False, passes=all_passes())
            cal.write_text(json.dumps(self.calibration('stale')))
            stale = pm.build(path, calibration_path=cal, verify_frames=False, passes=all_passes())
        c = entry(with_cal, 'G1')['comparisonWithFit']
        self.assertEqual(c['status'], 'compared')
        self.assertAlmostEqual(c['printedMinusFitDeg'], 26.27 - 22.0)
        self.assertEqual(entry(with_cal, 'G4')['comparisonWithFit']['status'], 'no-fitted-yaw')
        self.assertEqual(entry(with_cal, 'G2')['comparisonWithFit']['status'], 'no-fit-entry-for-pose-method')
        self.assertEqual(entry(none, 'G1')['comparisonWithFit']['status'], 'no-calibration-json')
        self.assertEqual(entry(stale, 'G1')['comparisonWithFit']['status'], 'calibration-json-not-bound-to-these-observations')
        for other_doc in (other, none, stale):
            for key in ('yaw0Deg', 'fovDeg', 'uncertainty', 'errors'):
                self.assertEqual(entry(with_cal, 'G1')[key], entry(other_doc, 'G1')[key], key)


class Document(unittest.TestCase):
    def test_pending_cli_rerunnable_and_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, report = Path(tmp) / 'p.json', Path(tmp) / 'r.md'
            argv = ['--observations', str(Path(tmp) / 'missing.json'), '--output', str(out), '--report', str(report), '--calibration', str(Path(tmp) / 'none.json')]
            self.assertEqual(pm.main(argv), 0)
            first = out.read_bytes()
            pm.main(argv)
            self.assertEqual(first, out.read_bytes())
            doc = json.loads(first)
            self.assertEqual((doc['status'], doc['statusDetail']), ('pending-observations', 'pending-observations'))
            self.assertEqual([p['poseId'] for p in doc['poses']], ['G1', 'G2', 'G3', 'G3b', 'G4'])
            self.assertTrue(all(p['yaw0Deg'] is not None and p['observationsBound'] is False and p['satelliteValidationStatus'] in ('pending-observations', pm.NOT_OBSERVED) for p in doc['poses']))
            self.assertIn('Pendiente de observaciones', report.read_text())
            self.assertEqual(pm.main(argv + ['--strict']), 2)

    def test_frame_sha_is_mandatory_in_the_cli(self):
        row = make_obs('a', 'G1', G1_HELD, 0.4, imagePath='camera_assimilation/vision/nope.jpg', imageSha256='0' * 64)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'o.json'
            path.write_text(json.dumps({'schema': fit.OBSERVATIONS_SCHEMA, 'observations': [row]}))
            doc = pm.build(path, calibration_path=Path(tmp) / 'none.json')
            self.assertEqual(doc['status'], 'invalid-observations')
            self.assertTrue(all(p['heldOutIds'] == [] for p in doc['poses']))
        parser_source = (HERE / 'printed_model.py').read_text()
        self.assertNotIn('--no-verify', parser_source)
        self.assertNotIn('verify_frames=False', parser_source.split('def main')[1])

    def test_report_mentions_assumption_and_today_note(self):
        doc, _ = build_with([make_obs('a', 'G1', G1_HELD, 0.4)])
        text = pm.render_report(doc)
        self.assertIn('azimut supuesto', text)
        self.assertIn('prueba la pose', text)
        self.assertIn('printed-x-unverified-historical', text)

    def test_importable_by_filepath(self):
        spec = importlib.util.spec_from_file_location('c_side_printed', HERE / 'printed_model.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(callable(module.observation_bearing))


class RealInputs(unittest.TestCase):
    def test_real_firms_geometry_runs_without_changing_parameters(self):
        if not (fit.DEFAULT_SATELLITE_DIR / 'hotspots.geojson').exists():
            self.skipTest('satellite evidence not present')
        doc, _ = build_with([make_obs('a', 'G1', G1_HELD, 0.4), make_obs('b', 'G4', G4_PASS, 0.3)], passes=fit.load_passes())
        self.assertEqual(entry(doc, 'G1')['yaw0Deg'], 26.27)
        self.assertEqual(entry(doc, 'G4')['uncertainty']['suggestedAngularHalfWidthDeg'], 3.0)
        self.assertTrue(entry(doc, 'G4')['errors']['heldOut'][0]['centroid']['rangeM'] > 20000)


if __name__ == '__main__':
    unittest.main()
