"""Cheap tests for fit.py. Synthetic data below checks the code, it is NOT a measurement.

Run: python3 -m unittest discover -s tools/firetrace/camera_assimilation/calibration -p 'test_fit.py'
"""
import importlib.util
import json
import math
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location('firetrace_calibration_fit', HERE / 'fit.py')
fit = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = fit
_spec.loader.exec_module(fit)

SPLIT_SHA256 = 'c08b34094debb8b43111a69c673723c0325b9ce3ed9e452bb1c0cfe51cc5769f'
CAMERA = [-119.1175, 36.80417, 1570]
FIT_PASS = 'NOAA21@2025-08-27T19:49:00Z'
HELD_PASS = 'SNPP@2025-08-27T20:16:00Z'
EXTRA_PASS = 'MODIS@2025-08-27T18:17:00Z'


def destination(origin, bearing, distance_m):
    lon, lat, brg, d = math.radians(origin[0]), math.radians(origin[1]), math.radians(bearing), distance_m / fit.EARTH_RADIUS_M
    lat2 = math.asin(math.sin(lat) * math.cos(d) + math.cos(lat) * math.sin(d) * math.cos(brg))
    lon2 = lon + math.atan2(math.sin(brg) * math.sin(d) * math.cos(lat), math.cos(d) - math.sin(lat) * math.sin(lat2))
    return [math.degrees(lon2), math.degrees(lat2)]


def synthetic_pass(pid, camera, bearings, range_m=15000.0, pixel=375):
    source, epoch = fit.PASSES[pid]
    return {'id': pid, 'source': source, 't': epoch, 'acquiredUtc': '', 'declaredDetections': len(bearings),
            'points': [tuple(destination(camera, b, range_m)) + (10.0, pixel) for b in bearings]}


def make_passes(camera, centre=30.0, held_centre=33.0):
    return {FIT_PASS: synthetic_pass(FIT_PASS, camera, [centre - 0.3, centre, centre + 0.3]),
            HELD_PASS: synthetic_pass(HELD_PASS, camera, [held_centre - 0.3, held_centre, held_centre + 0.3]),
            EXTRA_PASS: synthetic_pass(EXTRA_PASS, camera, [centre + 1], pixel=1000)}


def x_for(bearing, yaw0, fov):
    return (math.tan(math.radians(fit.wrap180(bearing - yaw0))) / math.tan(math.radians(fov) / 2) + 1) / 2


def make_obs(oid, pose_id, pass_id, x, minutes=0.0, method='cosmos', **extra):
    printed = datetime.fromtimestamp(fit.PASSES[pass_id][1], timezone.utc) - timedelta(hours=7) + timedelta(minutes=minutes)
    camera_id = fit.POSES[pose_id]['cameraId']
    row = {'id': oid, 'cameraId': camera_id, 'poseId': pose_id, 'method': method, 'base_visible': True, 'x_base': x, 'y_base': 0.5,
           'printedTime': printed.replace(tzinfo=None).isoformat(), 'printedTimeStatus': 'verified-by-agent',
           'timeUtcAssumed': (printed + timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%SZ'), 'clockStatus': 'assumed-PDT',
           'smoke': True, 'reviewStatus': 'pending-operator-review'}
    row.update(extra)
    return row


class SyntheticFit(unittest.TestCase):
    """Truth is built in; checks the maths and bookkeeping only."""

    def setUp(self):
        self.fov = fit.effective_fov_deg(1.2)
        self.yaw = 40.0
        self.passes = make_passes(CAMERA)
        self.obs = [make_obs('f1', 'G1', FIT_PASS, x_for(30.0, self.yaw, self.fov), minutes=1),
                    make_obs('f2', 'G1', FIT_PASS, x_for(30.0, self.yaw, self.fov), minutes=-2),
                    make_obs('h1', 'G1', HELD_PASS, x_for(33.0, self.yaw, self.fov), minutes=2)]

    def run_fit(self, observations=None, **kw):
        return fit.fit_pose('G1', self.obs if observations is None else observations, self.passes, CAMERA, method='cosmos', **kw)

    def test_recovers_known_yaw0_and_heldout_exactly(self):
        # Fit pass centroid is the built-in truth direction, so the answer is analytic.
        r = self.run_fit()
        self.assertAlmostEqual(r['yaw0Deg'], self.yaw, places=4)
        held = r['evaluation']['heldOut'][0]
        self.assertLess(abs(held['centroid']['meanSignedResidualDeg']), 0.1)
        self.assertEqual(held['nearestGroup']['distanceDeg']['mean'], 0.0)
        self.assertEqual(r['trainingIds'], ['f1', 'f2'])
        self.assertEqual(r['heldOutIds'], ['h1'])

    def test_heldout_error_has_expected_size_in_metres(self):
        # Truth for the held-out pass is 8 deg from the fit pass, observed at 3 deg: 5 deg residual at 15 km.
        obs = self.obs[:2] + [make_obs('h1', 'G1', HELD_PASS, x_for(38.0, self.yaw, self.fov), minutes=0)]
        held = self.run_fit(obs)['evaluation']['heldOut'][0]
        self.assertAlmostEqual(abs(held['centroid']['meanSignedResidualDeg']), 5.0, delta=0.1)
        self.assertAlmostEqual(held['centroid']['crossTrackM']['mean'], 15000 * math.sin(math.radians(5.0)), delta=60)
        self.assertAlmostEqual(held['nearestGroup']['distanceDeg']['mean'], 5.0 - 0.3 - 0.7, delta=0.1)  # 0.3 deg group + ~0.7 deg pixel half width
        self.assertNotEqual(held['centroid']['crossTrackM']['mean'], held['nearestGroup']['crossTrackM']['mean'])

    def test_azimuth_wrap_across_north(self):
        camera = CAMERA
        passes = make_passes(camera, centre=359.0, held_centre=3.0)
        yaw = 358.0
        obs = [make_obs('f1', 'G1', FIT_PASS, x_for(359.0, yaw, self.fov)), make_obs('h1', 'G1', HELD_PASS, x_for(3.0, yaw, self.fov))]
        r = fit.fit_pose('G1', obs, passes, camera, method='cosmos')
        self.assertLess(abs(fit.wrap180(r['yaw0Deg'] - yaw)), 0.05)
        self.assertLess(abs(r['evaluation']['heldOut'][0]['centroid']['meanSignedResidualDeg']), 0.1)
        self.assertAlmostEqual(fit.wrap180(350 - 10), -20.0)
        self.assertAlmostEqual(fit.bearing_from_x(0.5, 358.0, self.fov), 358.0)
        self.assertAlmostEqual(fit.bearing_from_x(1.0, 358.0, self.fov), fit.wrap360(358.0 + fit.relative_angle_deg(1.0, self.fov)))
        self.assertTrue(0 <= fit.bearing_from_x(1.0, 358.0, self.fov) < 360)

    def test_no_leakage_from_heldout_or_extra_observations(self):
        base = self.run_fit()
        wild = [dict(o, x_base=0.99) if o['id'] == 'h1' else o for o in self.obs]
        wild.append(make_obs('e1', 'G1', EXTRA_PASS, 0.01))
        again = self.run_fit(wild)
        self.assertEqual(base['yaw0Deg'], again['yaw0Deg'])
        self.assertEqual(set(again['trainingIds']) & set(again['heldOutIds'] + again['extraCheckIds']), set())
        self.assertEqual(again['extraCheckIds'], ['e1'])

    def test_heldout_alone_does_not_fit(self):
        r = self.run_fit([o for o in self.obs if o['id'] == 'h1'])
        self.assertIsNone(r['yaw0Deg'])
        self.assertEqual(r['status'], 'no-calibration')
        self.assertIn('fit pass', r['reason'])

    def test_frozen_split_is_preregistered_and_disjoint(self):
        self.assertEqual(fit.split_sha256(), SPLIT_SHA256, 'split changed after it was frozen')
        for pose, roles in fit.SPLIT.items():
            ids = roles['fit'] + roles['heldOut'] + roles['extraCheck']
            self.assertEqual(len(ids), len(set(ids)), pose)
            self.assertTrue(all(i in fit.PASSES for i in ids))
        self.assertEqual(fit.SPLIT['G4']['fit'], ['NOAA21@2025-08-27T21:29:00Z'])
        self.assertEqual(fit.SPLIT['G4']['heldOut'], ['SNPP@2025-08-27T21:57:00Z', 'MODIS@2025-08-27T23:00:00Z'])
        self.assertEqual(fit.SPLIT['G1']['fit'], fit.SPLIT['G3b']['fit'])
        self.assertEqual(fit.SPLIT['G2']['fit'] + fit.SPLIT['G3']['fit'], [])

    def test_hidden_base_never_enters_fit(self):
        hidden = make_obs('hid', 'G1', FIT_PASS, None, base_visible=False)
        invented = make_obs('inv', 'G1', FIT_PASS, 0.9, base_visible=False)
        null_visible = make_obs('nul', 'G1', FIT_PASS, None)
        r = self.run_fit(self.obs + [hidden, invented, null_visible])
        reasons = {e['id']: e['reason'] for e in r['excluded']}
        self.assertEqual(reasons, {'hid': 'base-hidden', 'inv': 'hidden-base-with-coordinate', 'nul': 'x-null-while-visible'})
        self.assertAlmostEqual(r['yaw0Deg'], self.run_fit()['yaw0Deg'], places=9)

    def test_uncertain_time_and_clock_rows_are_rejected(self):
        extra = [make_obs('u1', 'G1', FIT_PASS, 0.9, printedTimeStatus='uncertain'),
                 make_obs('u2', 'G1', FIT_PASS, 0.9, clockStatus='unknown'),
                 make_obs('u3', 'G1', FIT_PASS, 0.9, timeUtcAssumed='2025-08-27T10:00:00Z'),
                 make_obs('u4', 'G1', FIT_PASS, 1.4)]
        r = self.run_fit(self.obs + extra)
        self.assertEqual({e['id'] for e in r['excluded']}, {'u1', 'u2', 'u3', 'u4'})
        self.assertEqual(r['trainingIds'], ['f1', 'f2'])

    def test_five_minute_gap_limit_and_clock_offset(self):
        near = make_obs('near', 'G1', FIT_PASS, 0.5, minutes=4.9)
        far = make_obs('far', 'G1', FIT_PASS, 0.5, minutes=5.2)
        r = self.run_fit([near, far])
        self.assertEqual(r['trainingIds'], ['near'])
        self.assertEqual(r['excluded'][0]['reason'], 'no-pass-within-5min')
        shifted = self.run_fit([near], clock_offset_min=2)  # camera clock +2 min -> 6.9 min away
        self.assertIsNone(shifted['yaw0Deg'])
        self.assertAlmostEqual(r['matched'][0]['gap'], 4.9 * 60, delta=1)

    def test_pose_mixing_is_refused(self):
        wrong_camera = make_obs('wc', 'G1', FIT_PASS, 0.5, cameraId='buckrock')
        g2 = make_obs('g2', 'G2', FIT_PASS, 0.5)
        late = make_obs('late', 'G1', FIT_PASS, 0.5, minutes=0)
        late['printedTime'] = '2025-08-27T17:30:00'  # inside G2's window, not G1's
        late['timeUtcAssumed'] = '2025-08-28T00:30:00Z'
        r = self.run_fit(self.obs + [wrong_camera, late])
        self.assertEqual({e['id']: e['reason'] for e in r['excluded']}, {'wc': 'camera-pose-mismatch', 'late': 'outside-pose-window'})
        g2_fit = fit.fit_pose('G2', [g2], self.passes, CAMERA, method='cosmos')
        self.assertIsNone(g2_fit['yaw0Deg'])
        self.assertEqual(g2_fit['reason'], fit.NO_PASS_REASON)
        # G1 and G3b are different cameras: a G3b row never reaches G1.
        g3b = make_obs('g3b', 'G3b', FIT_PASS, 0.1)
        self.assertEqual(self.run_fit(self.obs + [g3b])['trainingIds'], ['f1', 'f2'])
        self.assertEqual(fit.fit_pose('G3b', self.obs + [g3b], self.passes, CAMERA, method='cosmos')['trainingIds'], ['g3b'])

    def test_methods_are_never_pooled(self):
        other = make_obs('s1', 'G1', FIT_PASS, 0.8, method='simple-detector')
        both = self.obs + [other]
        cosmos = fit.fit_pose('G1', both, self.passes, CAMERA, method='cosmos')
        simple = fit.fit_pose('G1', both, self.passes, CAMERA, method='simple-detector')
        self.assertEqual(cosmos['trainingIds'], ['f1', 'f2'])
        self.assertEqual(simple['trainingIds'], ['s1'])
        self.assertNotEqual(cosmos['yaw0Deg'], simple['yaw0Deg'])
        self.assertEqual(fit.fit_pose('G1', both, self.passes, CAMERA, method=None)['trainingIds'], [])

    def test_fov_is_fixed_and_not_identifiable_from_one_pass(self):
        r = self.run_fit()
        self.assertFalse(r['identifiability']['fovFitted'])
        self.assertFalse(r['identifiability']['fovIdentifiable'])
        self.assertAlmostEqual(r['fovDeg'], 56.018, places=2)
        self.assertIsNone(fit.design_condition([0.4, 0.4, 0.4], 56.0))
        self.assertIsNotNone(fit.design_condition([0.1, 0.9, 0.5], 56.0))

    def test_inconsistent_fit_frames_report_empty_sector(self):
        far_apart = [make_obs('a', 'G1', FIT_PASS, 0.1), make_obs('b', 'G1', FIT_PASS, 0.9)]
        r = self.run_fit(far_apart)
        self.assertTrue(r['sectorIntersectionEmpty'])
        self.assertIsNone(r['yaw0FeasibleSector'])

    def test_position_shift_moves_yaw_by_about_offset_over_range(self):
        base = self.run_fit()['yaw0Deg']
        moved = fit.fit_pose('G1', self.obs, self.passes, fit.shift_position(CAMERA, 500.0, 0.0), method='cosmos')['yaw0Deg']
        shift = abs(fit.wrap180(moved - base))
        self.assertLess(shift, math.degrees(500.0 / 15000.0) + 0.2)
        self.assertGreater(shift, 0.5)

    def test_relative_angle_and_focal_scaling(self):
        self.assertAlmostEqual(fit.relative_angle_deg(0.5, 65.1), 0.0)
        self.assertAlmostEqual(fit.relative_angle_deg(1.0, 65.1), 32.55, places=6)
        self.assertAlmostEqual(fit.relative_angle_deg(0.0, 65.1), -32.55, places=6)
        self.assertAlmostEqual(fit.effective_fov_deg(1.0), 65.1, places=9)
        self.assertLess(fit.effective_fov_deg(1.4), fit.effective_fov_deg(1.2))


class BearingApi(unittest.TestCase):
    def pose(self):
        return {'cameraId': 'delilah', 'poseId': 'G1', 'method': 'cosmos', 'yaw0Deg': 10.0, 'fovDeg': 56.0,
                'uncertainty': {'suggestedAngularHalfWidthDeg': 4.0, 'validated': True}}

    def test_matches_formula_and_refuses_unusable_rows(self):
        obs = make_obs('bearing-test', 'G1', FIT_PASS, 0.75)
        out = fit.observation_bearing(obs, self.pose())
        self.assertTrue(out['usable'])
        self.assertAlmostEqual(out['bearingDeg'], (10.0 + math.degrees(math.atan(0.5 * math.tan(math.radians(28.0))))) % 360)
        self.assertEqual(out['angularHalfWidthDeg'], 4.0)
        for bad in (dict(obs, base_visible=False), dict(obs, x_base=None), dict(obs, x_base=1.2), dict(obs, poseId='G2'),
                    dict(obs, cameraId='buckrock'), dict(obs, method='simple-detector'), dict(obs, printedTimeStatus='uncertain'), dict(obs, timeUtcAssumed='invalid')):
            self.assertFalse(fit.observation_bearing(bad, self.pose())['usable'], bad)
        self.assertFalse(fit.observation_bearing(obs, dict(self.pose(), yaw0Deg=None))['usable'])

    def test_c_can_import_by_filepath(self):
        spec = importlib.util.spec_from_file_location('c_side_import', HERE / 'fit.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # deliberately not registered in sys.modules
        self.assertTrue(callable(module.observation_bearing))


class Document(unittest.TestCase):
    def test_pending_observations_and_cli_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, report = Path(tmp) / 'c.json', Path(tmp) / 'r.md'
            argv = ['--observations', str(Path(tmp) / 'missing.json'), '--output', str(out), '--report', str(report)]
            self.assertEqual(fit.main(argv), 0)
            first = out.read_bytes()
            fit.main(argv)
            self.assertEqual(first, out.read_bytes())
            doc = json.loads(first)
            self.assertEqual(doc['status'], 'no-calibration')
            self.assertEqual(doc['statusDetail'], 'pending-observations')
            self.assertEqual([p['poseId'] for p in doc['poses']], ['G1', 'G2', 'G3', 'G3b', 'G4'])
            self.assertTrue(all(p['yaw0Deg'] is None and p['reason'] for p in doc['poses']))
            self.assertIn('pending-observations', report.read_text())
            self.assertEqual(fit.main(argv + ['--strict']), 2)

    def test_invalid_observations_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / 'o.json'
            bad.write_text(json.dumps({'schema': 'something-else', 'observations': []}))
            doc = fit.build(bad)
            self.assertEqual(doc['statusDetail'], 'invalid-observations')
            self.assertTrue(all(p['yaw0Deg'] is None for p in doc['poses']))

    def test_synthetic_end_to_end_document(self):
        # Uses the REAL FIRMS passes with SYNTHETIC observations: exercises the pipeline, proves nothing physical.
        passes = fit.load_passes()
        geometry = fit.pass_geometry(passes[FIT_PASS], CAMERA)
        fov = fit.effective_fov_deg(1.2)
        yaw = fit.wrap360(geometry['centroidBearingDeg'] - 5.0)
        rows = [make_obs('syn-fit', 'G1', FIT_PASS, x_for(geometry['centroidBearingDeg'], yaw, fov))]
        held_geom = fit.pass_geometry(passes[HELD_PASS], CAMERA)
        rows.append(make_obs('syn-held', 'G1', HELD_PASS, x_for(held_geom['centroidBearingDeg'], yaw, fov)))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'o.json'
            path.write_text(json.dumps({'schema': fit.OBSERVATIONS_SCHEMA, 'observations': rows}))
            doc = fit.build(path, verify_frames=False)
        self.assertEqual(doc['status'], 'experimental')
        pose = next(p for p in doc['poses'] if p['poseId'] == 'G1')
        self.assertAlmostEqual(pose['yaw0Deg'], yaw, places=4)
        held = pose['errors']['heldOut'][0]
        self.assertLess(held['centroid']['absResidualDeg']['max'], 1e-3)
        self.assertEqual(pose['sensitivity']['position'][2]['radiusM'], 500)
        self.assertEqual(len(pose['sensitivity']['clockOffsetMin']), 7)
        self.assertEqual([c['hypothesis'] for c in pose['sensitivity']['clockHypothesis']], ['assumed-PDT', 'PST', 'UTC'])
        self.assertTrue(pose['bearingModel']['usable'])
        self.assertIn('## delilah / G1 / cosmos', fit.render_report(doc))
        json.dumps(doc)  # serialisable


class ExternalPrintedXCheck(unittest.TestCase):
    def setUp(self):
        self.fov = fit.effective_fov_deg(1.2)
        self.passes = make_passes(CAMERA)

    def doc(self, printed_x):
        yaw = 40.0
        rows = [make_obs('f1', 'G1', FIT_PASS, x_for(30.0, yaw, self.fov)), make_obs('h1', 'G1', HELD_PASS, x_for(33.0, yaw, self.fov))]
        saved = dict(fit.PRINTED_X_DEG)
        fit.PRINTED_X_DEG['G1'] = printed_x
        try:
            return fit.build_pose_entry('G1', 'cosmos', rows, self.passes, CAMERA, 'delilah')
        finally:
            fit.PRINTED_X_DEG.clear()
            fit.PRINTED_X_DEG.update(saved)

    def test_printed_x_is_never_an_input_of_the_fit(self):
        a, b = self.doc(41.5), self.doc(250.0)
        self.assertEqual(a['yaw0Deg'], b['yaw0Deg'])
        self.assertEqual(a['errors'], b['errors'])
        self.assertFalse(a['externalCheck']['usedInFit'])

    def test_difference_is_wrapped_and_scored_without_fit(self):
        e = self.doc(41.5)['externalCheck']
        self.assertAlmostEqual(e['yaw0MinusPrintedXDeg'], -1.5, places=3)
        held = e['printedXAsZeroParameterYaw0']['heldOut'][0]
        self.assertAlmostEqual(held['centroid']['meanSignedResidualDeg'], 1.5, delta=0.1)  # X +1.5 deg -> predictions +1.5 deg
        wrapped = self.doc(40.0 - 360.0 + 2.0)['externalCheck']
        self.assertAlmostEqual(wrapped['yaw0MinusPrintedXDeg'], -2.0, places=3)

    def test_only_poses_with_printed_x_get_a_check_and_current_frame_is_context_only(self):
        self.assertEqual(sorted(fit.PRINTED_X_DEG), ['G1', 'G2', 'G3b', 'G4'])
        self.assertEqual((fit.PRINTED_X_DEG['G1'], fit.PRINTED_X_DEG['G3b'], fit.PRINTED_X_DEG['G4']), (26.27, -39.19, -26.13))
        if fit.DEFAULT_CLOCK_CHECK.exists():
            cf = fit.load_clock_check(fit.DEFAULT_CLOCK_CHECK)
            self.assertFalse(cf['historicalPoseVerified'])
            self.assertEqual(len(cf['results']), 2)


class RealSatelliteInputs(unittest.TestCase):
    def test_satellite_targets_are_measured_and_wrap_safe(self):
        if not (fit.DEFAULT_SATELLITE_DIR / 'hotspots.geojson').exists():
            self.skipTest('satellite evidence not present')
        positions, _ = fit.load_positions(fit.DEFAULT_REFERENCES)
        rows = fit.satellite_targets(fit.load_passes(), positions)
        self.assertEqual(len(rows), 4 + 4 + 3)  # G1, G3b (fit+2 held+extra each) and G4 (fit+2 held)
        g1 = next(r for r in rows if r['poseId'] == 'G1' and r['role'] == 'fit')
        self.assertTrue(0 < g1['centroidBearingDeg'] < 40 and 8000 < g1['centroidRangeM'] < 20000)
        self.assertGreater(g1['sectorWidthDeg'], 0)
        self.assertIsNone(fit.x_column_for_bearing(200.0, 20.0, 56.0))  # behind the camera
        self.assertAlmostEqual(fit.x_column_for_bearing(20.0, 20.0, 56.0), 0.5)

    def test_passes_match_overpasses_and_group_structure(self):
        if not (fit.DEFAULT_SATELLITE_DIR / 'hotspots.geojson').exists():
            self.skipTest('satellite evidence not present')
        passes = fit.load_passes()  # raises if a point count differs from overpasses.json
        overpasses = {(r['source'], r['t']): r for r in json.loads((fit.DEFAULT_SATELLITE_DIR / 'overpasses.json').read_text())['overpasses']}
        for pid, (source, epoch) in fit.PASSES.items():
            centroid = overpasses[(source, epoch)]['centroid']
            pts = passes[pid]['points']
            self.assertAlmostEqual(sum(p[0] for p in pts) / len(pts), centroid[0], delta=2e-5)
            self.assertAlmostEqual(sum(p[1] for p in pts) / len(pts), centroid[1], delta=2e-5)
        geometry = fit.pass_geometry(passes['NOAA21@2025-08-27T21:29:00Z'], [-118.86067, 36.73727, 2578])
        self.assertEqual(sum(g['n'] for g in geometry['groups']), 72)

class RootHoldoutRegression(unittest.TestCase):
    def test_prediction_uncertainty_never_uses_heldout_errors(self):
        passes=make_passes(CAMERA);fov=fit.effective_fov_deg(1.2)
        train=make_obs('fit','G1',FIT_PASS,x_for(30,40,fov))
        def entry(x):
            return fit.build_pose_entry('G1','cosmos',[train,make_obs('held','G1',HELD_PASS,x)],passes,CAMERA,'delilah')
        a,b=entry(0.05),entry(0.95)
        self.assertEqual(a['yaw0Deg'],b['yaw0Deg'])
        self.assertEqual(a['uncertainty']['suggestedAngularHalfWidthDeg'],b['uncertainty']['suggestedAngularHalfWidthDeg'])
        self.assertFalse(a['uncertainty']['validated'])
        self.assertTrue(a['uncertainty']['holdoutEvaluated'])

    def test_gap_between_groups_does_not_count_as_angular_support(self):
        data=synthetic_pass(FIT_PASS,CAMERA,[20.0,40.0])
        geometry=fit.pass_geometry(data,CAMERA)
        result=fit.evaluate_rows([{'id':'gap','x':0.5,'passId':FIT_PASS,'gap':0}],{FIT_PASS:geometry},30,65.1)[0]
        self.assertFalse(result['observations'][0]['insideAnySector'])
        self.assertEqual(result['sector']['insideFraction'],0)
        self.assertGreater(result['nearestGroup']['distanceDeg']['mean'],0)

    def test_loading_requires_matching_frame_receipts(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);vision=root/'camera_assimilation/vision';vision.mkdir(parents=True)
            image=vision/'frame.jpg';image.write_bytes(b'frame')
            row=make_obs('receipt','G1',FIT_PASS,0.5,imagePath='camera_assimilation/vision/frame.jpg',imageSha256=fit.sha256_file(image))
            path=root/'observations.json';path.write_text(json.dumps({'schema':fit.OBSERVATIONS_SCHEMA,'observations':[row]}))
            with patch.object(fit,'FIRETRACE',root):
                self.assertEqual(len(fit.load_observations(path)['observations']),1)
                image.write_bytes(b'changed')
                with self.assertRaises(ValueError):fit.load_observations(path)

if __name__ == '__main__':
    unittest.main()
