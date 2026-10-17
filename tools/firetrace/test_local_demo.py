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
