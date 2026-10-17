import copy
import math
import time
import unittest

import simulation

N = 41
CELL = 50


def make(elev=None, **over):
    data = {
        'origin': [-121.41472, 35.90356],
        'grid': {'origin': [-121.41472, 35.90356], 'cellSizeM': CELL,
                 'elevations': elev or [[500.0] * N for _ in range(N)]},
        'windFromDeg': 270, 'windSpeedMps': 0, 'baseSpreadMMin': 5, 'fuelFactor': 1, 'durationMin': 30,
    }
    data.update(over)
    return data


def arrivals(result):
    return {(f['properties']['row'], f['properties']['col']): f['properties']['arrivalMin'] for f in result['features']}


class SimulationTests(unittest.TestCase):
    def test_flat_calm_is_symmetric(self):
        a = arrivals(simulation.simulate(make(durationMin=60)))
        c = N // 2
        for k in (1, 2, 4):
            vals = [a[(c - k, c)], a[(c + k, c)], a[(c, c - k)], a[(c, c + k)]]
            self.assertLess(max(vals) - min(vals), 1e-9)
            diag = [a[(c + i * k, c + j * k)] for i in (-1, 1) for j in (-1, 1)]
            self.assertLess(max(diag) - min(diag), 1e-9)
        self.assertEqual(a[(c, c)], 0)
        self.assertAlmostEqual(a[(c, c + 2)], 2 * CELL / 5, places=2)

    def test_downwind_reaches_farther_than_upwind(self):
        result = simulation.simulate(make(windSpeedMps=10, windFromDeg=270, durationMin=60))  # wind from west, blows east
        a = arrivals(result)
        c = N // 2
        east = max(col for (r, col) in a if r == c) - c
        west = c - min(col for (r, col) in a if r == c)
        self.assertGreater(east, west)
        self.assertLess(a[(c, c + 3)], a[(c, c - 3)])

    def test_wind_direction_is_meteorological_from(self):
        a = arrivals(simulation.simulate(make(windSpeedMps=10, windFromDeg=0, durationMin=60)))  # from north, blows south
        c = N // 2
        self.assertLess(a[(c + 3, c)], a[(c - 3, c)])

    def test_uphill_is_faster(self):
        elev = [[500.0 + 0.3 * (col - N // 2) * CELL for col in range(N)] for _ in range(N)]  # rises eastwards
        a = arrivals(simulation.simulate(make(elev=elev, durationMin=60)))
        c = N // 2
        self.assertLess(a[(c, c + 2)], a[(c, c - 2)])

    def test_nothing_after_horizon(self):
        for duration in (1, 10, 60):
            result = simulation.simulate(make(durationMin=duration, windSpeedMps=15))
            self.assertTrue(result['features'])
            self.assertLessEqual(max(f['properties']['arrivalMin'] for f in result['features']), duration)
        self.assertLess(len(simulation.simulate(make(durationMin=1))['features']), 30)

    def test_output_contract_and_geometry(self):
        result = simulation.simulate(make(terrain={'terrainSource': 'AWS Terrarium', 'terrainStatus': 'real-dem', 'x': 'ignored'}))
        p = result['properties']
        self.assertEqual(result['type'], 'FeatureCollection')
        self.assertEqual((p['mode'], p['validated']), ('illustrative-scenario', False))
        self.assertTrue(p['assumptions'] and p['limitations'])
        self.assertEqual(set(p['terrain']), {'terrainSource', 'terrainStatus'})
        seed = next(f for f in result['features'] if f['properties']['arrivalMin'] == 0)
        ring = seed['geometry']['coordinates'][0]
        self.assertEqual(ring[0], ring[-1])
        lons, lats = [q[0] for q in ring], [q[1] for q in ring]
        self.assertTrue(min(lons) < -121.41472 < max(lons) and min(lats) < 35.90356 < max(lats))
        self.assertAlmostEqual((max(lats) - min(lats)) * simulation.M_PER_DEG_LAT, CELL, places=3)

    def test_deterministic(self):
        d = make(windSpeedMps=7)
        self.assertEqual(simulation.simulate(d), simulation.simulate(copy.deepcopy(d)))

    def test_extreme_valid_slope_is_clamped_without_overflow(self):
        elev = [[0.0] * N for _ in range(N)]
        elev[N // 2][N // 2 + 1] = 9000
        data = make(elev=elev, durationMin=60)
        data['grid']['cellSizeM'] = 10
        result = simulation.simulate(data)
        self.assertTrue(result['features'])
        self.assertTrue(all(math.isfinite(f['properties']['arrivalMin']) for f in result['features']))

    def test_rejects_broken_data(self):
        def bad(mutate):
            d = make()
            mutate(d)
            with self.assertRaises(ValueError):
                simulation.simulate(d)
        bad(lambda d: d['grid']['elevations'][3].__setitem__(5, None))
        bad(lambda d: d['grid']['elevations'][3].__setitem__(5, float('nan')))
        bad(lambda d: d['grid']['elevations'][3].__setitem__(5, float('inf')))
        bad(lambda d: d['grid']['elevations'][3].__setitem__(5, '500'))
        bad(lambda d: d['grid']['elevations'][3].__setitem__(5, True))
        bad(lambda d: d['grid']['elevations'].pop())
        bad(lambda d: d['grid']['elevations'][0].pop())
        bad(lambda d: d['grid'].__setitem__('elevations', [[0.0] * 40 for _ in range(40)]))
        bad(lambda d: d['grid'].__setitem__('elevations', [[0.0] * 63 for _ in range(63)]))
        bad(lambda d: d['grid'].__setitem__('elevations', [[0.0] * 19 for _ in range(19)]))
        bad(lambda d: d['grid'].__setitem__('origin', [-121.0, 35.9]))
        bad(lambda d: d['grid'].__setitem__('cellSizeM', 0))
        bad(lambda d: d.pop('grid'))
        bad(lambda d: d.__setitem__('origin', [200, 0]))
        bad(lambda d: d.__setitem__('windFromDeg', 361))
        bad(lambda d: d.__setitem__('windSpeedMps', -1))
        bad(lambda d: d.__setitem__('windSpeedMps', 31))
        bad(lambda d: d.__setitem__('baseSpreadMMin', 0))
        bad(lambda d: d.__setitem__('fuelFactor', 3))
        bad(lambda d: d.__setitem__('durationMin', 61))
        bad(lambda d: d.__setitem__('durationMin', float('nan')))
        with self.assertRaises(ValueError):
            simulation.simulate(None)

    def test_worst_case_is_bounded(self):
        n = 61
        elev = [[500.0 + 40 * math.sin(r / 3) * math.cos(c / 3) for c in range(n)] for r in range(n)]
        d = make(elev=elev, windSpeedMps=30, baseSpreadMMin=30, fuelFactor=2, durationMin=60)
        d['grid']['elevations'] = elev
        start = time.perf_counter()
        result = simulation.simulate(d)
        self.assertLess(time.perf_counter() - start, 3)
        self.assertLessEqual(len(result['features']), n * n)
        self.assertTrue(result['properties']['boundaryReached'])


if __name__ == '__main__':
    unittest.main()
