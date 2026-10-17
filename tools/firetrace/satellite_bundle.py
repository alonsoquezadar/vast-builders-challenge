"""Serve hash-checked historical layers without exposing acquisition credentials."""
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).parent / 'evidence/garnet/satellite'
FILES = {'hotspots': 'hotspots.geojson', 'arrival': 'arrival-reconstructed.geojson',
         'perimeter': 'perimeter.geojson', 'weather': 'weather-hourly.json',
         'summary': 'summary.json', 'daily': 'daily-extent-reconstructed.geojson',
         'overpasses': 'overpasses.json'}
CLASSES = {'hotspots': 'observed-thermal-detections', 'arrival': 'reconstructed-retrospective',
           'perimeter': 'official-final-perimeter', 'weather': 'historical-weather-model',
           'summary': 'derived-summary', 'daily': 'reconstructed-retrospective',
           'overpasses': 'observed-thermal-detections'}


@lru_cache(maxsize=16)
def _read(path, expected_hash):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError('La capa no coincide con su manifiesto de procedencia.')
    return json.loads(raw)


def load_satellite(layer, directory=None):
    if layer not in FILES:
        raise ValueError('Capa satelital no disponible.')
    root = Path(directory) if directory else ROOT
    manifest = json.loads((root / 'manifest.json').read_text())
    name = FILES[layer]
    receipt = next((entry for entry in manifest['outputs'] if entry['file'] == name), None)
    if not receipt:
        raise ValueError('La capa no tiene huella en el manifiesto.')
    data = _read(str(root / name), receipt['sha256'])
    output = {**data} if isinstance(data, dict) else {'records': data}
    output['_provenance'] = {'dataClass': CLASSES[layer], 'sha256': receipt['sha256'],
                             'bundleCreatedAt': manifest['createdAt'],
                             'incidentId': '2025-CASNF-001684', 'historicalReplay': True}
    if layer in ('arrival', 'daily'):
        output['_provenance']['limitations'] = [
            'Reconstrucción retrospectiva recortada con el perímetro final posterior.',
            'La primera detección térmica asociada no determina la hora exacta de llegada del fuego.',
            'Las celdas con soporte de detección también son reconstruidas; no son perímetros observados.']
    if layer == 'weather':
        output['status'] = 'historical-model'
        output['source'] = 'Open-Meteo Historical Weather API · Best Match · modelo en un punto'
        output['_provenance']['modelSelection'] = 'No se fijó un modelo concreto; Best Match combina IFS, ERA5 y ERA5-Land.'
        output['_provenance']['documentation'] = 'https://open-meteo.com/en/docs/historical-weather-api'
    return output


def weather_at(value, directory=None):
    if not isinstance(value, str):
        raise ValueError('Elige una fecha meteorológica con zona horaria explícita.')
    target = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if target.tzinfo is None:
        raise ValueError('La fecha meteorológica necesita zona horaria.')
    data = load_satellite('weather', directory)
    records = data.get('hours', [])
    if not records:
        raise ValueError('No hay meteorología para el escenario.')
    def difference(row):
        return abs((datetime.fromisoformat(row['timeUtc'].replace('Z', '+00:00')) - target).total_seconds())
    row = min(records, key=difference)
    delta = difference(row)
    if delta > 3600:
        raise ValueError('No hay meteorología histórica a menos de una hora de la fecha elegida.')
    return {**row, 'requestedTimeUtc': target.astimezone(timezone.utc).isoformat(),
            'offsetSeconds': delta, 'source': data['source'], 'point': data['point'],
            'dataClass': 'historical-weather-model', 'windHeightM': 10,
            'relativeHumidityHeightM': 2, '_provenance': data['_provenance'],
            'limitations': 'Un punto de modelo histórico; no es viento medido por cámara ni humedad del combustible.'}


def scenario_weather(value, origin):
    row = weather_at(value)
    if not isinstance(origin, list) or len(origin) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in origin):
        raise ValueError('La semilla necesita longitud y latitud finitas.')
    lon, lat = origin
    point = row['point']
    distance = math.hypot((lon-point['lon'])*math.cos(math.radians(lat)), lat-point['lat'])*111195
    if distance > 50000:
        raise ValueError('El punto meteorológico de Garnet queda a más de 50 km de la semilla.')
    return row
