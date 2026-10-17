"""Download the Garnet Fire satellite and weather inputs into raw/.

Reads the FIRMS key from the FIRMS_MAP_KEY environment variable; the key is
never written to disk. Records every query (key redacted), fetch time and
SHA-256 in raw/queries.json.

    FIRMS_MAP_KEY=... python3 fetch_satellite.py
"""
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / 'raw'
BBOX = '-119.35,36.75,-118.75,37.15'
FIRMS_SOURCES = ['VIIRS_SNPP_SP', 'VIIRS_NOAA20_SP', 'VIIRS_NOAA21_NRT', 'MODIS_SP']
FIRMS_WINDOWS = ['2025-08-24', '2025-08-29', '2025-09-03', '2025-09-08']  # 5-day windows, 24 Aug - 12 Sep
WFIGS = 'https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters/FeatureServer/0/query'
WFIGS_PARAMS = {
    'where': "poly_IncidentName LIKE 'Garnet%' AND attr_POOState='US-CA' AND attr_FireDiscoveryDateTime >= DATE '2025-08-01'",
    'outFields': 'poly_IncidentName,poly_GISAcres,poly_PolygonDateTime,attr_FireDiscoveryDateTime,attr_UniqueFireIdentifier,poly_MapMethod',
    'outSR': '4326',
    'f': 'geojson',
}
OPEN_METEO = 'https://archive-api.open-meteo.com/v1/archive'
OPEN_METEO_PARAMS = {
    'latitude': '36.90', 'longitude': '-119.00', 'start_date': '2025-08-24', 'end_date': '2025-09-13',
    'hourly': 'wind_speed_10m,wind_direction_10m,wind_gusts_10m,relative_humidity_2m,temperature_2m',
    'wind_speed_unit': 'ms', 'timezone': 'UTC',
}


def get(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'FireTrace research (hackathon)'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main():
    key = os.environ.get('FIRMS_MAP_KEY')
    if not key:
        sys.exit('FIRMS_MAP_KEY no está definida.')
    RAW.mkdir(exist_ok=True)
    queries = []

    def save(name, url, public_url, body):
        (RAW / name).write_bytes(body)
        queries.append({'file': name, 'query': public_url, 'fetchedAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                        'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()})

    for source in FIRMS_SOURCES:
        for start in FIRMS_WINDOWS:
            path = f'/api/area/csv/{{MAP_KEY}}/{source}/{BBOX}/5/{start}'
            url = 'https://firms.modaps.eosdis.nasa.gov' + path.replace('{MAP_KEY}', key)
            body = get(url)
            if not body.startswith(b'latitude'):
                sys.exit(f'FIRMS devolvió una respuesta inesperada para {source} {start}.')
            save(f'firms_{source}_{start}.csv', url, 'https://firms.modaps.eosdis.nasa.gov' + path, body)

    url = WFIGS + '?' + urllib.parse.urlencode(WFIGS_PARAMS)
    save('wfigs_perimeter.geojson', url, url, get(url))
    url = OPEN_METEO + '?' + urllib.parse.urlencode(OPEN_METEO_PARAMS)
    save('open_meteo_hourly.json', url, url, get(url))

    (RAW / 'queries.json').write_text(json.dumps({'note': 'FIRMS key redacted as {MAP_KEY}.', 'queries': queries}, indent=1))
    print(f'{len(queries)} archivos en {RAW}')


if __name__ == '__main__':
    main()
