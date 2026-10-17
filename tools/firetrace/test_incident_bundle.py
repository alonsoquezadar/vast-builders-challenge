import json
from pathlib import Path
import shutil
import tempfile
import unittest

from incident_bundle import load_incident

ROOT = Path(__file__).with_name('evidence') / 'garnet'


class IncidentBundleTests(unittest.TestCase):
    def test_all_six_observations_match_frames_and_keep_unresolved_location(self):
        bundle = load_incident(ROOT)
        self.assertEqual(len(bundle['frames']), 6)
        self.assertEqual(bundle['geolocation'], 'unresolved')
        self.assertIsNone(bundle['propagationModel'])
        for frame in bundle['frames']:
            self.assertEqual(frame['analysisIntegrity'], 'matched')
            self.assertEqual(frame['analysis']['imageSha256'], frame['imageSha256'])
            self.assertEqual(frame['analysis']['geolocation'], 'unresolved')
            self.assertEqual(frame['timezone'], 'unverified')

    def test_changed_frame_is_rejected_instead_of_showing_wrong_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(ROOT, tmp, dirs_exist_ok=True)
            Path(tmp, 'delilah-86.jpg').write_bytes(b'changed image')
            with self.assertRaises(ValueError): load_incident(tmp)

    def test_wrong_analysis_is_withheld_and_missing_analysis_still_allows_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(ROOT, tmp, dirs_exist_ok=True)
            path = Path(tmp, 'delilah-86-analysis.json')
            data = json.loads(path.read_text())
            data['imageSha256'] = 'wrong'
            path.write_text(json.dumps(data))
            Path(tmp, 'buckrock-222-analysis.json').unlink()
            bundle = load_incident(tmp)
            for name in ['delilah-86', 'buckrock-222']:
                frame = next(f for f in bundle['frames'] if f['id'] == name)
                self.assertIsNone(frame['analysis'])
                self.assertEqual(frame['analysisIntegrity'], 'unavailable-or-mismatched')


if __name__ == '__main__':
    unittest.main()
