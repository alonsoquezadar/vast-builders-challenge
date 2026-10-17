import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from camera_bundle import load_camera_bundle,camera_frame


class CameraBundleTests(unittest.TestCase):
    def test_missing_artifacts_do_not_claim_assimilation(self):
        with tempfile.TemporaryDirectory() as directory:
            result=load_camera_bundle(directory)
            self.assertFalse(result['operationallyValidated'])
            self.assertEqual(result['vision']['observations'],[])
            self.assertEqual(result['assimilation']['status'],'pending-input')

    def test_only_receipted_vision_images_are_available(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);vision=root/'camera_assimilation/vision';vision.mkdir(parents=True)
            raw=b'jpeg-test';(vision/'frame.jpg').write_bytes(raw)
            row={'id':'frame-1','imagePath':'camera_assimilation/vision/frame.jpg','imageSha256':hashlib.sha256(raw).hexdigest()}
            manifest=vision/'observations.json';manifest.write_text(json.dumps({'observations':[row]}))
            self.assertEqual(camera_frame('frame-1',root)[0],raw)
            (vision/'frame.jpg').write_bytes(b'changed')
            self.assertEqual(len(load_camera_bundle(root)['vision']['integrityIssues']),1)
            with self.assertRaises(ValueError):camera_frame('frame-1',root)
            row['imagePath']='../../outside.jpg';manifest.write_text(json.dumps({'observations':[row]}))
            self.assertEqual(load_camera_bundle(root)['vision']['observations'],[])

    def test_calibration_is_withdrawn_when_source_observations_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);vision=root/'camera_assimilation/vision';vision.mkdir(parents=True)
            (vision/'frame.jpg').write_bytes(b'frame')
            row={'id':'frame-1','imagePath':'camera_assimilation/vision/frame.jpg','imageSha256':hashlib.sha256(b'frame').hexdigest()}
            manifest=vision/'observations.json';manifest.write_text(json.dumps({'observations':[row]}))
            calibration=root/'camera_assimilation/calibration';calibration.mkdir()
            receipt={'status':'experimental','inputs':{'observations':{'sha256':hashlib.sha256(manifest.read_bytes()).hexdigest()}}}
            (calibration/'calibration.json').write_text(json.dumps(receipt))
            self.assertTrue(load_camera_bundle(root)['calibrationArtifactCurrent'])
            row['reason']='revised visible evidence';manifest.write_text(json.dumps({'observations':[row]}))
            self.assertFalse(load_camera_bundle(root)['calibrationArtifactCurrent'])

if __name__=='__main__':unittest.main()
