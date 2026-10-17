import json
import unittest
from pathlib import Path

import numpy as np

import reconstruction_forecast as rf
import video_scenario as vs

HERE = Path(__file__).resolve().parent
DOC = SRC = None


def setUpModule():
    global DOC, SRC
    SRC = rf.load_sources()
    DOC = vs.build(SRC)


def P():
    return DOC['properties']


class ScenarioTests(unittest.TestCase):
    def test_contract(self):
        p = P()
        self.assertEqual(p['schema'], 'firetrace-video-scenario-v1')
        self.assertIs(p['validated'], False)
        self.assertEqual(p['dataClass'], 'modelled')
        self.assertEqual(p['endSec'] - p['startSec'], 8 * 3600)
        self.assertEqual(p['evaluation']['referenceClass'], 'later satellite reconstruction; not independent validation')
        for key in ('source', 'assumptions', 'limitations', 'provenance', 'bias'):
            self.assertTrue(p[key])

    def test_initial_matches_input(self):
        t0 = P()['startSec']
        self.assertEqual(P()['initialCells'], int((SRC.t_grid <= t0).sum()))
        self.assertEqual(P()['initialAreaHa'], round(P()['initialCells'] * P()['cellAreaHa'], 2))
        self.assertEqual(P()['series'][0]['modelledAreaHa'], P()['initialAreaHa'])
        self.assertEqual(P()['series'][0]['newAreaHa'], 0)
        self.assertEqual(P()['provenance']['arrivalSha256'], SRC.arrival_sha)

    def test_features_are_only_new_modelled_cells(self):
        p = P()
        self.assertEqual(len(DOC['features']), p['newCellCount'])
        seen = set()
        for f in DOC['features']:
            fp = f['properties']
            self.assertEqual(set(fp), {'arrivalSec', 'cellAreaHa', 'dataClass'})
            self.assertEqual(fp['dataClass'], 'modelled')
            self.assertTrue(p['startSec'] <= fp['arrivalSec'] <= p['endSec'])
            ring = f['geometry']['coordinates'][0]
            self.assertEqual(ring[0], ring[-1])
            key = tuple(ring[0])
            self.assertNotIn(key, seen)
            seen.add(key)
        # no feature coincides with an initial cell
        grid = SRC.grid
        rows, cols = np.nonzero(SRC.t_grid <= p['startSec'])
        init = {tuple(vs.cell_polygon(int(r), int(c), grid)[0]) for r, c in zip(rows, cols)}
        self.assertFalse(seen & init)

    def test_progressive_arrival_inside_video_interval(self):
        p = P()
        times = [f['properties']['arrivalSec'] for f in DOC['features']]
        in_video = [t for t in times if p['videoStartSec'] <= t <= p['videoEndSec']]
        self.assertGreater(len(in_video), 20)
        self.assertGreater(len(set(in_video)), 10)
        self.assertLess(len(in_video), len(times))

    def test_series_consistent(self):
        p = P()
        s = p['series']
        self.assertEqual([x['timeSec'] for x in s], list(range(p['startSec'], p['endSec'] + 1, 300)))
        self.assertEqual(s[-1]['timeSec'], p['endSec'])
        areas = [x['modelledAreaHa'] for x in s]
        self.assertEqual(areas, sorted(areas))
        for a, b in zip(s, s[1:]):
            self.assertAlmostEqual(b['incrementAreaHa'], b['modelledAreaHa'] - a['modelledAreaHa'], places=2)
            self.assertAlmostEqual(b['newAreaHa'], b['modelledAreaHa'] - p['initialAreaHa'], places=2)
        total_new = sum(f['properties']['cellAreaHa'] for f in DOC['features'])
        self.assertAlmostEqual(s[-1]['modelledAreaHa'] - p['initialAreaHa'], total_new, places=2)

    def test_evaluation_at_exact_overpass(self):
        e = P()['evaluation']
        self.assertEqual(e['timeUtc'], '2025-08-28T05:19:00Z')
        self.assertEqual(e['timeSec'], vs._epoch('2025-08-28T05:19:00Z'))
        at = max((x for x in P()['series'] if x['timeSec'] <= e['timeSec']), key=lambda x: x['timeSec'])
        # series is on a 5-minute grid: 05:19 lies between 05:15 and 05:20, so predicted is bracketed
        nxt = min((x for x in P()['series'] if x['timeSec'] >= e['timeSec']), key=lambda x: x['timeSec'])
        self.assertLessEqual(at['modelledAreaHa'], e['predictedAreaHa'])
        self.assertLessEqual(e['predictedAreaHa'], nxt['modelledAreaHa'])
        ref = int((SRC.t_grid <= e['timeSec']).sum()) * P()['cellAreaHa']
        self.assertEqual(e['referenceAreaHa'], round(ref, 2))
        self.assertTrue(0 <= e['iou'] <= 1)

    def test_next_overpass_must_exist(self):
        with self.assertRaises(ValueError):
            vs.next_overpass(vs._epoch('2025-08-28T05:20:00Z'))

    def test_only_recent_boundary_ignites(self):
        t0 = P()['startSec']
        initial, seeds = vs.recent_seed_mask(SRC, t0)
        boundary = rf._boundary_cells(initial)
        self.assertTrue((seeds & ~boundary).sum() == 0)
        self.assertTrue((SRC.t_grid[seeds] > t0 - 12 * 3600).all())
        self.assertLess(seeds.sum(), boundary.sum())
        self.assertEqual(P()['activeSeedCount'], int(seeds.sum()))
        # old-boundary-only cells have no influence: the arrival field equals the field from recent seeds alone
        arrival, _, _ = vs.run_model(SRC, t0)
        full = rf.propagate(SRC.dem, SRC.grid['cellM'], initial, [(w['windFromDeg'], w['windSpeedMps']) for w in rf._weather_window(SRC, t0)], 0.0, 480.0)
        self.assertLessEqual(np.isfinite(arrival).sum(), np.isfinite(full).sum())
        self.assertTrue((arrival >= full - 1e-9).all())  # fewer seeds can never arrive earlier

    def test_default_propagate_unchanged_and_seed_validation(self):
        z = np.zeros((9, 9))
        m = np.zeros((9, 9), bool); m[4, 4] = True
        wind = [(270, 0.0)] * 2
        a = rf.propagate(z, 200.0, m, wind, 0.0, 60.0)
        b = rf.propagate(z, 200.0, m, wind, 0.0, 60.0, seed_mask=m)
        np.testing.assert_array_equal(a, b)
        with self.assertRaises(ValueError):
            rf.propagate(z, 200.0, m, wind, 0.0, 60.0, seed_mask=np.ones((9, 9), bool))

    def test_wind_direction_steers_spread(self):
        z = np.zeros((41, 41))
        m = np.zeros((41, 41), bool); m[20, 20] = True
        east = rf.propagate(z, 200.0, m, [(270, 8.0)] * 6, 0.0, 360.0)   # from west -> blows towards east
        north = rf.propagate(z, 200.0, m, [(180, 8.0)] * 6, 0.0, 360.0)  # from south -> towards north
        self.assertLess(east[20, 23], east[20, 17])
        self.assertLess(east[20, 23], east[17, 20])
        self.assertLess(north[17, 20], north[23, 20])
        self.assertLess(north[17, 20], north[20, 23])

    def test_no_observed_claims(self):
        text = json.dumps(DOC).lower()
        self.assertNotIn('"observed"', text)
        self.assertEqual({f['properties']['dataClass'] for f in DOC['features']}, {'modelled'})

    def test_saved_file_matches_generator(self):
        saved = json.loads((HERE / 'evidence' / 'garnet' / 'video-scenario.json').read_text())
        self.assertEqual(saved, json.loads(json.dumps(DOC, ensure_ascii=False)))


if __name__ == '__main__':
    unittest.main()
