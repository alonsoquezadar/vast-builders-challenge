"""Tests on SYNTHETIC fixtures (flat fake terrain, constant fake wind, a disc 'fire', a fake camera).
They verify the machinery (gates, causality, set-valued update, reserved data untouched). They are NOT results about the Garnet Fire
and say nothing about real camera or forecast skill.   python3 -m unittest test_assimilation   (from this directory)"""
import copy
import json
import sys
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import assimilate as asm  # noqa: E402
import config  # noqa: E402
import data as dat  # noqa: E402
import experiment as exp  # noqa: E402
import metrics as met  # noqa: E402
import model as mdl  # noqa: E402
import run  # noqa: E402
from grid import Grid  # noqa: E402

CFG = copy.deepcopy(config.CONFIG)
CAM = (-119.06, 36.80)
T0 = 1.7e9 + 3600


def fixture(n=200):
    grid = Grid(-119.10, -119.02, 36.88, 36.96)
    lon, lat = grid.centers_lonlat()
    init = np.where(np.hypot((lon - lon.mean()) * 88962, (lat - lat.mean()) * 111320) < 1000)[0]
    weather = {'epoch': np.arange(48) * 3600.0 + 1.7e9, 'from': np.full(48, 270.0), 'speed': np.full(48, 1.0)}
    mod = mdl.Model(grid, np.full(grid.size, 1500.0), weather, T0, init, np.full(len(init), -60.0), 4.0, 1.0, 12)
    t_end = 180.0
    base, brate = mod.run(mdl.baseline_theta(12), t_end)
    draws = mdl.sample_prior(n, 12, CFG['prior'], 1)
    parr, prate = mdl.run_ensemble(mod, draws, t_end)
    ctx = asm.Context(mod, CFG, base, brate, draws, parr, prate, t_end, {'syn-cam': CAM})
    ring = np.where((base > 80) & (base < 100))[0]
    return ctx, ring


def row(ctx, ring, off=1.5, sigma=1.0, rid='syn1', t=T0 + 100 * 60):
    b = ctx.geoms['syn-cam'].bearing
    tgt = ring[np.argmax(b[ring])]
    return {'id': rid, 'cameraId': 'syn-cam', 'poseId': 'G1', 'method': 'cosmos', 't': t, 'timeUtc': dat.utc_iso(t),
            'bearingDeg': float(b[tgt] + off), 'sigmaDeg': sigma, 'sigmaCalDeg': sigma, 'sigmaPixDeg': 0.0, 'sigmaSource': 'synthetic',
            'usedInCalibrationFit': False, 'cameraPositionStatus': 'synthetic', 'cameraLonLat': list(CAM), 'x_base': 0.5}


def obs(oid='o1', visible=True, x=0.5, time='2025-08-27T20:00:00Z', **kw):
    d = {'id': oid, 'cameraId': 'delilah', 'poseId': 'G1', 'sourceVideoSecond': 3, 'imagePath': 'x.jpg', 'imageSha256': '0' * 64,
         'frameWidth': 640, 'frameHeight': 360, 'printedTime': '2025-08-27T13:00:00', 'printedTimeStatus': 'verified-by-agent',
         'timeUtcAssumed': time, 'clockStatus': 'assumed-PDT', 'method': 'cosmos', 'smoke': True, 'base_visible': visible,
         'x_base': x if visible else None, 'y_base': 0.5 if visible else None, 'confidence': 0.5, 'reason': 'synthetic',
         'reviewStatus': 'pending-operator-review'}
    d.update(kw)
    return d


def pose(**kw):
    p = {'cameraId': 'delilah', 'poseId': 'G1', 'method': 'cosmos', 'status': 'experimental', 'yaw0Deg': 26.27, 'fovDeg': 56.0,
         'calibrationBasis': 'printed-x-unverified-historical', 'parameterOrigin': 'printed-X-prior-not-fitted', 'observationsBound': True,
         'trainingIds': [], 'heldOutIds': [], 'uncertainty': {'priorAngularHalfWidthDeg': 3.0, 'holdoutEvaluated': False}}
    p.update(kw)
    return p


def cal(*poses, **kw):
    d = {'schema': 'firetrace-camera-calibration-v1', 'status': 'experimental', 'calibrationBasis': 'printed-x-unverified-historical',
         'positions': {'delilah': {'coordinates': [-119.1175, 36.80417, 1570], 'status': 'candidate'}}, 'poses': list(poses) or [pose()]}
    d.update(kw)
    return d


def gate(o, c, allow=False, **kw):
    return dat.gate_observations({'observations': [o]}, c, CFG, 'cosmos', allow, 1.7e9, 1.8e9, **kw)


class SyntheticAssimilation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx, cls.ring = fixture()

    def test_camera_changes_posterior_only_inside_wedge(self):
        res = asm.run_cycle(self.ctx, [row(self.ctx, self.ring)], 'C01', 7)
        self.assertEqual(res['status'], 'updated', res['reason'])
        self.assertTrue(res['identifiedParameters'])
        base = np.where(np.isfinite(self.ctx.base_arr), self.ctx.base_arr, 1e6)
        corr = np.where(np.isfinite(res['corrected_arr']), res['corrected_arr'], 1e6)
        changed = np.abs(corr - base) > 1e-6
        self.assertGreater(changed.sum(), 0)
        self.assertFalse((changed & (res['wedgeWeight'] == 0)).any(), 'a correction appeared outside the camera wedge')
        self.assertTrue(np.array_equal(res['neutral_arr'][res['wedgeWeight'] == 0], self.ctx.base_arr[res['wedgeWeight'] == 0]))

    def test_unidentified_parameters_keep_their_prior(self):
        res = asm.run_cycle(self.ctx, [row(self.ctx, self.ring)], 'C01', 7)
        kept = [p for p in res['parameters'] if not p['identified']]
        self.assertTrue(kept)
        # composite members redraw non-identified parameters from the prior: the identified set is a strict subset
        self.assertLess(len(res['identifiedParameters']), len(res['parameters']))

    def test_hidden_base_never_enters_and_changes_nothing(self):
        c = cal()
        rows, ex = gate(obs('hid', visible=False), c)
        self.assertEqual(rows, [])
        self.assertEqual(ex[0]['reason'], 'hidden-base')
        rows, ex = gate(obs('hid2', visible=False, x_base=0.4), c)
        self.assertEqual(ex[0]['reason'], 'hidden-base-with-coordinate')
        r = row(self.ctx, self.ring)
        with_hidden = asm.run_cycle(self.ctx, [x for x in [r] + rows], 'C01', 7)
        alone = asm.run_cycle(self.ctx, [r], 'C01', 7)
        self.assertTrue(np.array_equal(with_hidden['corrected_arr'], alone['corrected_arr']))

    def test_noninformative_observation_gives_no_effect(self):
        far = row(self.ctx, self.ring, off=0.0, sigma=12.0)  # 12 deg covers the whole fire: compatible with everything
        res = asm.run_cycle(self.ctx, [far], 'C02', 3)
        self.assertEqual(res['status'], 'no-effect')
        self.assertTrue(np.array_equal(res['corrected_arr'], self.ctx.base_arr.astype(float)))

    def test_weight_collapse_gate_falls_back_to_baseline(self):
        ctx = copy.copy(self.ctx)
        ctx.cfg = copy.deepcopy(CFG)
        ctx.cfg['identifiability']['minEssFraction'] = 0.999
        res = asm.run_cycle(ctx, [row(ctx, self.ring)], 'C03', 7)
        self.assertEqual(res['status'], 'gated-weight-collapse')
        self.assertTrue(np.array_equal(res['corrected_arr'], ctx.base_arr.astype(float)))

    def test_cluster_issue_time_is_latest_row_and_cycles_cannot_see_later_rows(self):
        a, b = row(self.ctx, self.ring, rid='a', t=T0 + 3000), row(self.ctx, self.ring, rid='b', t=T0 + 6000)
        clusters = asm.make_clusters([b, a], 10.0)
        self.assertEqual([[r['id'] for r in c] for c in clusters], [['a'], ['b']])
        c1 = asm.run_cycle(self.ctx, clusters[0], 'C01', 1)
        self.assertEqual(c1['issueEpoch'], T0 + 3000)
        self.assertEqual(c1['observationIds'], ['a'])

    def test_pass_matching_requires_issue_strictly_before_pass(self):
        cycles = [{'cycleId': 'C1', 'issueEpoch': 1000.0}, {'cycleId': 'C2', 'issueEpoch': 1000.0 + 1800}]
        passes = [('P', {'t': 1000.0 + 1800})]  # pass at exactly C2's issue time
        m = exp.match_cycles(passes, cycles, CFG)
        used = {x['cycle']['cycleId'] for x in m if x['cycle']}
        self.assertNotIn('C2', used)
        self.assertIn('C1', used)
        for x in m:
            if x['cycle']:
                self.assertGreater(x['actualLeadMin'], 0)

    def test_metric_changes_with_firms_but_cycle_does_not(self):
        r = row(self.ctx, self.ring)
        a = asm.run_cycle(self.ctx, [r], 'C01', 7)
        b = asm.run_cycle(self.ctx, [r], 'C01', 7)  # FIRMS is not an input of run_cycle at all
        self.assertTrue(np.array_equal(a['corrected_arr'], b['corrected_arr']))
        near = {'lon': np.array([-119.0605]), 'lat': np.array([36.92]), 'pixelM': np.array([375])}
        far = {'lon': np.array([-119.0605]), 'lat': np.array([37.2]), 'pixelM': np.array([375])}
        init_mask = self.ctx.model.burned
        m1 = met.pass_metrics(self.ctx.base_arr, self.ctx.model.grid, init_mask, 100.0, near, 500, 60)
        m2 = met.pass_metrics(self.ctx.base_arr, self.ctx.model.grid, init_mask, 100.0, far, 500, 60)
        self.assertNotEqual(m1['medianNearestActiveBandM'], m2['medianNearestActiveBandM'])

    def test_verdict_reports_worsening(self):
        b, c = {'medianNearestActiveBandM': 500.0}, {'medianNearestActiveBandM': 900.0}
        self.assertEqual(met.verdict(b, c, 100.0)[0], 'worsened')
        self.assertEqual(met.verdict(c, b, 100.0)[0], 'improved')
        self.assertEqual(met.verdict(b, b, 100.0)[0], 'identical')
        self.assertEqual(met.verdict(b, {'medianNearestActiveBandM': None}, 100.0)[0], 'not-evaluable')


class Gates(unittest.TestCase):
    def test_printed_basis_usable_and_bearing_formula(self):
        rows, ex = gate(obs(x=0.5), cal())
        self.assertEqual(ex, [])
        self.assertAlmostEqual(rows[0]['bearingDeg'], 26.27, places=6)
        self.assertEqual(rows[0]['sigmaSource'], 'calibration.uncertainty.priorAngularHalfWidthDeg')
        self.assertAlmostEqual(rows[0]['sigmaCalDeg'], 3.0)

    def test_unbound_or_uncalibrated_pose_rejected(self):
        for p in (pose(observationsBound=False), pose(yaw0Deg=None), pose(status='no-calibration')):
            rows, ex = gate(obs(), cal(p))
            self.assertEqual((rows, ex[0]['reason']), ([], 'pose-not-calibrated'))

    def test_wrong_clock_or_uncertain_time_or_method_rejected(self):
        c = cal()
        self.assertEqual(gate(obs(clockStatus='PST'), c)[1][0]['reason'], 'clock-not-assumed-pdt')
        self.assertEqual(gate(obs(printedTimeStatus='uncertain'), c)[1][0]['reason'], 'printed-time-uncertain')
        self.assertEqual(gate(obs(method='simple-detector'), c)[1][0]['reason'], 'method-not-selected')
        self.assertEqual(gate(obs(x=1.5), c)[1][0]['reason'], 'x-out-of-range')

    def test_time_window_excludes_rows_outside(self):
        self.assertEqual(gate(obs(time='2020-01-01T00:00:00Z'), cal())[1][0]['reason'], 'outside-time-window')

    def test_sigma_gate(self):
        rows, ex = gate(obs(), cal(), sigma_override=40.0)
        self.assertEqual(ex[0]['reason'], 'sigma-gate')

    def test_fitted_experimental_needs_flag_and_reserves_holdout_ids(self):
        fitted = pose(calibrationBasis=None, parameterOrigin='fit', heldOutIds=['held'], trainingIds=['train'],
                      uncertainty={'fitPassSectorMaxHalfWidthDeg': 2.0, 'positionShift100mMaxYaw0Deg': 0.5})
        c = cal(fitted, calibrationBasis=None)
        self.assertEqual(gate(obs('o1'), c)[1][0]['reason'], 'pose-experimental-not-allowed')
        rows, _ = gate(obs('o1'), c, allow=True)
        self.assertEqual(rows[0]['sigmaSource'], 'fit-only-envelope')
        self.assertEqual(gate(obs('held'), c, allow=True)[1][0]['reason'], 'calibration-held-out-observation')
        self.assertTrue(gate(obs('train'), c, allow=True)[0][0]['usedInCalibrationFit'])

    def test_heldout_residuals_never_change_sigma(self):
        base = pose(calibrationBasis=None, uncertainty={'fitPassSectorMaxHalfWidthDeg': 2.0, 'positionShift100mMaxYaw0Deg': 0.5})
        leaky = copy.deepcopy(base)
        leaky['uncertainty'].update({'heldOutMaxAbsCentroidResidualDeg': 40.0, 'suggestedAngularHalfWidthDeg': 40.0})
        leaky['errors'] = {'heldOut': [{'centroid': {'absResidualDeg': {'max': 99}}}]}
        s1 = dat.pose_sigma_cal(base, cal(base, calibrationBasis=None), CFG)[0]
        s2 = dat.pose_sigma_cal(leaky, cal(leaky, calibrationBasis=None), CFG)[0]
        self.assertEqual(s1, s2)
        printed_leaky = pose(uncertainty={'priorAngularHalfWidthDeg': 40.0, 'holdoutEvaluated': True})
        self.assertEqual(dat.pose_sigma_cal(printed_leaky, cal(printed_leaky), CFG)[1], 'config-default-prior')

    def test_split_printed_basis_scores_every_post_t0_pass_and_never_fit(self):
        ids = ['A@1', 'B@2']
        split = dat.split_from_calibration(cal(), CFG, ids)
        self.assertEqual((split['fit'], split['heldOut']), ([], ids))
        fitted = cal(pose(calibrationBasis=None), calibrationBasis=None,
                     frozenSplit={'poses': {'G1': {'fit': ['A@1'], 'heldOut': ['B@2'], 'extraCheck': []}}})
        s2 = dat.split_from_calibration(fitted, CFG, ids)
        self.assertEqual((s2['fit'], s2['heldOut']), (['A@1'], ['B@2']))

    def test_passes_at_or_before_t0_and_fit_passes_are_not_scored(self):
        sat = dat.load_satellite(run.DEFAULT_SAT)
        t0 = dat.parse_epoch(CFG['t0']['primary'])
        table = dat.pass_table(sat)
        split = {'fit': ['NOAA21@2025-08-27T19:49:00Z'], 'heldOut': sorted(table), 'extraCheck': []}
        _, roles = exp.eval_passes(sat, split, t0, t0 + 7 * 3600)
        self.assertEqual(roles['NOAA21@2025-08-27T19:49:00Z'][0], 'calibration-fit-not-scored')
        self.assertTrue(all(r[0] == 'initialization-not-scored' for pid, r in roles.items() if table[pid]['t'] <= t0))


class RealDataSmoke(unittest.TestCase):
    """Uses the real Garnet layers and DEM with no camera input (baseline only): checks schema, strict JSON and the zero-use rule."""

    def test_paused_and_pending_scenarios(self):
        class A:
            observations, calibration = str(HERE / 'missing-observations.json'), str(HERE / 'missing-calibration.json')
            sat_dir, method, allow_experimental, sensitivity = str(run.DEFAULT_SAT), 'cosmos', False, False
            members, sigma_prior_deg, clock_sigma_min, t0, paused_reason = 5, None, None, None, None

        scen, geo = run.build(A)
        self.assertEqual(scen['status'], 'pending-inputs')
        A.paused_reason = 'test pause'
        scen, geo = run.build(A)
        self.assertEqual(scen['status'], 'paused-next-phase')
        self.assertEqual((scen['cameraUseCount'], scen['forecasts'], scen['corrected']['status']), (0, [], 'disabled'))
        self.assertTrue(scen['initialization']['retrospectiveLeakage'])
        self.assertFalse(scen['operationalForecast'])
        for key in ('schema', 'status', 'dataClasses', 'initialization', 'cameraUseCount', 'idList', 'baseline', 'corrected', 'forecasts', 'metrics', 'limitations'):
            self.assertIn(key, scen)
        json.dumps(scen, allow_nan=False, default=run.jdefault)
        json.dumps(geo, allow_nan=False, default=run.jdefault)
        kinds = {f['properties']['kind'] for f in geo['features']}
        self.assertIn('initialization-footprint', kinds)
        self.assertIn('validation-detection', kinds)
        for pid, info in scen['idList']['passRoles'].items():
            if info['role'] == 'validation':
                self.assertGreater(info['utc'], scen['initialization']['t0Utc'])


if __name__ == '__main__':
    unittest.main()
