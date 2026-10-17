"""Build the Garnet Fire satellite and weather layers from raw/.

    python3 build_layers.py            # reads raw/, writes layers next to this file

Needs numpy, scipy and shapely. Observed layers: perimeter, hotspots,
overpasses, weather. Reconstructed layers: arrival-reconstructed and
daily-extent-reconstructed (interpolation of thermal detections inside the
published final perimeter; not a mapped fire front).
"""
import csv
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Point, box, mapping, shape
from shapely.ops import unary_union
from shapely.prepared import prep

HERE = Path(__file__).resolve().parent
RAW = HERE / 'raw'
PDT = timezone(timedelta(hours=-7), 'PDT')
CELL_M = 200
VIIRS_RADIUS_M = 400
FILL_NEIGHBOURS = 6
FOOTPRINT_BUFFER_DEG = 0.01
REPORTED_ACRES = [
    ('2025-08-25T23:59:00-07:00', 4400, 'https://www.fs.usda.gov/r05/sierra/newsroom/releases/garnet-fire-update-august-25-2025'),
    ('2025-08-31T23:59:00-07:00', 18748, 'https://sierranewsonline.com/garnet-fire-update-3/ (prensa local)'),
]
LAT0, LON0 = 36.95, -119.05
M_LAT = 111_320
M_LON = 111_320 * math.cos(math.radians(LAT0))


def xy(lon, lat):
    return (np.asarray(lon) - LON0) * M_LON, (np.asarray(lat) - LAT0) * M_LAT


def lonlat(x, y):
    return x / M_LON + LON0, y / M_LAT + LAT0


def utc(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def pdt(epoch):
    return datetime.fromtimestamp(epoch, PDT).strftime('%Y-%m-%dT%H:%M:%S-07:00')


def acres(n_cells):
    return n_cells * (CELL_M / 1000) ** 2 * 247.105


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, data):
    path = HERE / name
    path.write_text(json.dumps(data, separators=(',', ':'), ensure_ascii=False))
    return path


def load_detections(footprint):
    seen, out = set(), []
    for path in sorted(RAW.glob('firms_*.csv')):
        source = path.stem.split('_', 1)[1].rsplit('_', 1)[0]
        for row in csv.DictReader(path.open()):
            if source.startswith('MODIS') and int(row['confidence']) < 50:
                continue
            if source.startswith('VIIRS') and row['confidence'] == 'l':
                continue
            lon, lat = float(row['longitude']), float(row['latitude'])
            if not footprint.contains(Point(lon, lat)):
                continue
            hhmm = row['acq_time'].zfill(4)
            key = (source, row['latitude'], row['longitude'], row['acq_date'], hhmm)
            if key in seen:
                continue
            seen.add(key)
            when = datetime.strptime(f"{row['acq_date']} {hhmm}", '%Y-%m-%d %H%M').replace(tzinfo=timezone.utc)
            out.append({'lon': lon, 'lat': lat, 't': int(when.timestamp()), 'source': source, 'satellite': row['satellite'],
                        'confidence': row['confidence'], 'frp': float(row['frp']), 'daynight': row['daynight']})
    return sorted(out, key=lambda d: d['t'])


def arrival_grid(perimeter, detections):
    viirs = [d for d in detections if d['source'].startswith('VIIRS')]
    tree = cKDTree(np.c_[xy([d['lon'] for d in viirs], [d['lat'] for d in viirs])])
    times = np.array([d['t'] for d in viirs])
    minx, miny, maxx, maxy = perimeter.bounds
    (x0, x1), (y0, y1) = zip(xy(minx, miny), xy(maxx, maxy))
    inside = prep(perimeter)
    cells = np.array([(x, y) for y in np.arange(y0 + CELL_M / 2, y1, CELL_M) for x in np.arange(x0 + CELL_M / 2, x1, CELL_M)
                      if inside.contains(Point(*lonlat(x, y)))])
    arrival = np.full(len(cells), np.nan)
    for i, hits in enumerate(tree.query_ball_point(cells, VIIRS_RADIUS_M)):
        if hits:
            arrival[i] = times[hits].min()
    observed = ~np.isnan(arrival)
    _, nearest = cKDTree(cells[observed]).query(cells[~observed], k=FILL_NEIGHBOURS)
    arrival[~observed] = np.median(arrival[observed][nearest], axis=1)
    return cells, arrival.astype(int), observed


def cell_polygon(x, y):
    h = CELL_M / 2
    return box(*lonlat(x - h, y - h), *lonlat(x + h, y + h))


def round_geometry(geom):
    def r(c):
        return [r(i) for i in c] if isinstance(c[0], (list, tuple)) else [round(c[0], 5), round(c[1], 5)]
    g = mapping(geom)
    return {'type': g['type'], 'coordinates': r(g['coordinates'])}


def main():
    queries = json.loads((RAW / 'queries.json').read_text())['queries']
    perimeter_fc = json.loads((RAW / 'wfigs_perimeter.geojson').read_text())
    perimeter_props = perimeter_fc['features'][0]['properties']
    perimeter = shape(perimeter_fc['features'][0]['geometry'])
    detections = load_detections(perimeter.buffer(FOOTPRINT_BUFFER_DEG))
    cells, arrival, observed = arrival_grid(perimeter, detections)
    scale = perimeter_props['poly_GISAcres'] / acres(len(cells))
    ordered = np.sort(arrival)

    def acres_by(epoch):
        return round(acres(np.searchsorted(ordered, epoch, side='right')) * scale)

    outputs = []
    outputs.append(write('perimeter.geojson', {
        'type': 'FeatureCollection', 'status': 'observed',
        'source': 'WFIGS Interagency Perimeters (final, IR image interpretation)',
        'features': [{'type': 'Feature', 'geometry': round_geometry(perimeter), 'properties': {
            'incidentId': perimeter_props['attr_UniqueFireIdentifier'], 'gisAcres': perimeter_props['poly_GISAcres'],
            'mapMethod': perimeter_props['poly_MapMethod'], 'polygonDateTime': utc(perimeter_props['poly_PolygonDateTime'] / 1000),
            'fireDiscovery': utc(perimeter_props['attr_FireDiscoveryDateTime'] / 1000)}}]}))

    outputs.append(write('hotspots.geojson', {
        'type': 'FeatureCollection', 'status': 'observed',
        'meaning': 'Thermal anomaly pixel centres at overpass time. Not fire area, front or spread rate.',
        'features': [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [d['lon'], d['lat']]}, 'properties': {
            't': d['t'], 'acquiredUtc': utc(d['t']), 'acquiredPdt': pdt(d['t']), 'source': d['source'], 'satellite': d['satellite'],
            'confidence': d['confidence'], 'frpMW': d['frp'], 'daynight': d['daynight'],
            'pixelM': 1000 if d['source'].startswith('MODIS') else 375}} for d in detections]}))

    passes = {}
    for d in detections:
        passes.setdefault((d['source'], d['t']), []).append(d)
    outputs.append(write('overpasses.json', {'status': 'observed', 'overpasses': [{
        'source': s, 't': t, 'acquiredUtc': utc(t), 'acquiredPdt': pdt(t), 'detections': len(ds),
        'totalFrpMW': round(sum(d['frp'] for d in ds), 1),
        'centroid': [round(float(np.mean([d['lon'] for d in ds])), 5), round(float(np.mean([d['lat'] for d in ds])), 5)]}
        for (s, t), ds in sorted(passes.items(), key=lambda kv: kv[0][1])]}))

    outputs.append(write('arrival-reconstructed.geojson', {
        'type': 'FeatureCollection', 'status': 'reconstructed',
        'meaning': (f'{CELL_M} m cells inside the final perimeter. kind=observed-support: earliest VIIRS detection within '
                    f'{VIIRS_RADIUS_M} m. kind=interpolated: median of the {FILL_NEIGHBOURS} nearest supported cells. '
                    'Arrival times are bounded by overpass times; this is not a mapped front.'),
        'features': [{'type': 'Feature', 'geometry': round_geometry(cell_polygon(x, y)), 'properties': {
            't': int(t), 'arrivalUtc': utc(t), 'arrivalPdt': pdt(t), 'kind': 'observed-support' if o else 'interpolated'}}
            for (x, y), t, o in zip(cells, arrival, observed)]}))

    first_day = datetime.fromtimestamp(int(ordered[0]), PDT).date()
    last_day = datetime.fromtimestamp(int(ordered[-1]), PDT).date()
    daily, day = [], first_day
    while day <= last_day:
        end = int(datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=PDT).timestamp())
        burned = [cell_polygon(x, y) for (x, y), t in zip(cells, arrival) if t <= end]
        daily.append({'type': 'Feature', 'geometry': round_geometry(unary_union(burned).simplify(0.0005)), 'properties': {
            'localDate': day.isoformat(), 'endPdt': pdt(end), 'reconstructedAcres': acres_by(end),
            'newDetections': sum(1 for d in detections if datetime.fromtimestamp(d['t'], PDT).date() == day)}})
        day += timedelta(days=1)
    outputs.append(write('daily-extent-reconstructed.geojson', {
        'type': 'FeatureCollection', 'status': 'reconstructed',
        'meaning': 'Union of arrival cells up to the end of each local day (PDT). Not an official daily perimeter.',
        'features': daily}))

    weather = json.loads((RAW / 'open_meteo_hourly.json').read_text())
    h = weather['hourly']
    outputs.append(write('weather-hourly.json', {
        'status': 'observed-model', 'source': 'Open-Meteo historical archive (ERA5-based reanalysis), one grid point, 10 m',
        'point': {'lon': weather['longitude'], 'lat': weather['latitude'], 'elevationM': weather['elevation']},
        'conventions': 'windFromDeg = meteorological direction the wind blows FROM (same as simulation.py). Times UTC.',
        'hours': [{'timeUtc': h['time'][i] + ':00Z', 'windFromDeg': h['wind_direction_10m'][i], 'windSpeedMps': h['wind_speed_10m'][i],
                   'gustMps': h['wind_gusts_10m'][i], 'rhPct': h['relative_humidity_2m'][i], 'tempC': h['temperature_2m'][i]}
                  for i in range(len(h['time']))]}))

    validation = [{'at': at, 'reportedAcres': rep, 'reconstructedAcres': acres_by(datetime.fromisoformat(at).timestamp()),
                   'source': src} for at, rep, src in REPORTED_ACRES]
    for v in validation:
        v['ratio'] = round(v['reconstructedAcres'] / v['reportedAcres'], 2)
    outputs.append(write('summary.json', {
        'incident': 'Garnet Fire, 2025-CASNF-001684, Sierra National Forest',
        'counts': {'detections': len(detections), 'overpasses': len(passes), 'arrivalCells': len(cells),
                   'cellsWithDetectionSupport': int(observed.sum())},
        'firstDetectionUtc': utc(detections[0]['t']), 'lastDetectionUtc': utc(detections[-1]['t']),
        'parameters': {'cellM': CELL_M, 'viirsRadiusM': VIIRS_RADIUS_M, 'fillNeighbours': FILL_NEIGHBOURS,
                       'footprintBufferDeg': FOOTPRINT_BUFFER_DEG, 'dropped': 'VIIRS confidence l, MODIS confidence < 50',
                       'areaScale': round(scale, 4)},
        'validationAgainstReportedAcres': validation}))

    manifest = {
        'createdAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'inputs': queries,
        'outputs': [{'file': p.name, 'sha256': sha(p), 'bytes': p.stat().st_size} for p in outputs],
        'scripts': [{'file': n, 'sha256': sha(HERE / n)} for n in ('fetch_satellite.py', 'build_layers.py')],
    }
    (HERE / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    print(json.dumps(json.loads((HERE / 'summary.json').read_text()), indent=1))


if __name__ == '__main__':
    main()
