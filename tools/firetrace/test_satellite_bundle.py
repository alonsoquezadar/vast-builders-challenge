import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from satellite_bundle import load_satellite, weather_at


class SatelliteBundleTests(unittest.TestCase):
    def test_real_layers_keep_observed_reconstructed_and_weather_separate(self):
        counts = {'hotspots': 13883, 'arrival': 6073, 'perimeter': 1}
        classes = {'hotspots': 'observed-thermal-detections', 'arrival': 'reconstructed-retrospective',
                   'perimeter': 'official-final-perimeter'}
        for layer in counts:
            data = load_satellite(layer)
            self.assertEqual(len(data['features']), counts[layer])
            self.assertEqual(data['_provenance']['dataClass'], classes[layer])
        self.assertEqual(load_satellite('weather')['status'], 'historical-model')
        self.assertIn('Best Match', load_satellite('weather')['source'])

    def test_weather_is_selected_in_utc_and_cannot_extrapolate_past_available_hours(self):
        data = weather_at('2025-08-28T01:12:00Z')
        self.assertEqual(data['timeUtc'], '2025-08-28T01:00:00Z')
        self.assertEqual(data['offsetSeconds'], 720)
        self.assertEqual(data['dataClass'], 'historical-weather-model')
        for time in ['2025-08-28T01:00:00', '2024-01-01T00:00:00Z', 'not-a-date']:
            with self.assertRaises(ValueError): weather_at(time)

    def test_unknown_files_and_changed_layer_bytes_are_rejected(self):
        for name in ['raw/queries', 'manifest', '../../main.py']:
            with self.assertRaises(ValueError): load_satellite(name)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = b'{"features": []}'
            (root/'manifest.json').write_text(json.dumps({'createdAt': 'now', 'outputs': [
                {'file': 'hotspots.geojson', 'sha256': hashlib.sha256(raw).hexdigest()}]}))
            (root/'hotspots.geojson').write_bytes(b'changed')
            with self.assertRaises(ValueError): load_satellite('hotspots', root)


if __name__ == '__main__':
    unittest.main()
