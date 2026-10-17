import copy
import hashlib
import json
from pathlib import Path
import unittest

from incident_bundle import load_incident
from localisation import localise_payload, translate_text
from satellite_bundle import load_satellite


class BritishEnglishPresentationTests(unittest.TestCase):
    def test_saved_response_is_translated_without_rewriting_evidence_or_correcting_its_claims(self):
        root = Path(__file__).parent / 'evidence/garnet'
        source_file = root / 'delilah-110-analysis.json'
        before = source_file.read_bytes()
        source = load_incident(root)
        original = copy.deepcopy(source)
        display = localise_payload(source)
        frame = next(f for f in display['frames'] if f['id'] == 'delilah-110')
        raw_frame = next(f for f in source['frames'] if f['id'] == 'delilah-110')
        self.assertIn('aerial or satellite', frame['analysis']['content'])
        self.assertIn('incorrectly', frame['reviewNotes'][0])
        self.assertIn('display translation', frame['analysis']['translationNote'])
        self.assertEqual(frame['analysis']['translation']['originalContentSha256'],
                         hashlib.sha256(raw_frame['analysis']['content'].encode()).hexdigest())
        self.assertEqual(frame['analysis']['imageSha256'], raw_frame['analysis']['imageSha256'])
        self.assertEqual(source, original)
        self.assertEqual(source_file.read_bytes(), before)

    def test_geometry_times_and_source_hashes_are_not_translated(self):
        source = load_satellite('arrival')
        display = localise_payload(source)
        self.assertEqual(display['features'], source['features'])
        self.assertEqual(display['_provenance']['sha256'], source['_provenance']['sha256'])
        self.assertIn('Retrospective reconstruction', display['_provenance']['limitations'][0])
        weather = load_satellite('weather')
        english_weather = localise_payload(weather)
        self.assertEqual(english_weather['hours'], weather['hours'])
        self.assertIn('single model point', english_weather['source'])

    def test_dynamic_messages_keep_dates_numbers_and_identifiers(self):
        self.assertEqual(translate_text('No hay área inicial reconstruida en 2025-08-24T00:00:00Z: la primera celda llega en 2025-08-24T09:26:00Z. Selecciona una hora con área inicial; no se genera una semilla artificial.'),
                         'No initial reconstructed area at 2025-08-24T00:00:00Z: the first cell arrival is at 2025-08-24T09:26:00Z. Select a time with an initial reconstructed area; no artificial ignition point is created.')
        message = 'La meteorología horaria del archivo (Open-Meteo, hasta %s) no cubre %d h desde %s.' % ('2025-09-13T23:00:00Z', 24, '2025-09-13T20:00:00Z')
        self.assertEqual(translate_text(message), 'The hourly weather archive (Open-Meteo, through 2025-09-13T23:00:00Z) does not cover 24 hours from 2025-09-13T20:00:00Z.')
        self.assertEqual(translate_text('horizonHours debe ser uno de [6, 12, 24].'), 'horizonHours must be one of [6, 12, 24].')

    def test_unknown_original_material_and_machine_tokens_are_preserved(self):
        original = {'content': 'An original English observation.', 'role': 'modeled-extent',
                    'status': 'no-calibration', 'coordinates': [-119.1, 36.8], 'validated': False}
        self.assertEqual(localise_payload(original), original)
        self.assertNotIn('translation', localise_payload(original))

    def test_all_application_documents_declare_british_english(self):
        root = Path(__file__).parent
        for name in ('firetrace', 'index', 'alignment', 'incident', 'simulation', 'fusion'):
            with self.subTest(page=name):
                self.assertIn('lang="en-GB"', (root / (name + '.html')).read_text())


if __name__ == '__main__':
    unittest.main()
