import copy
import json
import math
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import reconstruction_forecast as rf
import simulation

HERE = Path(__file__).resolve().parent
T_REAL = '2025-08-27T23:00:00Z'
REAL = None


def setUpModule():
    global REAL
    rf.reset_caches()
    REAL = rf.load_sources()


def epoch(text):
    return int(datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp())


def octile_minutes(dx, dy, cell=200.0, rate=4.0):
    """Closed-form 8-neighbour travel time on flat, calm, uniform fuel."""
    lo, hi = sorted((abs(dx), abs(dy)))
    return ((hi - lo) * cell + lo * cell * math.sqrt(2)) / rate


def flat_sources(n=41, last_extra_h=30, center_t=-100, ring_t=3 * 3600, wind=(270, 0.0)):
    """Synthetic grid (flat DEM allowed only in tests): 3x3 initial block, 7x7 'reference' block at +3 h, far cell at +30 h."""
    t0 = 3600 * 472222  # an exact UTC hour
    c = n // 2
    t_grid = np.full((n, n), np.inf)
    t_grid[c - 3:c + 4, c - 3:c + 4] = t0 + ring_t
    t_grid[c - 1:c + 2, c - 1:c + 2] = t0 + center_t
    t_grid[0, 0] = t0 + last_extra_h * 3600
    footprint = np.isfinite(t_grid)
    weather = {t0 - 3600 + 3600 * i: {'timeUtc': rf._iso(t0 - 3600 + 3600 * i), 'windFromDeg': wind[0], 'windSpeedMps': wind[1],
                                      'gustMps': 5.0, 'rhPct': 40, 'tempC': 20.0} for i in range(0, 60)}
    grid = {'cellM': 200.0, 'nx': n, 'ny': n, 'x0': -4000.0, 'y0': 4000.0, 'lat0': 36.95, 'lon0': -119.05,
            'mPerDegLat': 111320.0, 'mPerDegLon': 88962.534}
    meta = {'status': 'test', 'source': 'synthetic', 'point': {}, 'firstUtc': rf._iso(min(weather)), 'lastUtc': rf._iso(max(weather))}
    dem_hashes = {'npzSha256': 'x', 'receiptSha256': 'y', 'tilesDigestSha256': 'z', 'tileCount': 0, 'source': 'synthetic',
                  'resampling': 'none', 'stats': {}}
    src = rf.Sources(np.full((n, n), 1000.0), grid, dem_hashes, t_grid, footprint, 'a', weather, 'w', meta, {})
    return src, t0


def synth(src, t0, hours=6, offset_s=0):
    return rf.forecast({'timeUtc': rf._iso(t0 + offset_s), 'horizonHours': hours}, sources=src)


def roles(result):
    return {f['properties']['role']: f for f in result['features']}


class PropagationTests(unittest.TestCase):
    def test_front_starts_at_every_cell_of_the_mask_not_a_single_seed(self):
        n = 41
        mask = np.zeros((n, n), bool)
        mask[15:26, 10:31] = True  # wide multi-cell block
        arrival = rf.propagate(np.full((n, n), 500.0), 200.0, mask, [(0, 0.0)] * 24, 0.0, 600.0)
        self.assertTrue((arrival[mask] == 0).all())
        for r, c in [(14, 10), (14, 30), (26, 20), (20, 9), (20, 31)]:  # next to opposite ends of the block
            self.assertAlmostEqual(arrival[r, c], 50.0, places=9)
        self.assertAlmostEqual(arrival[14, 9], 200 * math.sqrt(2) / 4, places=9)
        # a single-seed model centred on the block would need 10+ cells (>500 min) to reach those edges
        centre = (20, 20)
        self.assertGreater(octile_minutes(10, 0), 400)
        self.assertEqual(arrival[centre], 0)

    def test_matches_closed_form_octile_distance_from_a_multicell_mask(self):
        n = 31
        mask = np.zeros((n, n), bool)
        mask[12:15, 10:12] = True
        mask[18, 20] = True
        arrival = rf.propagate(np.full((n, n), 0.0), 200.0, mask, [(0, 0.0)] * 24, 0.0, 24 * 60.0)
        src_cells = np.argwhere(mask)
        for r, c in [(0, 0), (30, 30), (14, 25), (25, 5), (20, 21)]:
            expected = min(octile_minutes(c - sc, r - sr) for sr, sc in src_cells)
            self.assertAlmostEqual(arrival[r, c], expected, places=7)

    def test_wind_direction_changes_geometry(self):
        n = 61
        mask = np.zeros((n, n), bool)
        mask[28:33, 28:33] = True
        flat = np.full((n, n), 300.0)
        hours, horizon = 60, 3000.0  # long enough that every cell is reached, so no cut-off rounding at the horizon
        west = rf.propagate(flat, 200.0, mask, [(270, 10.0)] * hours, 0.0, horizon)  # wind FROM west: spreads east
        east = rf.propagate(flat, 200.0, mask, [(90, 10.0)] * hours, 0.0, horizon)
        calm = rf.propagate(flat, 200.0, mask, [(270, 0.0)] * hours, 0.0, horizon)
        self.assertLess(west[30, 40], calm[30, 40])  # downwind faster
        self.assertGreater(west[30, 20], calm[30, 20])  # upwind slower
        np.testing.assert_allclose(west, east[:, ::-1], atol=1e-9)  # mirror symmetry, so no hidden bias
        self.assertFalse(np.allclose(west, east))
        expected = 200 / (4.0 * math.exp(simulation.KW * 10.0))
        self.assertAlmostEqual(west[30, 33], expected, places=9)

    def test_meteorological_from_convention_adds_180(self):
        w = rf.wind_factors(0, 10.0, 200.0)  # wind from north blows towards south
        dirs = rf._DIRECTIONS
        south = w[dirs.index((1, 0))]
        north = w[dirs.index((-1, 0))]
        self.assertAlmostEqual(south, math.exp(simulation.KW * 10.0))
        self.assertAlmostEqual(north, math.exp(-simulation.KW * 10.0))

    def test_slope_changes_geometry_without_wind(self):
        n = 41
        mask = np.zeros((n, n), bool)
        mask[20, 20] = True
        rows = np.arange(n, dtype=float)[:, None]
        tilted = np.repeat(rows * -50.0, n, axis=1)  # row index grows south, elevation falls to the south => uphill is north
        a = rf.propagate(tilted, 200.0, mask, [(0, 0.0)] * 24, 0.0, 800.0)
        up, down = a[19, 20], a[21, 20]
        dz = 50.0
        self.assertAlmostEqual(up, 200 / (4.0 * min(simulation.S_MAX, math.exp(simulation.KS * dz / 200))), places=9)
        self.assertAlmostEqual(down, 200 / (4.0 * max(simulation.S_MIN, math.exp(-simulation.KS * dz / 200))), places=9)
        self.assertLess(up, down)
        self.assertAlmostEqual(a[20, 19], a[20, 21], places=9)

    def test_hour_boundaries_are_integrated_fifo(self):
        mask = np.zeros((3, 4), bool)
        mask[:, 0] = True
        hours = [(270, 0.0), (270, 10.0)]  # wind from west: eastward step is downwind
        phase = 50.0
        arrival = rf.propagate(np.full((3, 4), 100.0), 200.0, mask, hours, phase, 60.0)
        rate1, rate2 = 4.0, 4.0 * math.exp(simulation.KW * 10.0)
        expected = 10.0 + (200 - 10.0 * rate1) / rate2
        self.assertAlmostEqual(arrival[1, 1], expected, places=9)
        # starting later never finishes earlier (FIFO)
        later = rf.propagate(np.full((3, 4), 100.0), 200.0, mask, hours, 55.0, 60.0)
        self.assertGreaterEqual(later[1, 1] + 5.0, arrival[1, 1])
        # a constant-wind run in the second hour only is faster than the first-hour-then-second one
        fast = rf.propagate(np.full((3, 4), 100.0), 200.0, mask, [(270, 10.0)] * 2, phase, 60.0)
        self.assertLess(fast[1, 1], arrival[1, 1])

    def test_shorter_horizon_is_prefix_of_longer_horizon(self):
        n = 31
        mask = np.zeros((n, n), bool)
        mask[14:17, 14:17] = True
        elev = np.add.outer(np.sin(np.arange(n) / 4.0) * 80, np.cos(np.arange(n) / 5.0) * 60) + 800
        hourly = [(200 + 17 * h % 360, 2.0 + h % 5) for h in range(30)]
        long_run = rf.propagate(elev, 200.0, mask, hourly, 20.0, 24 * 60.0)
        for h in (6, 12):
            short = rf.propagate(elev, 200.0, mask, hourly, 20.0, h * 60.0)
            both = np.isfinite(short)
            np.testing.assert_allclose(short[both], long_run[both], atol=1e-9)
            self.assertTrue(((long_run <= h * 60.0) == np.isfinite(short)).all())

    def test_rejects_empty_mask_and_missing_wind(self):
        elev = np.full((10, 10), 10.0)
        with self.assertRaises(ValueError):
            rf.propagate(elev, 200.0, np.zeros((10, 10), bool), [(0, 1.0)] * 8, 0.0, 60.0)
        mask = np.zeros((10, 10), bool)
        mask[5, 5] = True
        with self.assertRaises(ValueError):
            rf.propagate(elev, 200.0, mask, [(0, 1.0)], 0.0, 120.0)
        with self.assertRaises(ValueError):
            rf.propagate(np.where(mask, np.nan, 1.0), 200.0, mask, [(0, 1.0)] * 8, 0.0, 60.0)


class MetricTests(unittest.TestCase):
    @staticmethod
    def masks(initial, predicted, reference, shape=(10, 10)):
        out = []
        for cells in (initial, predicted, reference):
            m = np.zeros(shape, bool)
            for r, c in cells:
                m[r, c] = True
            out.append(m)
        return out

    def test_known_intersection_excess_and_deficit(self):
        initial = [(0, 0), (0, 1)]
        predicted = initial + [(1, 0), (1, 1), (1, 2)]
        reference = initial + [(1, 0), (2, 0)]
        m = rf.compare(*self.masks(initial, predicted, reference), cell_ha=4.0)
        self.assertEqual(m['intersectionHa'], 3 * 4.0)
        self.assertEqual(m['overpredictionHa'], 2 * 4.0)
        self.assertEqual(m['underpredictionHa'], 1 * 4.0)
        self.assertEqual(m['predictedHa'], 5 * 4.0)
        self.assertEqual(m['referenceHa'], 4 * 4.0)
        self.assertEqual(m['initialHa'], 2 * 4.0)
        self.assertAlmostEqual(m['iou'], 3 / 6, places=4)
        self.assertAlmostEqual(m['growthIou'], 1 / 4, places=4)  # growth sets: {(1,0),(1,1),(1,2)} vs {(1,0),(2,0)}

    def test_total_iou_is_dominated_by_the_initial_mask_but_growth_iou_is_not(self):
        shape = (20, 20)
        init = [(r, c) for r in range(10) for c in range(10)]
        predicted = init + [(15, c) for c in range(10)]
        reference = init + [(17, c) for c in range(10)]
        m = rf.compare(*self.masks(init, predicted, reference, shape), cell_ha=4.0)
        self.assertGreater(m['iou'], 0.8)  # 100 / 120
        self.assertEqual(m['growthIou'], 0.0)

    def test_growth_iou_undefined_without_growth(self):
        init = [(0, 0), (0, 1)]
        m = rf.compare(*self.masks(init, init, init), cell_ha=4.0)
        self.assertEqual(m['iou'], 1.0)
        self.assertIsNone(m['growthIou'])
        self.assertTrue(m['growthIouReason'])


class GeometryTests(unittest.TestCase):
    def test_hole_and_disjoint_parts_keep_area(self):
        grid = REAL.grid
        mask = np.zeros((20, 20), bool)
        mask[2:9, 2:9] = True
        mask[5, 5] = False  # hole
        mask[12:14, 12:15] = True
        geom = rf.mask_geometry(mask, grid)
        self.assertEqual(geom['type'], 'MultiPolygon')
        from shapely.geometry import shape
        poly = shape(geom)
        expected = (mask.sum()) * 200.0 * 200.0
        approx = poly.area * grid['mPerDegLat'] * grid['mPerDegLon']
        self.assertAlmostEqual(approx / expected, 1.0, places=3)
        self.assertEqual(sorted(len(rings) for rings in geom['coordinates']), [1, 2])  # one part with a hole, one without

    def test_empty_mask_is_empty_multipolygon(self):
        self.assertEqual(rf.mask_geometry(np.zeros((3, 3), bool), REAL.grid), {'type': 'MultiPolygon', 'coordinates': []})


class SyntheticForecastTests(unittest.TestCase):
    def test_predicted_extent_matches_closed_form_and_invariants(self):
        src, t0 = flat_sources()
        result = synth(src, t0, 6, offset_s=0)
        p, rs = result['properties'], roles(result)
        yy, xx = np.mgrid[0:41, 0:41]
        init = (src.t_grid <= t0)
        sr, sc = np.nonzero(init)
        dist = np.min([[octile_minutes(x - cc, y - rr) for x, y in zip(xx.ravel(), yy.ravel())] for rr, cc in zip(sr, sc)], axis=0)
        expected = int((dist <= 360).sum())
        self.assertEqual(rs['modeled-extent']['properties']['cellCount'], expected)
        self.assertEqual(rs['initial-extent']['properties']['cellCount'], 9)  # several cells, not one seed
        m = p['metrics']
        self.assertAlmostEqual(m['intersectionHa'] + m['overpredictionHa'], m['predictedHa'])
        self.assertAlmostEqual(m['intersectionHa'] + m['underpredictionHa'], m['referenceHa'])
        self.assertAlmostEqual(m['iou'], m['intersectionHa'] / (m['intersectionHa'] + m['overpredictionHa'] + m['underpredictionHa']), places=4)
        self.assertEqual(m['underpredictionHa'], 0.0)  # the 7x7 block is inside the reached octagon
        self.assertGreater(m['overpredictionHa'], 0)
        self.assertEqual(rs['overprediction']['properties']['areaHa'], m['overpredictionHa'])
        self.assertEqual(m['referenceHa'], 49 * 4.0 + 0.0)
        self.assertFalse(p['domainBoundaryReached'])

    def test_contract_shape(self):
        src, t0 = flat_sources()
        r = synth(src, t0, 6)
        self.assertEqual(r['type'], 'FeatureCollection')
        p = r['properties']
        self.assertEqual(p['mode'], 'retrospective-forecast')
        self.assertIs(p['validated'], False)
        for key in ('timeUtc', 'validUtc', 'horizonHours', 'referenceAvailable', 'domainBoundaryReached', 'metrics', 'weather',
                    'assumptions', 'limitations', 'provenance'):
            self.assertIn(key, p)
        for key in ('iou', 'growthIou', 'intersectionHa', 'overpredictionHa', 'underpredictionHa', 'predictedHa', 'referenceHa', 'initialHa'):
            self.assertIn(key, p['metrics'])
        self.assertEqual(set(roles(r)), {'initial-extent', 'modeled-extent', 'reference-extent', 'overlap', 'overprediction', 'underprediction'})
        classes = {k: f['properties']['dataClass'] for k, f in roles(r).items()}
        self.assertEqual(classes, {'initial-extent': 'reconstructed', 'modeled-extent': 'modeled', 'reference-extent': 'reconstructed',
                                   'overlap': 'modeled-comparison', 'overprediction': 'modeled-comparison', 'underprediction': 'modeled-comparison'})
        for key in ('windFromDeg', 'windSpeedMps', 'rhPct', 'tempC', 'timeUtc'):
            self.assertIn(key, p['weather'])
        for key in ('demSha256', 'arrivalSha256', 'weatherSha256', 'grid', 'method', 'fuelStatus'):
            self.assertIn(key, p['provenance'])
        self.assertEqual(p['validUtc'], rf._iso(t0 + 6 * 3600))

    def test_no_reference_beyond_the_reconstruction(self):
        src, t0 = flat_sources(last_extra_h=2)  # reconstruction ends 2 h after t0
        r = synth(src, t0, 6)
        p = r['properties']
        self.assertFalse(p['referenceAvailable'])
        for key in ('iou', 'growthIou', 'intersectionHa', 'overpredictionHa', 'underpredictionHa', 'referenceHa'):
            self.assertIsNone(p['metrics'][key])
        self.assertGreater(p['metrics']['predictedHa'], p['metrics']['initialHa'])  # the forecast still exists, not a frozen fire
        self.assertEqual(set(roles(r)), {'initial-extent', 'modeled-extent'})
        self.assertIn('growthIouReason', p['metrics'])

    def test_forecast_is_not_clipped_to_final_footprint(self):
        src, t0 = flat_sources()
        r = synth(src, t0, 24)
        p = r['properties']
        outside = p['diagnostics']['modeledOutsideFinalFootprintHa']
        self.assertGreater(outside, 0)
        self.assertGreater(p['metrics']['predictedHa'], p['diagnostics']['finalFootprintHa'])
        self.assertGreaterEqual(p['metrics']['overpredictionHa'], outside)  # counted as overprediction, never hidden

    def test_domain_exhaustion_is_flagged_not_contained(self):
        src, t0 = flat_sources(n=21)
        r = synth(src, t0, 24)
        p = r['properties']
        self.assertTrue(p['domainBoundaryReached'])
        self.assertEqual(roles(r)['modeled-extent']['properties']['cellCount'], 21 * 21)  # fills the domain; no invented containment
        self.assertIsNotNone(p['metrics']['iou'])
        self.assertFalse(synth(flat_sources(n=61)[0], t0, 6)['properties']['domainBoundaryReached'])

    def test_horizons_nest_with_same_conditions(self):
        src, t0 = flat_sources(n=81, wind=(250, 3.0))
        counts = [roles(synth(src, t0, h))['modeled-extent']['properties']['cellCount'] for h in (6, 12, 24)]
        self.assertLess(counts[0], counts[1])
        self.assertLess(counts[1], counts[2])
        from shapely.geometry import shape
        small, mid, big = (shape(roles(synth(src, t0, h))['modeled-extent']['geometry']) for h in (6, 12, 24))
        self.assertLess(small.difference(mid).area, 1e-12)
        self.assertLess(mid.difference(big).area, 1e-12)

    def test_input_validation(self):
        src, t0 = flat_sources()
        iso = rf._iso(t0)
        bad = [None, [], 'x', {}, {'timeUtc': iso}, {'horizonHours': 6},
               {'timeUtc': '2025-08-27T23:00:00', 'horizonHours': 6},
               {'timeUtc': 'ayer', 'horizonHours': 6}, {'timeUtc': 123, 'horizonHours': 6},
               {'timeUtc': iso, 'horizonHours': 7}, {'timeUtc': iso, 'horizonHours': True}, {'timeUtc': iso, 'horizonHours': '6'},
               {'timeUtc': iso, 'horizonHours': None}, {'timeUtc': iso, 'horizonHours': float('nan')}, {'timeUtc': 'x' * 500, 'horizonHours': 6}]
        for data in bad:
            with self.assertRaises(ValueError, msg=repr(data)):
                rf.forecast(data, sources=src)
        # offsets are converted, not rejected
        a = rf.forecast({'timeUtc': rf._iso(t0).replace('Z', '+00:00'), 'horizonHours': 6}, sources=src)
        local = datetime.fromtimestamp(t0, timezone.utc).astimezone(timezone(__import__('datetime').timedelta(hours=-7))).isoformat()
        b = rf.forecast({'timeUtc': local, 'horizonHours': 6}, sources=src)
        self.assertEqual(a['properties']['timeUtc'], b['properties']['timeUtc'])

    def test_empty_initial_area_is_a_clear_error_without_fake_seed(self):
        src, t0 = flat_sources()
        with self.assertRaises(ValueError) as ctx:
            synth(src, t0, 6, offset_s=-10 * 3600)
        self.assertIn('área inicial', str(ctx.exception))

    def test_horizon_beyond_weather_archive_is_a_clear_error(self):
        src, t0 = flat_sources()
        last = max(src.weather)
        with self.assertRaises(ValueError) as ctx:
            rf.forecast({'timeUtc': rf._iso(last - 3 * 3600), 'horizonHours': 12}, sources=src)
        self.assertIn('meteorología', str(ctx.exception).lower())

    def test_cached_output_is_never_shared(self):
        src, t0 = flat_sources()
        a = synth(src, t0, 6)
        a['properties']['metrics']['iou'] = -1
        a['features'].clear()
        b = synth(src, t0, 6)
        self.assertNotEqual(b['properties']['metrics']['iou'], -1)
        self.assertEqual(len(b['features']), 6)


class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {h: rf.forecast({'timeUtc': T_REAL, 'horizonHours': h}) for h in (6, 12, 24)}

    def test_sources_are_the_pinned_real_ones(self):
        self.assertEqual(int(REAL.footprint.sum()), 6073)
        self.assertEqual(REAL.dem_hashes['npzSha256'], json.loads((HERE / 'forecast_data' / 'source-receipt.json').read_text())['dem']['sha256'])
        self.assertEqual(REAL.dem.shape, (REAL.grid['ny'], REAL.grid['nx']))
        self.assertGreater(float(REAL.dem.std()), 100)  # real relief, not flat
        self.assertEqual(REAL.arrival_sha, '726dddb723f8ef11ef445626ce50c0f3ab6a52f5e0a08d8c95caf937f59680cc')

    def test_extended_dem_reproduces_the_base_dem_exactly(self):
        data = HERE / 'forecast_data'
        base_receipt = json.loads((data / 'dem-receipt.json').read_text())['grid']
        base = np.load(data / 'dem-200m.npz')['elevation'].astype(float)
        g = REAL.grid
        c0, r0 = round((base_receipt['x0'] - g['x0']) / 200), round((g['y0'] - base_receipt['y0']) / 200)
        np.testing.assert_array_equal(REAL.dem[r0:r0 + base.shape[0], c0:c0 + base.shape[1]], base)
        self.assertGreaterEqual(min(r0, c0, g['ny'] - r0 - base.shape[0], g['nx'] - c0 - base.shape[1]), 0)

    def test_dem_tiles_match_receipt_when_cache_is_present(self):
        receipt = json.loads((HERE / 'forecast_data' / 'dem-extended-receipt.json').read_text())
        import hashlib
        checked = 0
        for tile in receipt['tiles']:
            name = tile['url'].rsplit('/', 3)[-3:]
            fname = '12_%s_%s' % (name[1], name[2])
            for d in (HERE / 'camera_assimilation' / 'assimilation' / 'dem' / 'tiles', HERE / 'forecast_data' / 'tiles-extra'):
                if (d / fname).is_file():
                    self.assertEqual(hashlib.sha256((d / fname).read_bytes()).hexdigest(), tile['sha256'])
                    checked += 1
                    break
        if checked < len(receipt['tiles']):
            self.skipTest('base tile cache not present')

    def test_starts_from_the_reconstructed_mask(self):
        t0 = epoch(T_REAL)
        expected = int((REAL.t_grid <= t0).sum())
        for h, r in self.results.items():
            rs = roles(r)
            self.assertEqual(rs['initial-extent']['properties']['cellCount'], expected)
            self.assertGreater(expected, 1000)
            self.assertGreater(rs['modeled-extent']['properties']['cellCount'], expected)
            self.assertEqual(r['properties']['metrics']['initialHa'], expected * 4.0)
            self.assertEqual(r['properties']['horizonHours'], h)

    def test_real_run_reports_total_and_growth_iou_and_boundary(self):
        for r in self.results.values():
            p = r['properties']
            self.assertTrue(p['referenceAvailable'])
            self.assertFalse(p['validated'])
            self.assertIsInstance(p['metrics']['growthIou'], float)
            self.assertIsInstance(p['domainBoundaryReached'], bool)
            self.assertLessEqual(p['metrics']['growthIou'], p['metrics']['iou'])  # the initial mask inflates total IoU
            self.assertTrue(any('borde' in text.lower() and 'reaviva' in text.lower() for text in p['limitations']))
        self.assertFalse(self.results[24]['properties']['domainBoundaryReached'])  # extended DEM has room at 24 h

    def test_real_horizons_nest(self):
        areas = [self.results[h]['properties']['metrics']['predictedHa'] for h in (6, 12, 24)]
        self.assertLessEqual(areas[0], areas[1])
        self.assertLessEqual(areas[1], areas[2])
        t0 = epoch(T_REAL)
        arrival = rf._field(REAL, t0)['arrival']
        self.assertTrue(((arrival <= 360) <= (arrival <= 720)).all() and ((arrival <= 720) <= (arrival <= 1440)).all())

    def test_hourly_weather_is_used_and_labelled_as_model(self):
        p = self.results[6]['properties']
        w = p['weather']
        raw = {h['timeUtc']: h for h in json.loads((HERE / 'evidence/garnet/satellite/weather-hourly.json').read_text())['hours']}
        self.assertEqual(w['timeUtc'], T_REAL)
        self.assertEqual(w['windFromDeg'], raw[T_REAL]['windFromDeg'])
        self.assertEqual(w['windToDeg'], (raw[T_REAL]['windFromDeg'] + 180) % 360)
        self.assertEqual([h['timeUtc'] for h in w['hourly']][:3], ['2025-08-27T23:00:00Z', '2025-08-28T00:00:00Z', '2025-08-28T01:00:00Z'])
        self.assertEqual(len(w['hourly']), 6)
        self.assertEqual(len(self.results[24]['properties']['weather']['hourly']), 24)
        self.assertEqual(w['dataClass'], 'model-single-point')
        self.assertTrue(any('un solo punto' in text.lower() for text in p['limitations']))

    def test_real_wind_and_slope_change_the_real_geometry(self):
        t0 = epoch(T_REAL)
        mask = REAL.t_grid <= t0
        base_args = (200.0, mask)
        hours = 24
        wind_w = rf.propagate(REAL.dem, *base_args, [(270, 8.0)] * hours, 0.0, 720.0)
        wind_e = rf.propagate(REAL.dem, *base_args, [(90, 8.0)] * hours, 0.0, 720.0)
        calm = rf.propagate(REAL.dem, *base_args, [(270, 0.0)] * hours, 0.0, 720.0)
        flat = rf.propagate(np.full_like(REAL.dem, 1500.0), *base_args, [(270, 0.0)] * hours, 0.0, 720.0)
        rows, cols = np.nonzero(mask)
        east_edge = cols.max()
        self.assertFalse(np.array_equal(np.isfinite(wind_w), np.isfinite(wind_e)))
        reach = lambda a: int(np.isfinite(a)[:, east_edge + 1:].sum())
        self.assertGreater(reach(wind_w), reach(wind_e))  # real downwind advantage on the real relief
        self.assertFalse(np.array_equal(np.isfinite(calm), np.isfinite(flat)))  # relief alone changes the footprint

    def test_before_first_detection_and_after_archive(self):
        with self.assertRaises(ValueError) as ctx:
            rf.forecast({'timeUtc': '2025-08-24T09:00:00Z', 'horizonHours': 6})
        self.assertIn('área inicial', str(ctx.exception))
        with self.assertRaises(ValueError):
            rf.forecast({'timeUtc': '2025-09-13T20:00:00Z', 'horizonHours': 24})  # weather ends 2025-09-13T23:00Z

    def test_no_reference_after_the_last_reconstructed_arrival(self):
        r = rf.forecast({'timeUtc': '2025-09-12T00:00:00Z', 'horizonHours': 24})
        p = r['properties']
        self.assertFalse(p['referenceAvailable'])
        self.assertIsNone(p['metrics']['iou'])
        self.assertGreater(p['metrics']['predictedHa'], p['metrics']['initialHa'])
        self.assertNotIn('reference-extent', roles(r))
        late = rf.forecast({'timeUtc': '2025-09-12T00:00:00Z', 'horizonHours': 6})['properties']  # 06:00Z is still inside the reconstruction
        self.assertTrue(late['referenceAvailable'])

    def test_response_is_small_and_fast_enough_for_web(self):
        rf.reset_caches()
        started = time.time()
        r = rf.forecast({'timeUtc': '2025-08-27T20:00:00Z', 'horizonHours': 24})
        self.assertLess(time.time() - started, 15)
        self.assertLess(len(json.dumps(r)), 3_000_000)
        self.assertLess(sum(len(f['geometry']['coordinates']) for f in r['features']), 400)
        started = time.time()
        rf.forecast({'timeUtc': '2025-08-27T20:00:00Z', 'horizonHours': 6})  # cached field, other horizon
        self.assertLess(time.time() - started, 5)
        rf.reset_caches()


class SourceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        sat = HERE / 'evidence' / 'garnet' / 'satellite'
        self.arrival, self.weather = self.tmp / 'arrival.geojson', self.tmp / 'weather.json'
        shutil.copy(sat / 'arrival-reconstructed.geojson', self.arrival)
        shutil.copy(sat / 'weather-hourly.json', self.weather)
        self.data = self.tmp / 'data'
        self.data.mkdir()
        for name in ('dem-extended-200m.npz', 'dem-extended-receipt.json', 'source-receipt.json'):
            shutil.copy(HERE / 'forecast_data' / name, self.data / name)

    def load(self):
        return rf.load_sources(self.arrival, self.weather, self.data)

    def test_untouched_copies_load(self):
        self.assertEqual(int(self.load().footprint.sum()), 6073)

    def test_modified_arrival_weather_or_dem_fail(self):
        for path in (self.arrival, self.weather, self.data / 'dem-extended-200m.npz', self.data / 'dem-extended-receipt.json'):
            raw = bytearray(path.read_bytes())
            raw[len(raw) // 2] ^= 0x01
            path.write_bytes(bytes(raw))
            with self.assertRaises(rf.ForecastDataError, msg=path.name):
                self.load()
            raw[len(raw) // 2] ^= 0x01
            path.write_bytes(bytes(raw))
        self.load()

    def test_missing_dem_has_no_flat_fallback(self):
        (self.data / 'dem-extended-200m.npz').unlink()
        with self.assertRaises(rf.ForecastDataError):
            self.load()

    def test_receipt_that_does_not_describe_the_dem_is_rejected(self):
        receipt = json.loads((self.data / 'source-receipt.json').read_text())
        other = json.loads((HERE / 'forecast_data' / 'dem-receipt.json').read_text())
        import hashlib
        (self.data / 'dem-extended-receipt.json').write_text(json.dumps(other))
        receipt['demReceipt']['sha256'] = hashlib.sha256((self.data / 'dem-extended-receipt.json').read_bytes()).hexdigest()
        (self.data / 'source-receipt.json').write_text(json.dumps(receipt))
        with self.assertRaises(rf.ForecastDataError):
            self.load()


if __name__ == '__main__':
    unittest.main()
