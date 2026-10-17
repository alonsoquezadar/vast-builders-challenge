"""FireTrace demo bundle: freeze gateway data into one versioned JSON file for a replayable demo.

Capture (needs the FireTrace gateway running; GET only, no external calls from this tool):
    python3 demo_bundle.py capture --bbox -122.6 37.2 -121.4 38.0 --out demo.json [--perimeters]
Check a bundle:
    python3 demo_bundle.py validate demo.json
Use from the gateway:
    from demo_bundle import load_bundle, replay_response
    status, body = replay_response(load_bundle('demo.json'), 'firms')

The bundle is an explicit REPLAY: nothing in it is live. A source that failed is stored as
`unavailable` with a reason; hot spots, cameras or perimeters are never synthesised.
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

SCHEMA = 'firetrace.demo-bundle/1'
NOTICE = 'REPLAY: datos congelados de una captura anterior. No son tiempo real ni una medición actual.'
DEFAULT_BASE_URL = 'http://localhost:5174'
# Same California box the gateway accepts for cameras/perimeters.
CA_BOUNDS = (-125.0, 32.0, -113.0, 43.0)
MAX_SPAN_DEG = 3.0
MAX_BUNDLE_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
# The gateway's perimeters endpoint returns an envelope of lon +-0.25, lat +-0.18 around the point.
PERIM_HALF = (0.25, 0.18)
MAX_PERIMETER_TILES = 16

# Only these properties survive capture: no image/stream URLs, tokens or free-form fields.
ALLOWED_PROPERTIES = {
    'firms': ('observedAt', 'frp', 'confidence', 'scanKm', 'trackKm', 'satellite', 'source'),
    'cameras': ('id', 'name', 'last_frame_ts', 'az_current', 'tilt_current', 'fov', 'county', 'elevationM'),
    'perimeters': ('poly_IncidentName', 'poly_DateCurrent', 'poly_GISAcres'),
}
OBSERVED_FIELD = {'firms': 'observedAt', 'cameras': 'last_frame_ts', 'perimeters': 'poly_DateCurrent'}
GATEWAY_PATH = {'firms': '/api/firms', 'cameras': '/api/cameras', 'perimeters': '/api/perimeters'}
SOURCE_ORDER = ('firms', 'cameras', 'perimeters')

SECRET_PATTERN = re.compile(
    r'data:image/|://[^/\s]*@|[?&](?:token|access_token|api[_-]?key|key|sig|signature|auth|x-amz-[a-z-]+)=|'
    r'\bbearer\s+\S|-----BEGIN', re.I)
SECRET_KEY_PATTERN = re.compile(r'token|secret|password|passwd|authorization|api[_-]?key|credential|cookie', re.I)


class BundleError(ValueError):
    """The bundle is malformed, unsafe or too large."""


class FetchError(Exception):
    """A gateway request failed; the message is safe to store as an `unavailable` reason."""


# ---------------------------------------------------------------- bbox

def parse_bbox(values):
    if isinstance(values, dict):
        values = [values.get(k) for k in ('west', 'south', 'east', 'north')]
    try:
        west, south, east, north = [float(v) for v in values]
    except (TypeError, ValueError):
        raise BundleError('bbox debe tener 4 números: west south east north.')
    if not all(math.isfinite(v) for v in (west, south, east, north)):
        raise BundleError('bbox contiene valores no finitos.')
    if not (west < east and south < north):
        raise BundleError('bbox inválido: se requiere west<east y south<north.')
    if west < CA_BOUNDS[0] or east > CA_BOUNDS[2] or south < CA_BOUNDS[1] or north > CA_BOUNDS[3]:
        raise BundleError('bbox fuera de California (lon -125..-113, lat 32..43).')
    if east - west > MAX_SPAN_DEG or north - south > MAX_SPAN_DEG:
        raise BundleError(f'bbox demasiado grande: máximo {MAX_SPAN_DEG}° por lado.')
    return {'west': west, 'south': south, 'east': east, 'north': north}


def _in_bbox(lon, lat, b):
    return b['west'] <= lon <= b['east'] and b['south'] <= lat <= b['north']


def _geometry_bounds(geometry):
    """(minLon, minLat, maxLon, maxLat) of a Polygon/MultiPolygon, or None when malformed."""
    if not isinstance(geometry, dict) or geometry.get('type') not in ('Polygon', 'MultiPolygon'):
        return None
    points = []

    def walk(node, depth):
        if depth == 0:
            if (isinstance(node, list) and len(node) >= 2 and all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in node[:2])):
                points.append((node[0], node[1]))
                return True
            return False
        return isinstance(node, list) and bool(node) and all(walk(child, depth - 1) for child in node)

    depth = 2 if geometry['type'] == 'Polygon' else 3
    if not walk(geometry.get('coordinates'), depth) or not points:
        return None
    lons, lats = [p[0] for p in points], [p[1] for p in points]
    return min(lons), min(lats), max(lons), max(lats)


def _bounds_intersect(bounds, b):
    return not (bounds[2] < b['west'] or bounds[0] > b['east'] or bounds[3] < b['south'] or bounds[1] > b['north'])


# ---------------------------------------------------------------- sanitising

def _safe_url(url):
    """Drop credentials, query and fragment; keep only plain http(s) locations."""
    if not isinstance(url, str):
        return None
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        return None
    host = parts.hostname if ':' not in parts.hostname else f'[{parts.hostname}]'
    netloc = host + (f':{parts.port}' if parts.port else '')
    return urlunsplit((parts.scheme, netloc, parts.path, '', ''))


def _scrub_value(value):
    """Scalar only, finite, not secret-looking. Returns (value, redacted?)."""
    if value is None or isinstance(value, (bool, int)):
        return value, False
    if isinstance(value, float):
        return (value, False) if math.isfinite(value) else (None, True)
    if isinstance(value, str):
        return (None, True) if SECRET_PATTERN.search(value) else (value, False)
    return None, True


def _clean_feature(source, feature, bbox):
    """Return (clean feature | None, redactions). None means: outside the bbox or malformed."""
    if not isinstance(feature, dict):
        return None, 0
    geometry, props = feature.get('geometry'), feature.get('properties')
    if not isinstance(props, dict):
        props = {}
    if source == 'perimeters':
        bounds = _geometry_bounds(geometry)
        if bounds is None or not _bounds_intersect(bounds, bbox):
            return None, 0
        clean_geometry = {'type': geometry['type'], 'coordinates': geometry['coordinates']}
    else:
        coords = geometry.get('coordinates') if isinstance(geometry, dict) and geometry.get('type') == 'Point' else None
        if (not isinstance(coords, list) or len(coords) < 2
                or not all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in coords[:2])
                or not _in_bbox(coords[0], coords[1], bbox)):
            return None, 0
        clean_geometry = {'type': 'Point', 'coordinates': [coords[0], coords[1]]}
    redactions, clean_props = 0, {}
    for key in ALLOWED_PROPERTIES[source]:
        if key in props:
            clean_props[key], redacted = _scrub_value(props[key])
            redactions += redacted
    return {'type': 'Feature', 'geometry': clean_geometry, 'properties': clean_props}, redactions


def _observed_range(source, features):
    field = OBSERVED_FIELD[source]
    values = [f['properties'].get(field) for f in features if f['properties'].get(field) is not None]
    kinds = {type(v) is str for v in values}
    numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)
    if not values or (len(kinds) != 1) or not (kinds == {True} or numeric):
        return {'field': field, 'min': None, 'max': None}
    return {'field': field, 'min': min(values), 'max': max(values)}


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _digest(bundle):
    return hashlib.sha256(_canonical({'bbox': bundle['bbox'], 'sources': bundle['sources']}).encode()).hexdigest()


# ---------------------------------------------------------------- fetching

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def http_get(url, timeout=60):
    """GET bytes from the gateway. Redirects are refused; errors become FetchError with a safe reason."""
    request = Request(url, headers={'User-Agent': 'FireTrace-demo-bundle/1', 'Accept': 'application/json'})
    try:
        with build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        detail = ''
        try:
            payload = json.loads(error.read(4096))
            if isinstance(payload, dict) and isinstance(payload.get('error'), str):
                detail = ': ' + payload['error'][:160]
        except (ValueError, OSError):
            pass
        raise FetchError(f'el gateway respondió HTTP {error.code}{detail}')
    except URLError as error:
        raise FetchError(f'gateway inaccesible ({type(error.reason).__name__})')
    except (TimeoutError, OSError) as error:
        raise FetchError(f'gateway inaccesible ({type(error).__name__})')
    if len(body) > MAX_RESPONSE_BYTES:
        raise FetchError('respuesta del gateway demasiado grande')
    return body


def _no_constants(name):
    raise ValueError('constante JSON no finita: ' + name)


def _fetch_json(fetch, url, timeout):
    raw = fetch(url, timeout)
    try:
        value = json.loads(raw, parse_constant=_no_constants)
    except ValueError:
        raise FetchError('respuesta del gateway no es JSON válido')
    if not isinstance(value, dict):
        raise FetchError('respuesta del gateway con forma inesperada')
    if isinstance(value.get('error'), str) and 'features' not in value:
        raise FetchError('el gateway informó un error: ' + value['error'][:160])
    if value.get('type') != 'FeatureCollection' or not isinstance(value.get('features'), list):
        raise FetchError('respuesta del gateway no es un FeatureCollection')
    return value


def perimeter_centers(bbox):
    """Centres so that the gateway's fixed envelopes cover the whole bbox."""
    width, height = bbox['east'] - bbox['west'], bbox['north'] - bbox['south']
    nx, ny = max(1, math.ceil(width / (2 * PERIM_HALF[0]))), max(1, math.ceil(height / (2 * PERIM_HALF[1])))
    return [(bbox['west'] + (i + .5) * width / nx, bbox['south'] + (j + .5) * height / ny)
            for j in range(ny) for i in range(nx)]


def _unavailable(reason, captured_at):
    return {'status': 'unavailable', 'reason': reason, 'capturedAt': captured_at, 'data': None}


def _capture_source(source, base_url, bbox, fetch, timeout, captured_at):
    try:
        if source == 'perimeters':
            centers = perimeter_centers(bbox)
            if len(centers) > MAX_PERIMETER_TILES:
                raise FetchError(f'bbox requeriría {len(centers)} consultas de perímetros (máximo {MAX_PERIMETER_TILES}).')
            responses = [_fetch_json(fetch, f"{base_url}/api/perimeters?{urlencode({'lon': f'{lon:.5f}', 'lat': f'{lat:.5f}'})}", timeout)
                         for lon, lat in centers]
        else:
            responses = [_fetch_json(fetch, base_url + GATEWAY_PATH[source], timeout)]
    except FetchError as error:
        return _unavailable(str(error), captured_at)

    features, seen, total, redactions, skipped = [], set(), 0, 0, 0
    for response in responses:
        total += len(response['features'])
        for raw in response['features']:
            feature, redacted = _clean_feature(source, raw, bbox)
            if feature is None:
                skipped += 1
                continue
            key = _canonical(feature)
            if key in seen:  # overlapping perimeter tiles
                continue
            seen.add(key)
            features.append(feature)
            redactions += redacted
    first = responses[0]
    record = {
        'status': 'ok',
        'sourceUrl': _safe_url(first.get('sourceUrl')),
        'fetchedAt': first.get('fetchedAt') if isinstance(first.get('fetchedAt'), str) else None,
        'stale': first.get('stale') is True,
        'capturedAt': captured_at,
        'total': total,
        'count': len(features),
        'outsideBboxOrMalformed': skipped,
        'redactions': redactions,
        'observedRange': _observed_range(source, features),
        'data': {'type': 'FeatureCollection', 'features': features},
    }
    if source == 'perimeters':
        record['tiles'] = len(responses)
        record['truncated'] = any(r.get('exceededTransferLimit') is True or (r.get('properties') or {}).get('exceededTransferLimit') is True
                                  for r in responses)
    return record


def normalize_base_url(base_url):
    parts = urlsplit(base_url)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise BundleError('base-url debe ser http(s)://host[:puerto] sin credenciales ni query.')
    return _safe_url(base_url).rstrip('/')


def capture_bundle(base_url, bbox, include_perimeters=False, fetch=None, timeout=60, now=None):
    """Build a bundle from a running gateway. `fetch(url, timeout) -> bytes` is injectable for tests."""
    base_url, bbox, fetch = normalize_base_url(base_url), parse_bbox(bbox), fetch or http_get
    captured_at = (now or datetime.now(timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ')
    names = ['firms', 'cameras'] + (['perimeters'] if include_perimeters else [])
    bundle = {'schema': SCHEMA, 'replay': True, 'notice': NOTICE, 'capturedAt': captured_at,
              'gateway': base_url, 'bbox': bbox,
              'sources': {name: _capture_source(name, base_url, bbox, fetch, timeout, captured_at) for name in names}}
    bundle['sha256'] = _digest(bundle)
    problems = validate_bundle(bundle)
    if problems:
        raise BundleError('el bundle capturado no es válido: ' + '; '.join(problems[:3]))
    return bundle


# ---------------------------------------------------------------- validation / io

def _walk_strings(node, path=''):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, child in node.items():
            yield from _walk_strings(key, path + '{key}')
            yield from _walk_strings(child, f'{path}.{key}')
    elif isinstance(node, list):
        for index, child in enumerate(node):
            yield from _walk_strings(child, f'{path}[{index}]')


def _validate_source(name, record, bbox):
    errors, where = [], f'sources.{name}'
    if not isinstance(record, dict):
        return [f'{where}: debe ser un objeto']
    status = record.get('status')
    if not isinstance(record.get('capturedAt'), str):
        errors.append(f'{where}.capturedAt requerido')
    if status == 'unavailable':
        if not isinstance(record.get('reason'), str) or not record['reason'].strip():
            errors.append(f'{where}: unavailable requiere reason')
        if record.get('data') is not None:
            errors.append(f'{where}: unavailable no puede traer datos')
        return errors
    if status != 'ok':
        return errors + [f'{where}.status debe ser ok o unavailable']
    data = record.get('data')
    if not isinstance(data, dict) or data.get('type') != 'FeatureCollection' or not isinstance(data.get('features'), list):
        return errors + [f'{where}.data debe ser un FeatureCollection']
    if record.get('count') != len(data['features']):
        errors.append(f'{where}.count no coincide con las features')
    if not (record.get('fetchedAt') is None or isinstance(record.get('fetchedAt'), str)):
        errors.append(f'{where}.fetchedAt debe ser texto o null')
    if not isinstance(record.get('stale'), bool):
        errors.append(f'{where}.stale debe ser booleano')
    allowed = set(ALLOWED_PROPERTIES[name])
    for index, feature in enumerate(data['features']):
        label = f'{where}.data.features[{index}]'
        if not isinstance(feature, dict) or set(feature) != {'type', 'geometry', 'properties'} or feature['type'] != 'Feature':
            errors.append(f'{label}: forma inválida')
            continue
        props = feature['properties']
        if not isinstance(props, dict) or not set(props) <= allowed:
            errors.append(f'{label}: propiedades no permitidas')
        elif any(isinstance(v, (dict, list)) for v in props.values()):
            errors.append(f'{label}: propiedades no escalares')
        if name == 'perimeters':
            bounds = _geometry_bounds(feature['geometry'])
            if bounds is None or not _bounds_intersect(bounds, bbox):
                errors.append(f'{label}: perímetro inválido o fuera del bbox')
        else:
            geometry = feature['geometry']
            coords = geometry.get('coordinates') if isinstance(geometry, dict) and geometry.get('type') == 'Point' else None
            if (not isinstance(coords, list) or len(coords) != 2 or not all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in coords)
                    or not _in_bbox(coords[0], coords[1], bbox)):
                errors.append(f'{label}: punto inválido o fuera del bbox')
        if len(errors) >= 20:
            errors.append(f'{where}: demasiados errores, se omiten el resto')
            break
    return errors


def validate_bundle(bundle):
    """Return a list of problems; an empty list means the bundle is safe to replay."""
    if not isinstance(bundle, dict):
        return ['el bundle debe ser un objeto JSON']
    errors = []
    if bundle.get('schema') != SCHEMA:
        errors.append(f'schema debe ser {SCHEMA}')
    if bundle.get('replay') is not True:
        errors.append('replay debe ser true')
    if not isinstance(bundle.get('capturedAt'), str):
        errors.append('capturedAt requerido')
    try:
        bbox = parse_bbox(bundle.get('bbox'))
    except BundleError as error:
        return errors + [str(error)]
    sources = bundle.get('sources')
    if not isinstance(sources, dict) or not {'firms', 'cameras'} <= set(sources) or not set(sources) <= set(SOURCE_ORDER):
        return errors + ['sources debe incluir firms y cameras (perimeters opcional)']
    for name in SOURCE_ORDER:
        if name in sources:
            errors += _validate_source(name, sources[name], bbox)
    if not errors:
        try:
            if bundle.get('sha256') != _digest(bundle):
                errors.append('sha256 no coincide: el bundle fue modificado o está corrupto')
        except (TypeError, ValueError):
            errors.append('el bundle contiene valores no serializables')
    for path, text in _walk_strings(bundle):
        if path.endswith('{key}') and SECRET_KEY_PATTERN.search(text):
            errors.append(f'clave sospechosa de secreto en {path[:-5]}: {text[:40]}')
        elif SECRET_PATTERN.search(text):
            errors.append(f'valor sospechoso de secreto/imagen en {path}')
        if len(errors) >= 25:
            break
    return errors


def load_bundle(path, max_bytes=MAX_BUNDLE_BYTES):
    """Read and validate a bundle file; raises BundleError (never returns an unchecked bundle)."""
    try:
        if os.path.getsize(path) > max_bytes:
            raise BundleError(f'bundle mayor que {max_bytes} bytes.')
        with open(path, 'rb') as handle:
            bundle = json.loads(handle.read(), parse_constant=_no_constants)
    except OSError as error:
        raise BundleError(f'no se pudo leer el bundle ({type(error).__name__}).')
    except ValueError as error:
        if isinstance(error, BundleError):
            raise
        raise BundleError('el bundle no es JSON válido.')
    problems = validate_bundle(bundle)
    if problems:
        raise BundleError('bundle inválido: ' + '; '.join(problems[:5]))
    return bundle


def write_bundle(bundle, path, force=False, max_bytes=MAX_BUNDLE_BYTES):
    """Atomic write: temp file in the same directory, fsync, rename. Refuses to clobber without force."""
    problems = validate_bundle(bundle)
    if problems:
        raise BundleError('bundle inválido: ' + '; '.join(problems[:3]))
    payload = (json.dumps(bundle, indent=1, ensure_ascii=False, allow_nan=False) + '\n').encode()
    if len(payload) > max_bytes:
        raise BundleError(f'bundle de {len(payload)} bytes excede el máximo de {max_bytes}; reduce el bbox.')
    if os.path.exists(path) and not force:
        raise BundleError('el archivo ya existe; usa --force para reemplazarlo.')
    directory = os.path.dirname(os.path.abspath(path))
    handle, temp = tempfile.mkstemp(prefix='.demo-bundle-', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(handle, 'wb') as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(temp, 0o644)
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise
    return len(payload)


# ---------------------------------------------------------------- replay helper for the gateway

def replay_response(bundle, source, lon=None, lat=None):
    """(status, body) shaped like the live gateway endpoint, with replay=True.

    firms/cameras ignore lon/lat. perimeters filters to the gateway's envelope around lon/lat when given.
    An unavailable or absent source yields 503/404 with the stored reason, never invented data.
    """
    record = (bundle.get('sources') or {}).get(source)
    if record is None:
        return 404, {'error': f'{source} no fue capturado en este bundle.', 'replay': True}
    if record['status'] != 'ok':
        return 503, {'error': 'Fuente no disponible en el bundle: ' + record['reason'], 'replay': True, 'unavailable': True,
                     'capturedAt': record['capturedAt']}
    features = record['data']['features']
    if source == 'perimeters' and lon is not None and lat is not None:
        if not _in_bbox(lon, lat, bundle['bbox']):
            return 404, {'error': 'Ubicación fuera del recorte congelado en el bundle.', 'replay': True}
        window = {'west': lon - PERIM_HALF[0], 'east': lon + PERIM_HALF[0], 'south': lat - PERIM_HALF[1], 'north': lat + PERIM_HALF[1]}
        features = [f for f in features if _bounds_intersect(_geometry_bounds(f['geometry']), window)]
    body = {'type': 'FeatureCollection', 'features': features, 'sourceUrl': record['sourceUrl'], 'fetchedAt': record['fetchedAt'],
            'stale': record['stale'], 'replay': True, 'capturedAt': record['capturedAt'], 'bundleCapturedAt': bundle['capturedAt'],
            'notice': bundle['notice']}
    if source == 'perimeters':
        body['truncated'] = record['truncated']
    return 200, body


def summarize(bundle):
    lines = [f"{bundle['schema']} replay=true capturedAt={bundle['capturedAt']} bbox={bundle['bbox']}"]
    for name in SOURCE_ORDER:
        record = bundle['sources'].get(name)
        if record is None:
            continue
        if record['status'] != 'ok':
            lines.append(f"  {name}: UNAVAILABLE ({record['reason']})")
        else:
            span = record['observedRange']
            lines.append(f"  {name}: {record['count']} de {record['total']} · {span['field']} {span['min']} → {span['max']} · fetchedAt {record['fetchedAt']} · stale={record['stale']}")
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Congela datos del gateway FireTrace en un bundle JSON de replay.')
    sub = parser.add_subparsers(dest='command', required=True)
    capture = sub.add_parser('capture', help='captura desde un gateway en ejecución')
    capture.add_argument('--bbox', nargs=4, type=float, required=True, metavar=('W', 'S', 'E', 'N'))
    capture.add_argument('--out', required=True)
    capture.add_argument('--base-url', default=DEFAULT_BASE_URL)
    capture.add_argument('--perimeters', action='store_true', help='incluye /api/perimeters (varias consultas por bbox)')
    capture.add_argument('--timeout', type=float, default=60)
    capture.add_argument('--force', action='store_true', help='reemplaza el archivo de salida si existe')
    check = sub.add_parser('validate', help='valida un bundle existente')
    check.add_argument('path')
    args = parser.parse_args(argv)
    try:
        if args.command == 'validate':
            print(summarize(load_bundle(args.path)))
            return 0
        bundle = capture_bundle(args.base_url, args.bbox, args.perimeters, timeout=args.timeout)
        statuses = [record['status'] for record in bundle['sources'].values()]
        if 'ok' not in statuses:
            print('Ninguna fuente disponible; no se escribió el bundle.\n' + summarize(bundle), file=sys.stderr)
            return 1
        size = write_bundle(bundle, args.out, force=args.force)
        print(summarize(bundle) + f'\nEscrito {args.out} ({size} bytes).')
        return 0 if all(s == 'ok' for s in statuses) else 3
    except BundleError as error:
        print(f'Error: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
