import math
import unittest

from calibration import fit_camera


class CameraFitTests(unittest.TestCase):
    def case(self):
        origin = [-121.05, 35.67, 989]
        points = []
        # Independent pinhole projection for a north-facing, level camera.
        for i, (east, north, up) in enumerate([(-3500, 12000, -500), (-2000, 14000, 200),
                (-500, 17000, -200), (1500, 12000, 500), (3500, 16000, -300),
                (4500, 19000, 350), (-1200, 11000, 150), (2700, 18000, -400)]):
            lon = origin[0] + math.degrees(east / (6371000 * math.cos(math.radians(origin[1]))))
            lat = origin[1] + math.degrees(north / 6371000)
            elevation = origin[2] + up + (east*east+north*north)/(2*6371000)
            points.append({'pixel': [427+800*east/north, 240-800*up/north],
                           'world': [lon, lat, elevation], 'role': 'fit' if i < 6 else 'check'})
        return {'origin': origin, 'width': 854, 'height': 480, 'points': points}

    def test_recovers_known_camera_and_checks_independent_landmarks(self):
        result = fit_camera(self.case())
        self.assertLess(result['fitRmsPx'], .01)
        self.assertLess(result['checkRmsPx'], .01)
        self.assertEqual(result['status'], 'fitted-unvalidated')
        self.assertAlmostEqual(result['horizontalFovDeg'], math.degrees(2*math.atan(854/1600)), places=3)

    def test_wrong_holdout_is_visible_in_error_without_changing_fit(self):
        data = self.case()
        data['points'][-1]['pixel'][0] += 50
        result = fit_camera(data)
        self.assertLess(result['fitRmsPx'], .01)
        self.assertGreater(result['checkRmsPx'], 30)

    def test_refuses_missing_independent_checks_and_invalid_coordinates(self):
        for mutation in ['no_checks', 'nan', 'few', 'clustered']:
            with self.subTest(mutation=mutation):
                data = self.case()
                if mutation == 'no_checks':
                    for p in data['points']: p['role'] = 'fit'
                elif mutation == 'nan': data['points'][0]['world'][0] = float('nan')
                elif mutation == 'few': data['points'] = data['points'][:5]
                else:
                    for p in data['points']: p['pixel'] = [400, 240]
                with self.assertRaises(ValueError): fit_camera(data)


if __name__ == '__main__':
    unittest.main()
