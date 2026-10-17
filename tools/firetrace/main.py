"""FireTrace: a small server-side gateway. No credentials reach the browser."""
import base64
import csv
import hashlib
import io
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from demo_bundle import load_bundle, replay_response

ROOT = Path(__file__).parent
REPLAY_PATH = os.environ.get('FIRETRACE_REPLAY')
REPLAY = load_bundle(ROOT / REPLAY_PATH) if REPLAY_PATH else None
BACKEND_PROXY = os.environ.get('FIRETRACE_BACKEND_PROXY', '').rstrip('/')
FIRMS = 'https://firms.modaps.eosdis.nasa.gov/data/active_fire/viirs/csv/SUOMI_VIIRS_C2_USA_contiguous_and_Hawaii_7d.csv'
CAMERAS = 'https://cameras.alertcalifornia.org/public-camera-data'
PERIMETERS = 'https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_YearToDate/FeatureServer/0/query'
COSMOS = os.environ.get('COSMOS3_REASON_URL', 'http://166.19.38.112:8001').rstrip('/')
CACHE = {}
CACHE_LOCK = threading.Lock()


def remote(url, data=None, headers=None, timeout=35):
    req = Request(url, data=json.dumps(data).encode() if data is not None else None,
                  headers={'User-Agent': 'FireTrace-hackathon/0.1', **({'Content-Type': 'application/json'} if data is not None else {}), **(headers or {})})
    with urlopen(req, timeout=timeout) as response:
        return response.read()


def cached(key, ttl, loader):
    with CACHE_LOCK:
        previous = CACHE.get(key)
        if previous and time.time() - previous[0] < ttl:
            return {**previous[1], 'stale': False}
    try:
        value = loader()
        value['fetchedAt'] = datetime.now(timezone.utc).isoformat()
        with CACHE_LOCK:
            CACHE[key] = (time.time(), value)
        return {**value, 'stale': False}
    except Exception:
        if previous:
            return {**previous[1], 'stale': True}
        raise


def firms():
    features = []
    for row in csv.DictReader(io.StringIO(remote(FIRMS).decode())):
        lon, lat = float(row['longitude']), float(row['latitude'])
        if not (-124.6 < lon < -114 and 32.3 < lat < 42):
            continue
        hhmm = row['acq_time'].zfill(4)
        features.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
                         'properties': {'observedAt': f"{row['acq_date']}T{hhmm[:2]}:{hhmm[2:]}:00Z",
                                        'frp': float(row['frp']), 'confidence': row['confidence'],
                                        'scanKm': float(row['scan']), 'trackKm': float(row['track']),
                                        'satellite': row['satellite'], 'source': 'NASA FIRMS · S-NPP VIIRS'}})
    features.sort(key=lambda f: f['properties']['observedAt'])
    return {'type': 'FeatureCollection', 'features': features, 'sourceUrl': FIRMS}


def cameras():
    data = json.loads(remote(CAMERAS + '/all_cameras-v3.json', timeout=60))
    features = []
    for feature in data.get('features', []):
        coords, props = feature.get('geometry', {}).get('coordinates', []), feature.get('properties', {})
        if len(coords) < 2 or not all(isinstance(c, (int, float)) for c in coords[:2]) or not props.get('name'):
            continue
        if not (-125 < coords[0] < -113 and 32 < coords[1] < 43):
            continue
        features.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': coords[:2]},
                         'properties': {**{k: props.get(k) for k in ['id', 'name', 'last_frame_ts', 'az_current', 'tilt_current', 'fov', 'county']},
                                        'elevationM': coords[2] if len(coords) > 2 else None}})
    return {'type': 'FeatureCollection', 'features': features, 'sourceUrl': 'https://cameras.alertcalifornia.org/'}


def vss_search(query):
    if BACKEND_PROXY:
        return json.loads(remote(BACKEND_PROXY + '/api/search', {'query': query}, timeout=100))
    base = os.environ.get('VSS_URL', '').rstrip('/')
    if not base:
        raise ValueError('VAST no está configurado en este servidor.')
    login = json.loads(remote(base + '/api/v1/auth/login', {
        'username': os.environ.get('VSS_USERNAME'), 'password': os.environ.get('VSS_PASSWORD')}))
    result = json.loads(remote(base + '/api/v1/search', {
        'query': query, 'top_k': 5, 'llm_top_n': 1, 'min_similarity': 0.3},
        {'Authorization': 'Bearer ' + login['access_token']}, timeout=90))
    return {'results': [{k: hit.get(k) for k in ['reasoning_content', 'similarity_score', 'start_time', 'end_time', 'source']} for hit in result.get('results', [])]}


def analyze(data):
    image = data.get('image', '')
    match = re.fullmatch(r'data:image/(jpeg|png);base64,([A-Za-z0-9+/=\r\n]+)', image)
    if not match:
        raise ValueError('Selecciona una imagen JPEG o PNG.')
    raw = base64.b64decode(match[2], validate=True)
    if len(raw) > 6 * 1024 * 1024 or not (raw.startswith(b'\xff\xd8\xff') or raw.startswith(b'\x89PNG\r\n\x1a\n')):
        raise ValueError('La imagen debe ser JPEG/PNG y ocupar menos de 6 MB.')
    if BACKEND_PROXY:
        result = json.loads(remote(BACKEND_PROXY + '/api/analyze', {'image': image}, timeout=160))
        return {**result, 'imageSha256': hashlib.sha256(raw).hexdigest()}
    token = os.environ.get('GPU_BEARER_TOKEN')
    if not token:
        raise ValueError('El acceso a NVIDIA Cosmos no está configurado.')
    headers = {'Authorization': 'Bearer ' + token}
    models = json.loads(remote(COSMOS + '/v1/models', headers=headers))
    model = models['data'][0]['id']
    prompt = ('Describe this wildfire observation in Spanish. Separate visible evidence from uncertainty. '
              'If this is a screenshot, map, rendered scene, or simulation, explicitly identify it as such. '
              'A colored overlay in a screenshot is not an independent thermal measurement. '
              'State whether smoke, flames, or neither is visible, their image location, visibility obstructions, '
              'and alternative explanations such as clouds or fog. Do not infer geographic coordinates, '
              'temperature, ground area, fire perimeter, speed, or future spread from this single RGB image. '
              'Keep the response under 180 words. This is an unvalidated research observation for operator review.')
    result = json.loads(remote(COSMOS + '/v1/chat/completions', {
        'model': model, 'messages': [{'role': 'system', 'content': 'Responde exclusivamente en español. Describe solo evidencia visible; no conviertas gráficos o simulaciones en mediciones físicas.'}, {'role': 'user', 'content': [
            {'type': 'text', 'text': prompt}, {'type': 'image_url', 'image_url': {'url': image}}]}],
        'max_tokens': 800, 'temperature': 0.1}, headers, timeout=150))
    content = result['choices'][0]['message'].get('content')
    if not content:
        raise ValueError('Cosmos no devolvió una observación. Inténtalo de nuevo.')
    return {'content': content, 'model': model, 'analyzedAt': datetime.now(timezone.utc).isoformat(),
            'geolocation': 'unresolved', 'status': 'requires-review', 'imageSha256': hashlib.sha256(raw).hexdigest()}


def scenario_grid(origin):
    from terrain_grid import terrain_grid, validate_origin
    origin = validate_origin(origin)
    saved = ROOT / 'evidence/garnet/scenario-terrain.json'
    if saved.is_file():
        grid = json.loads(saved.read_text())
        if all(abs(a - b) < 1e-7 for a, b in zip(origin, grid['origin'])):
            return {**grid, 'terrainMode': 'recorded', 'origin': origin}
    return terrain_grid(origin)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        # Queries and upstream errors may contain sensitive data.
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == '/health':
                return self.send_json({'ok': True})
            if path in ['/evidence/plaskett/clip.mp4', '/evidence/garnet/delilah.mp4', '/evidence/garnet/buckrock.mp4']:
                clip = ROOT / path.lstrip('/')
                size = clip.stat().st_size
                start, end, status = 0, size - 1, 200
                requested = self.headers.get('Range')
                if requested:
                    match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
                    if not match or not any(match.groups()):
                        self.send_response(416)
                        self.send_header('Content-Range', f'bytes */{size}')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    if match[1]:
                        start = int(match[1])
                        end = min(int(match[2]), size - 1) if match[2] else size - 1
                    else:
                        start = max(0, size - int(match[2]))
                    if start > end or start >= size:
                        self.send_response(416)
                        self.send_header('Content-Range', f'bytes */{size}')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    status = 206
                self.send_response(status)
                self.send_header('Content-Type', 'video/mp4')
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Content-Length', str(end - start + 1))
                if status == 206:
                    self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                self.end_headers()
                with clip.open('rb') as stream:
                    stream.seek(start)
                    remaining = end - start + 1
                    while remaining:
                        block = stream.read(min(65536, remaining))
                        if not block:
                            break
                        self.wfile.write(block)
                        remaining -= len(block)
                return
            if path == '/api/status':
                return self.send_json({'vast': bool(os.environ.get('VSS_URL') or BACKEND_PROXY),
                                       'cosmos': bool(os.environ.get('GPU_BEARER_TOKEN') or BACKEND_PROXY),
                                       'mode': 'replay' if REPLAY else 'live',
                                       'demoExample': (ROOT / 'evidence/gann-official-thumbnail-source.json').is_file(),
                                       'replayCapturedAt': REPLAY['capturedAt'] if REPLAY else None})
            if path == '/api/alignment-observation':
                evidence = ROOT / 'evidence/plaskett'
                saved = json.loads((evidence / 'analysis-65.json').read_text())
                if saved.get('imageSha256') != hashlib.sha256((evidence / 'frame-65.jpg').read_bytes()).hexdigest():
                    return self.send_json({'error': 'La imagen no coincide con el análisis guardado.'}, 409)
                return self.send_json({'frameSecond': 65, 'analysis': saved,
                                       'source': json.loads((evidence / 'source.json').read_text())})
            if path == '/api/incident':
                from incident_bundle import load_incident
                return self.send_json(load_incident(ROOT / 'evidence/garnet'))
            if path == '/api/scenario-terrain':
                params = parse_qs(urlparse(self.path).query)
                return self.send_json(scenario_grid([float(params['lon'][0]), float(params['lat'][0])]))
            if path == '/api/satellite':
                from satellite_bundle import load_satellite
                layer = parse_qs(urlparse(self.path).query).get('layer', ['summary'])[0]
                return self.send_json(load_satellite(layer))
            if path == '/api/scenario-weather':
                from satellite_bundle import weather_at
                value = parse_qs(urlparse(self.path).query).get('time', [''])[0]
                return self.send_json(weather_at(value))
            if REPLAY and path in ['/api/firms', '/api/cameras', '/api/perimeters']:
                params = parse_qs(urlparse(self.path).query)
                lon = float(params['lon'][0]) if 'lon' in params else None
                lat = float(params['lat'][0]) if 'lat' in params else None
                status, body = replay_response(REPLAY, path.rsplit('/', 1)[1], lon, lat)
                return self.send_json(body, status)
            if path == '/api/demo-observation':
                sample = parse_qs(urlparse(self.path).query).get('sample', ['gann'])[0]
                name = {'gann': 'gann-official-thumbnail', 'grizzly': 'grizzly-camera'}.get(sample)
                if not name or not (ROOT / 'evidence' / (name + '.jpg')).is_file():
                    return self.send_json({'error': 'Ejemplo todavía no disponible.'}, 404)
                receipt = json.loads((ROOT / 'evidence' / (name + '-source.json')).read_text())
                saved_path = ROOT / 'evidence' / (name + '-analysis.json')
                saved = json.loads(saved_path.read_text()) if saved_path.is_file() else None
                if saved and saved.get('imageSha256') != hashlib.sha256((ROOT / 'evidence' / (name + '.jpg')).read_bytes()).hexdigest():
                    saved = None
                return self.send_json({'imagePath': './evidence/' + name + '.jpg', 'source': receipt, 'savedAnalysis': saved})
            if path == '/api/firms':
                return self.send_json(cached('firms', 600, firms))
            if path == '/api/cameras':
                return self.send_json(cached('cameras', 60, cameras))
            if path == '/api/perimeters':
                params = parse_qs(urlparse(self.path).query)
                lon, lat = float(params['lon'][0]), float(params['lat'][0])
                if not (-125 < lon < -113 and 32 < lat < 43):
                    raise ValueError('La ubicación debe estar en California o sus alrededores.')
                query = urlencode({'f': 'geojson', 'where': '1=1', 'outFields': 'poly_IncidentName,poly_DateCurrent,poly_GISAcres',
                                   'geometry': f'{lon-.25},{lat-.18},{lon+.25},{lat+.18}', 'geometryType': 'esriGeometryEnvelope',
                                   'inSR': 4326, 'outSR': 4326, 'spatialRel': 'esriSpatialRelIntersects', 'resultRecordCount': 100})
                value = json.loads(remote(PERIMETERS + '?' + query))
                if 'error' in value:
                    raise ValueError('El catálogo de perímetros no está disponible.')
                return self.send_json({**value, 'sourceUrl': PERIMETERS.rsplit('/query', 1)[0]})
            if path.startswith('/api/'):
                return self.send_json({'error': 'Ruta no disponible.'}, 404)
            if path not in ['/', '/index.html', '/style.css', '/app.js', '/geo.mjs',
                            '/alignment.html', '/alignment.js', '/alignment.css',
                            '/incident.html', '/incident.js', '/incident.css', '/incident_model.mjs',
                            '/simulation.html', '/simulation.js', '/simulation.css',
                            '/satellite-view.mjs', '/satellite-view.css',
                            '/evidence/garnet/delilah-86.jpg', '/evidence/garnet/delilah-110.jpg',
                            '/evidence/garnet/delilah-134.jpg', '/evidence/garnet/buckrock-222.jpg',
                            '/evidence/garnet/buckrock-244.jpg', '/evidence/garnet/buckrock-267.jpg',
                            '/evidence/plaskett/clip.mp4', '/evidence/plaskett/frame-55.jpg',
                            '/evidence/plaskett/frame-65.jpg', '/evidence/plaskett/frame-75.jpg',
                            '/evidence/gann-official-thumbnail.jpg', '/evidence/grizzly-camera.jpg']:
                return self.send_json({'error': 'Archivo no disponible.'}, 404)
            return super().do_GET()
        except (BrokenPipeError, ConnectionResetError):
            return
        except (ValueError, KeyError):
            return self.send_json({'error': 'Solicitud inválida o fuente no disponible.'}, 400)
        except Exception:
            return self.send_json({'error': 'La fuente externa no responde. Vuelve a intentarlo.'}, 502)

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length < 9 * 1024 * 1024:
                return self.send_json({'error': 'Solicitud demasiado grande o vacía.'}, 413)
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('La solicitud debe ser un objeto JSON.')
            path = urlparse(self.path).path
            if path == '/api/simulate':
                from simulation import simulate
                weather = None
                if data.get('weatherTimeUtc'):
                    from satellite_bundle import scenario_weather
                    weather = scenario_weather(data['weatherTimeUtc'], data.get('origin'))
                    data = {**data, 'windFromDeg': weather['windFromDeg'], 'windSpeedMps': weather['windSpeedMps']}
                grid = scenario_grid(data.get('origin'))
                result = simulate({**data, 'grid': grid, 'terrain': {
                    key: grid[key] for key in ['terrainSource', 'terrainFetchedAt', 'terrainStatus']}})
                result.setdefault('properties', {}).update({
                    'terrainSource': grid['terrainSource'], 'terrainStatus': grid['terrainStatus'],
                    'terrainFetchedAt': grid['terrainFetchedAt'], 'terrainMode': grid['terrainMode'],
                    'terrainTiles': grid['tiles'], 'seedStatus': 'operator-assumed-not-camera-detected'})
                result['properties']['meteorology'] = weather or {'dataClass': 'operator-assumed'}
                if weather:
                    result['properties']['assumptions']['wind'] = 'Viento DESDE, a 10 m, de un punto de modelo meteorológico histórico; no es una medición local.'
                    result['properties']['limitations'].append('Viento de un punto de modelo histórico; la humedad relativa se conserva como referencia y no modifica el factor de combustible.')
                return self.send_json(result)
            if path == '/api/calibrate':
                try:
                    from calibration import fit_camera
                    return self.send_json(fit_camera(data))
                except ImportError:
                    return self.send_json({'error': 'Instala requirements-calibration.txt para ajustar la cámara.'}, 503)
            if path == '/api/analyze':
                return self.send_json(analyze(data))
            if path == '/api/search':
                query = data.get('query', '').strip()
                if not query or len(query) > 500:
                    raise ValueError('Escribe una búsqueda de hasta 500 caracteres.')
                return self.send_json(vss_search(query))
            return self.send_json({'error': 'Ruta no disponible.'}, 404)
        except (ValueError, KeyError) as error:
            return self.send_json({'error': str(error)}, 400)
        except HTTPError as error:
            return self.send_json({'error': f'El servicio de análisis devolvió HTTP {error.code}.'}, 502)
        except Exception:
            return self.send_json({'error': 'El servicio no pudo completar el análisis.'}, 502)


if __name__ == '__main__':
    server = ThreadingHTTPServer((os.environ.get('HOST', '0.0.0.0'), int(os.environ.get('PORT', 8080))), Handler)
    print(f'FireTrace listening on port {server.server_port}', flush=True)
    server.serve_forever()
