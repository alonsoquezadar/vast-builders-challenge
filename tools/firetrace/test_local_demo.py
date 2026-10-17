import base64
import hashlib
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import main
from demo_bundle import load_bundle


class LocalDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_bundle(Path(__file__).with_name('demo-data.json'))
        cls.replay = patch.object(main, 'REPLAY', cls.bundle)
        cls.network = patch.object(main, 'remote', side_effect=AssertionError('Replay must not fetch upstream data'))
        cls.replay.start()
        cls.network.start()
        cls.server = main.ThreadingHTTPServer(('127.0.0.1', 0), main.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.network.stop()
        cls.replay.stop()

    def get(self, path):
        with urlopen(self.url + path, timeout=3) as response:
            return json.load(response)

    def test_replay_serves_saved_sources_without_upstream_network(self):
        for name in ['firms', 'cameras', 'perimeters']:
            data = self.get('/api/' + name)
            self.assertTrue(data['replay'])
            self.assertEqual(data['features'], self.bundle['sources'][name]['data']['features'])
            self.assertEqual(data['bundleCapturedAt'], self.bundle['capturedAt'])

    def test_example_analysis_matches_the_exact_source_image(self):
        for sample, name in [('gann', 'gann-official-thumbnail'), ('grizzly', 'grizzly-camera')]:
            data = self.get('/api/demo-observation?sample=' + sample)
            image = Path(__file__).with_name('evidence').joinpath(name + '.jpg').read_bytes()
            self.assertEqual(data['savedAnalysis']['imageSha256'], hashlib.sha256(image).hexdigest())
            self.assertEqual(data['savedAnalysis']['geolocation'], 'unresolved')

    def test_unknown_files_and_samples_are_not_exposed(self):
        for path in ['/main.py', '/evidence/grizzly-camera-source.json', '/api/demo-observation?sample=../../main']:
            with self.assertRaises(HTTPError) as error:
                self.get(path)
            self.assertEqual(error.exception.code, 404)

    def test_saved_mode_does_not_claim_live_data(self):
        data = self.get('/api/status')
        self.assertEqual(data['mode'], 'replay')
        self.assertEqual(data['replayCapturedAt'], self.bundle['capturedAt'])

    def test_alignment_assets_are_served_but_source_files_stay_private(self):
        for path, mime in [('/alignment.html', 'text/html'), ('/alignment.js', 'javascript'),
                           ('/evidence/plaskett/clip.mp4', 'video/mp4'),
                           ('/evidence/plaskett/frame-55.jpg', 'image/jpeg')]:
            with urlopen(self.url + path, timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(mime, response.headers['Content-Type'])
                response.read()
        for path in ['/calibration.py', '/evidence/plaskett/source.json']:
            with self.assertRaises(HTTPError) as error:
                self.get(path)
            self.assertEqual(error.exception.code, 404)

    def test_camera_fit_endpoint_requires_verified_correspondences(self):
        request = Request(self.url + '/api/calibrate', data=b'{}', headers={'Content-Type': 'application/json'})
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=3)
        self.assertEqual(error.exception.code, 400)

    def test_plaskett_analysis_is_bound_to_original_frame(self):
        data = self.get('/api/alignment-observation')
        frame = Path(__file__).with_name('evidence').joinpath('plaskett/frame-65.jpg').read_bytes()
        self.assertEqual(data['frameSecond'], 65)
        self.assertEqual(data['analysis']['imageSha256'], hashlib.sha256(frame).hexdigest())
        self.assertEqual(data['analysis']['geolocation'], 'unresolved')

    def test_incident_replay_is_available_without_upstream_network(self):
        data = self.get('/api/incident')
        self.assertEqual(data['mode'], 'historical-replay')
        self.assertEqual(len(data['frames']), 6)
        self.assertEqual(data['clockSynchronization'], 'unverified')
        self.assertIsNone(data['firmsHistoricalData'])
        self.assertTrue(all(frame['analysisIntegrity'] == 'matched' for frame in data['frames']))
        for path in ['/incident.html', '/incident.js', '/incident.css', '/incident_model.mjs',
                     '/evidence/garnet/delilah-86.jpg', '/evidence/garnet/buckrock-267.jpg']:
            with urlopen(self.url + path, timeout=3) as response:
                self.assertEqual(response.status, 200)
                response.read()
        with self.assertRaises(HTTPError) as error:
            self.get('/evidence/garnet/manifest.json')
        self.assertEqual(error.exception.code, 404)

    def test_scenario_uses_recorded_real_dem_and_rejects_invalid_seed(self):
        data = self.get('/api/scenario-terrain?lon=-119.027914&lat=36.86508')
        self.assertEqual(data['terrainStatus'], 'real-dem')
        self.assertEqual(data['terrainMode'], 'recorded')
        self.assertEqual(len(data['elevations']), 41)
        values = [v for row in data['elevations'] for v in row]
        self.assertGreater(max(values) - min(values), 100)
        for path in ['/api/scenario-terrain?lon=nan&lat=37', '/api/scenario-terrain?lon=0&lat=0']:
            with self.assertRaises(HTTPError) as error:
                self.get(path)
            self.assertEqual(error.exception.code, 400)

    def test_simulation_uses_server_dem_and_cannot_claim_client_supplied_terrain(self):
        payload = {'origin': [-119.027914, 36.86508], 'windFromDeg': 270, 'windSpeedMps': 6,
                   'baseSpreadMMin': 4, 'fuelFactor': 1, 'durationMin': 45,
                   'grid': {'origin': [0, 0], 'elevations': []},
                   'terrain': {'terrainSource': 'client-forged-source'}}
        request = Request(self.url + '/api/simulate', data=json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=3) as response:
            data = json.load(response)
        self.assertFalse(data['properties']['validated'])
        self.assertEqual(data['properties']['terrainSource'], 'AWS Terrarium')
        self.assertEqual(data['properties']['terrain']['terrainSource'], 'AWS Terrarium')
        self.assertEqual(data['properties']['terrainMode'], 'recorded')
        self.assertGreater(len(data['features']), 1)
        self.assertLessEqual(max(f['properties']['arrivalMin'] for f in data['features']), 45)

    def test_historical_weather_overrides_client_wind_and_remains_unvalidated(self):
        payload = {'origin': [-119.027914, 36.86508], 'windFromDeg': 0, 'windSpeedMps': 29,
                   'baseSpreadMMin': 4, 'fuelFactor': 1, 'durationMin': 45,
                   'weatherTimeUtc': '2025-08-28T01:00:00Z'}
        def post(body):
            request = Request(self.url + '/api/simulate', data=json.dumps(body).encode(),
                              headers={'Content-Type': 'application/json'})
            with urlopen(request, timeout=3) as response:
                return json.load(response)
        data = post(payload)['properties']
        weather = data['meteorology']
        self.assertEqual(weather['dataClass'], 'historical-weather-model')
        self.assertEqual(data['assumptions']['inputs']['windSpeedMps'], weather['windSpeedMps'])
        self.assertNotEqual(weather['windSpeedMps'], 29)
        self.assertFalse(data['validated'])
        for bad in [{'origin': [-121.41472, 35.90356]}, {'weatherTimeUtc': '2026-08-28T01:00:00Z'}]:
            with self.assertRaises(HTTPError) as error:
                post({**payload, **bad})
            self.assertEqual(error.exception.code, 400)
        self.assertNotIn('FIRMS_MAP_KEY', json.dumps(self.get('/api/satellite?layer=summary')))

    def test_simulation_page_is_served_without_exposing_python_source(self):
        for path in ['/simulation.html', '/simulation.js', '/simulation.css']:
            with urlopen(self.url + path, timeout=3) as response:
                self.assertEqual(response.status, 200)
                response.read()
        with self.assertRaises(HTTPError) as error:
            self.get('/simulation.py')
        self.assertEqual(error.exception.code, 404)

    def test_fusion_view_reports_experiment_and_keeps_sources_private(self):
        data = self.get('/api/camera-fusion')
        self.assertFalse(data['operationallyValidated'])
        self.assertEqual(data['mode'], 'retrospective-experiment')
        for path in ['/fusion.html', '/fusion.js', '/fusion.css']:
            with urlopen(self.url + path, timeout=3) as response:
                self.assertEqual(response.status, 200)
                response.read()
        with self.assertRaises(HTTPError) as error:
            self.get('/camera_bundle.py')
        self.assertEqual(error.exception.code, 404)

    def test_clip_supports_seeking_and_rejects_out_of_bounds_ranges(self):
        request = Request(self.url + '/evidence/plaskett/clip.mp4', headers={'Range': 'bytes=100-199'})
        clip = Path(__file__).with_name('evidence').joinpath('plaskett/clip.mp4').read_bytes()
        with urlopen(request, timeout=3) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), clip[100:200])
            self.assertEqual(response.headers['Content-Range'], f'bytes 100-199/{len(clip)}')
        for value in ['bytes=999999999-', 'bytes=9-2', 'bytes=-', 'bytes=0-1,3-4']:
            request = Request(self.url + '/evidence/plaskett/clip.mp4', headers={'Range': value})
            with self.assertRaises(HTTPError) as error:
                urlopen(request, timeout=3)
            self.assertEqual(error.exception.code, 416)

    def test_analysis_requires_configuration_in_saved_only_mode(self):
        image = Path(__file__).with_name('evidence').joinpath('gann-official-thumbnail.jpg').read_bytes()
        payload = {'image': 'data:image/jpeg;base64,' + base64.b64encode(image).decode()}
        req = Request(self.url + '/api/analyze', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with patch.object(main, 'BACKEND_PROXY', ''), patch.dict(main.os.environ, {'GPU_BEARER_TOKEN': ''}):
            with self.assertRaises(HTTPError) as error:
                urlopen(req, timeout=3)
        self.assertEqual(error.exception.code, 400)


if __name__ == '__main__':
    unittest.main()
