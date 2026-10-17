"""Tests for demo_bundle.py. Every fixture below is SYNTHETIC test data, not real fire/camera observations.

Run: python3 -m unittest test_demo_bundle -v   (from tools/firetrace)
"""
import copy
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import demo_bundle as db

BBOX = [-122.0, 37.0, -121.0, 38.0]
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def synthetic_firms():
    def hot(lon, lat, at):  # SYNTHETIC
        return {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
                'properties': {'observedAt': at, 'frp': 1.5, 'confidence': 'n', 'scanKm': .4, 'trackKm': .4,
                               'satellite': 'N', 'source': 'SYNTHETIC', 'internalNote': 'must be dropped'}}
    return {'type': 'FeatureCollection', 'fetchedAt': '2026-01-02T03:00:00+00:00', 'stale': True,
            'sourceUrl': 'https://user:pw@example.invalid/firms.csv?token=abc#x',
            'features': [hot(-121.5, 37.5, '2026-01-01T10:15:00Z'), hot(-121.0, 38.0, '2026-01-01T22:40:00Z'),
                         hot(-110.0, 37.5, '2026-01-01T23:00:00Z'), hot(-121.5, 39.5, '2026-01-01T23:10:00Z')]}


def synthetic_cameras():
    def cam(i, lon, lat, **extra):  # SYNTHETIC
        return {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
                'properties': {'id': f'Axis-SYN{i}', 'name': f'Synthetic {i}', 'last_frame_ts': 1767300000 + i,
                               'az_current': 90.0, 'tilt_current': 2.0, 'fov': 60, 'county': 'Nowhere', 'elevationM': 100, **extra}}
    return {'type': 'FeatureCollection', 'fetchedAt': '2026-01-02T03:01:00+00:00', 'stale': False,
            'sourceUrl': 'https://example.invalid/cams/',
            'features': [cam(1, -121.8, 37.2, image_url='https://example.invalid/i.jpg?token=zzz', stream='rtsp://u:p@h/x'),
                         cam(2, -121.2, 37.9), cam(3, -118.0, 34.0), {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': []}, 'properties': {}}]}


def synthetic_perimeters():
    def ring(w, s, e, n):
        return [[[w, s], [e, s], [e, n], [w, n], [w, s]]]
    def perim(name, *box):  # SYNTHETIC
        return {'type': 'Feature', 'id': 7, 'geometry': {'type': 'Polygon', 'coordinates': ring(*box)},
                'properties': {'poly_IncidentName': name, 'poly_DateCurrent': 1767300000000, 'poly_GISAcres': 12.5, 'extra': 'dropped'}}
    return {'type': 'FeatureCollection', 'sourceUrl': 'https://example.invalid/perims',
            'features': [perim('SYN-A', -121.9, 37.1, -121.8, 37.2), perim('SYN-FAR', -118.0, 34.0, -117.9, 34.1),
                         perim('SYN-EDGE', -121.1, 37.9, -120.5, 38.5)]}


def read_bytes(path):
    with open(path, 'rb') as handle:
        return handle.read()


def write_bytes(path, content):
    with open(path, 'wb') as handle:
        handle.write(content)


class FakeGateway:
    def __init__(self, **overrides):
        self.urls, self.responses = [], {'/api/firms': synthetic_firms(), '/api/cameras': synthetic_cameras(),
                                         '/api/perimeters': synthetic_perimeters(), **overrides}

    def __call__(self, url, timeout):
        self.urls.append(url)
        path = url.split('localhost:5174', 1)[1].split('?')[0]
        value = self.responses[path]
        if isinstance(value, Exception):
            raise value
        return value if isinstance(value, bytes) else json.dumps(value).encode()


def capture(gateway=None, perimeters=False):
    return db.capture_bundle('http://localhost:5174/', BBOX, perimeters, fetch=gateway or FakeGateway(), now=NOW)


class BboxTests(unittest.TestCase):
    def test_rejects_unsafe_boxes(self):
        for bad in ([-122, 37, -122, 38], [-121, 37, -122, 38], [-130, 37, -129, 38], [-124, 33, -119, 34], [-122, 37, -121], [-122, 'x', -121, 38]):
            with self.assertRaises(db.BundleError, msg=bad):
                db.parse_bbox(bad)

    def test_perimeter_tiles_cover_bbox(self):
        box = db.parse_bbox(BBOX)
        centers = db.perimeter_centers(box)
        self.assertEqual(len(centers), 6)  # 2 x 3 envelopes of 0.5 x 0.36
        for lon, lat in [(box['west'], box['south']), (box['east'], box['north']), (-121.5, 37.5)]:
            self.assertTrue(any(abs(lon - cx) <= .25 + 1e-9 and abs(lat - cy) <= .18 + 1e-9 for cx, cy in centers))


class CaptureTests(unittest.TestCase):
    def test_geographic_cut_keeps_boundary_and_drops_outside_or_malformed(self):
        bundle = capture()
        firms, cams = bundle['sources']['firms'], bundle['sources']['cameras']
        self.assertEqual([f['geometry']['coordinates'] for f in firms['data']['features']], [[-121.5, 37.5], [-121.0, 38.0]])
        self.assertEqual((firms['total'], firms['count']), (4, 2))
        self.assertEqual([f['properties']['id'] for f in cams['data']['features']], ['Axis-SYN1', 'Axis-SYN2'])
        self.assertEqual((cams['total'], cams['count'], cams['outsideBboxOrMalformed']), (4, 2, 2))

    def test_preserves_timestamps_and_flags_replay(self):
        bundle = capture()
        self.assertIs(bundle['replay'], True)
        self.assertIn('REPLAY', bundle['notice'])
        self.assertEqual(bundle['capturedAt'], '2026-01-02T03:04:05Z')
        firms = bundle['sources']['firms']
        self.assertEqual([f['properties']['observedAt'] for f in firms['data']['features']], ['2026-01-01T10:15:00Z', '2026-01-01T22:40:00Z'])
        self.assertEqual(firms['fetchedAt'], '2026-01-02T03:00:00+00:00')  # gateway value, not re-stamped
        self.assertIs(firms['stale'], True)
        self.assertEqual(firms['observedRange'], {'field': 'observedAt', 'min': '2026-01-01T10:15:00Z', 'max': '2026-01-01T22:40:00Z'})
        cams = bundle['sources']['cameras']
        self.assertEqual(cams['data']['features'][0]['properties']['last_frame_ts'], 1767300001)
        self.assertEqual(cams['observedRange'], {'field': 'last_frame_ts', 'min': 1767300001, 'max': 1767300002})

    def test_missing_gateway_fetchedAt_stays_null(self):
        payload = synthetic_firms()
        del payload['fetchedAt']
        bundle = capture(FakeGateway(**{'/api/firms': payload}))
        self.assertIsNone(bundle['sources']['firms']['fetchedAt'])

    def test_strips_images_credentials_and_unknown_fields(self):
        bundle = capture(perimeters=True)
        text = json.dumps(bundle)
        for leaked in ('token=', 'rtsp://', 'image_url', 'user:pw', 'internalNote', 'extra', '#x'):
            self.assertNotIn(leaked, text)
        self.assertEqual(bundle['sources']['firms']['sourceUrl'], 'https://example.invalid/firms.csv')
        self.assertEqual(set(bundle['sources']['cameras']['data']['features'][0]['properties']), set(db.ALLOWED_PROPERTIES['cameras']))

    def test_secret_looking_value_is_nulled_and_counted(self):
        payload = synthetic_cameras()
        payload['features'][0]['properties']['name'] = 'https://example.invalid/x?token=abc'
        bundle = capture(FakeGateway(**{'/api/cameras': payload}))
        cams = bundle['sources']['cameras']
        self.assertIsNone(cams['data']['features'][0]['properties']['name'])
        self.assertEqual(cams['redactions'], 1)

    def test_only_get_to_fixed_gateway_paths(self):
        gateway = FakeGateway()
        capture(gateway)
        self.assertEqual(gateway.urls, ['http://localhost:5174/api/firms', 'http://localhost:5174/api/cameras'])

    def test_perimeters_optional_tiled_deduped_and_cut(self):
        gateway = FakeGateway()
        bundle = capture(gateway, perimeters=True)
        perims = bundle['sources']['perimeters']
        self.assertEqual(len(gateway.urls), 2 + 6)
        self.assertTrue(all('/api/perimeters?lon=' in u and 'lat=' in u for u in gateway.urls[2:]))
        names = [f['properties']['poly_IncidentName'] for f in perims['data']['features']]
        self.assertEqual(names, ['SYN-A', 'SYN-EDGE'])  # same feature across 6 tiles appears once; SYN-FAR cut; SYN-EDGE intersects
        self.assertEqual(perims['data']['features'][0]['geometry']['type'], 'Polygon')
        self.assertEqual(perims['tiles'], 6)
        self.assertNotIn('perimeters', capture()['sources'])

    def test_source_failure_is_unavailable_with_reason_and_no_features(self):
        for failure, expected in [(db.FetchError('el gateway respondió HTTP 502'), 'HTTP 502'), (b'<html>', 'JSON'),
                                  (json.dumps({'error': 'La fuente externa no responde.'}).encode(), 'La fuente externa'),
                                  (json.dumps({'type': 'Feature'}).encode(), 'FeatureCollection')]:
            bundle = capture(FakeGateway(**{'/api/firms': failure}))
            firms = bundle['sources']['firms']
            self.assertEqual(firms['status'], 'unavailable')
            self.assertIn(expected, firms['reason'])
            self.assertIsNone(firms['data'])
            self.assertNotIn('count', firms)
            self.assertEqual(bundle['sources']['cameras']['status'], 'ok')  # other sources unaffected
            self.assertEqual(db.validate_bundle(bundle), [])

    def test_perimeter_tile_failure_marks_whole_source_unavailable(self):
        bundle = capture(FakeGateway(**{'/api/perimeters': db.FetchError('el gateway respondió HTTP 400')}), perimeters=True)
        self.assertEqual(bundle['sources']['perimeters']['status'], 'unavailable')

    def test_oversized_perimeter_plan_is_unavailable_before_any_request(self):
        gateway = FakeGateway()
        bundle = db.capture_bundle('http://localhost:5174', [-124, 33, -121.5, 35.5], True, fetch=gateway, now=NOW)
        self.assertEqual(bundle['sources']['perimeters']['status'], 'unavailable')
        self.assertFalse([u for u in gateway.urls if 'perimeters' in u])

    def test_base_url_rejects_credentials(self):
        for bad in ('http://u:p@localhost:5174', 'http://localhost:5174/?k=v', 'ftp://localhost', 'localhost:5174'):
            with self.assertRaises(db.BundleError):
                db.normalize_base_url(bad)


class ValidateTests(unittest.TestCase):
    def test_valid_bundle_and_tamper_detection(self):
        bundle = capture(perimeters=True)
        self.assertEqual(db.validate_bundle(bundle), [])
        tampered = copy.deepcopy(bundle)
        tampered['sources']['firms']['data']['features'][0]['properties']['frp'] = 99
        self.assertTrue(any('sha256' in p for p in db.validate_bundle(tampered)))

    def test_rejects_non_replay_and_fabricated_unavailable(self):
        bundle = capture()
        live = copy.deepcopy(bundle); live['replay'] = False
        self.assertTrue(any('replay' in p for p in db.validate_bundle(live)))
        fake = copy.deepcopy(bundle)
        fake['sources']['firms'] = {'status': 'unavailable', 'reason': '', 'capturedAt': 'x', 'data': synthetic_firms()}
        problems = db.validate_bundle(fake)
        self.assertTrue(any('reason' in p for p in problems) and any('no puede traer datos' in p for p in problems))

    def test_rejects_points_outside_bbox_and_foreign_properties(self):
        bundle = capture()
        out = copy.deepcopy(bundle)
        out['sources']['firms']['data']['features'][0]['geometry']['coordinates'] = [-100, 30]
        self.assertTrue(any('fuera del bbox' in p for p in db.validate_bundle(out)))
        extra = copy.deepcopy(bundle)
        extra['sources']['cameras']['data']['features'][0]['properties']['snapshot_url'] = 'https://example.invalid/a.jpg'
        self.assertTrue(any('no permitidas' in p for p in db.validate_bundle(extra)))

    def test_rejects_secret_in_any_string_even_with_matching_digest(self):
        bundle = capture()
        bundle['gateway'] = 'http://localhost:5174'
        bundle['sources']['firms']['sourceUrl'] = 'https://example.invalid/f?api_key=abc'
        bundle['sha256'] = db._digest(bundle)
        self.assertTrue(any('secreto' in p for p in db.validate_bundle(bundle)))


class IoTests(unittest.TestCase):
    def test_atomic_write_then_reload_roundtrip(self):
        bundle = capture(perimeters=True)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'demo.json')
            size = db.write_bundle(bundle, path)
            self.assertEqual(os.listdir(folder), ['demo.json'])  # no temp leftovers
            self.assertEqual(os.path.getsize(path), size)
            self.assertEqual(db.load_bundle(path), bundle)

    def test_failed_write_keeps_previous_file_and_leaves_no_temp(self):
        good, bad = capture(), capture()
        bad['sources']['firms']['count'] = 123  # invalid -> rejected before touching disk
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'demo.json')
            db.write_bundle(good, path)
            before = read_bytes(path)
            with self.assertRaises(db.BundleError):
                db.write_bundle(bad, path, force=True)
            real_replace = os.replace
            os.replace = lambda *a: (_ for _ in ()).throw(OSError('disk full'))
            try:
                with self.assertRaises(OSError):
                    db.write_bundle(good, path, force=True)
            finally:
                os.replace = real_replace
            self.assertEqual(read_bytes(path), before)
            self.assertEqual(os.listdir(folder), ['demo.json'])

    def test_refuses_overwrite_without_force_and_enforces_size_cap(self):
        bundle = capture()
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'demo.json')
            db.write_bundle(bundle, path)
            with self.assertRaises(db.BundleError):
                db.write_bundle(bundle, path)
            db.write_bundle(bundle, path, force=True)
            with self.assertRaises(db.BundleError):
                db.write_bundle(bundle, os.path.join(folder, 'small.json'), max_bytes=100)
            self.assertFalse(os.path.exists(os.path.join(folder, 'small.json')))
            with self.assertRaises(db.BundleError):
                db.load_bundle(path, max_bytes=100)

    def test_load_rejects_corrupt_or_edited_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'demo.json')
            for content in (b'{not json', b'{"a": NaN}', b'[]', b'{}'):
                write_bytes(path, content)
                with self.assertRaises(db.BundleError):
                    db.load_bundle(path)
            with self.assertRaises(db.BundleError):
                db.load_bundle(os.path.join(folder, 'missing.json'))


class ReplayResponseTests(unittest.TestCase):
    def test_shape_matches_gateway_and_is_marked_replay(self):
        status, body = db.replay_response(capture(), 'firms')
        self.assertEqual(status, 200)
        self.assertEqual((body['type'], body['replay'], body['stale']), ('FeatureCollection', True, True))
        self.assertEqual(len(body['features']), 2)
        self.assertEqual(body['bundleCapturedAt'], '2026-01-02T03:04:05Z')

    def test_unavailable_and_absent_sources_never_return_features(self):
        bundle = capture(FakeGateway(**{'/api/firms': db.FetchError('el gateway respondió HTTP 502')}))
        status, body = db.replay_response(bundle, 'firms')
        self.assertEqual(status, 503)
        self.assertTrue(body['unavailable'] and body['replay'] and 'features' not in body and 'HTTP 502' in body['error'])
        self.assertEqual(db.replay_response(bundle, 'perimeters')[0], 404)

    def test_perimeters_filtered_by_gateway_envelope(self):
        bundle = capture(perimeters=True)
        _, near = db.replay_response(bundle, 'perimeters', -121.85, 37.15)
        self.assertEqual([f['properties']['poly_IncidentName'] for f in near['features']], ['SYN-A'])
        self.assertEqual(db.replay_response(bundle, 'perimeters', -118.0, 34.0)[0], 404)


class HttpGetTests(unittest.TestCase):
    """Loopback-only server: checks error mapping and that redirects are refused."""

    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == '/redirect':
                    self.send_response(302); self.send_header('Location', 'http://example.invalid/'); self.end_headers()
                    return
                body = json.dumps({'error': 'La fuente externa no responde. Vuelve a intentarlo.'}).encode()
                self.send_response(502); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

        cls.server = HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_http_error_becomes_reason_without_url(self):
        with self.assertRaises(db.FetchError) as caught:
            db.http_get(self.base + '/api/firms', 5)
        self.assertIn('HTTP 502', str(caught.exception))
        self.assertNotIn('127.0.0.1', str(caught.exception))

    def test_redirect_not_followed(self):
        with self.assertRaises(db.FetchError) as caught:
            db.http_get(self.base + '/redirect', 5)
        self.assertIn('HTTP 302', str(caught.exception))

    def test_unreachable_gateway_is_fetch_error(self):
        with self.assertRaises(db.FetchError):
            db.http_get('http://127.0.0.1:1/api/firms', 2)


if __name__ == '__main__':
    unittest.main()
