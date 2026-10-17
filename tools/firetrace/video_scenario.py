"""Precomputed MODELLED spread scenario that runs alongside the real Garnet camera video.

    /opt/anaconda3/bin/python3 video_scenario.py            # writes evidence/garnet/video-scenario.json

The initial state is the satellite reconstruction (arrival-reconstructed.geojson, t <= 2025-08-27T23:00:00Z). Only
boundary cells that the reconstruction reached in the preceding 12 h spread; older boundary is not reignited. Spread
reuses ``reconstruction_forecast.propagate`` (multi-source Dijkstra, 8 neighbours, hourly wind, uniform assumed fuel) over
the pinned 200 m DEM and hourly wind. Nothing is tuned to the video or to the later reconstruction.
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import reconstruction_forecast as rf

HERE = Path(__file__).resolve().parent
OUT = HERE / 'evidence' / 'garnet' / 'video-scenario.json'
OVERPASSES = HERE / 'evidence' / 'garnet' / 'satellite' / 'overpasses.json'

SCHEMA = 'firetrace-video-scenario-v1'
START_UTC = '2025-08-27T23:00:00Z'
HORIZON_HOURS = 8
RECENT_HOURS = 12
STEP_SEC = 300
VIDEO_START_UTC = '2025-08-27T23:16:00Z'
VIDEO_END_UTC = '2025-08-28T03:17:00Z'
EVAL_UTC = '2025-08-28T05:19:00Z'
REFERENCE_CLASS = 'later satellite reconstruction; not independent validation'

SOURCE = ('Initial state: satellite reconstruction cells (200 m) with first detection at or before %s. Spread: heuristic rate model '
          'from simulation.py coefficients, pinned 200 m DEM and hourly single-point Open-Meteo wind, via reconstruction_forecast.propagate.' % START_UTC)
ASSUMPTIONS = [
    'The satellite reconstruction is held fixed at its 23:00 UTC state; it is the start of the model, not an observation of the video period.',
    'Only reconstructed boundary cells first detected within the 12 hours before the start spread; older boundary is treated as no longer active.',
    'Spread is integrated by multi-source minimum travel time (Dijkstra, 8 neighbours), hour by hour with the wind of each UTC hour.',
    'Fuel is uniform and assumed (factor 1); there is no fuel map and no fuel moisture.',
    'Wind comes from one model point and is the same across the domain; humidity and temperature do not change the rate.',
    'Arrival times are model outputs; cells are shown only when the model reaches them and are never observed truth.',
]
LIMITATIONS = [
    'Modelled and not validated: the engine is heuristic, uncalibrated, not Rothermel or FARSITE, and has no spotting or suppression.',
    'The existing engine overpredicts the later reconstruction; the output is an illustration of the assumptions, not a validated forecast or a guaranteed upper bound.',
    'The reference for the evaluation is a later satellite reconstruction, not an independent measurement; it cannot grow beyond the final perimeter, so modelled spread outside it counts as over-prediction.',
    'The reconstruction overstates published area (x1.53 on 25 August, x1.38 on 31 August) and its times are first detections, not the exact front.',
    'The initial mask already uses the retrospective final footprint of the reconstruction and its recent boundary is an inferred proxy for the active front.',
    'The DEM is 200 m (5x5 mean) and underestimates local slopes.',
]


def _iso(epoch):
    return datetime.fromtimestamp(int(epoch), timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _epoch(text):
    return int(datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp())


def recent_seed_mask(src, t0, recent_hours=RECENT_HOURS):
    """(initial mask, seed mask): seeds are boundary cells of the initial mask first reached within ``recent_hours`` before t0."""
    initial = src.t_grid <= t0
    seeds = rf._boundary_cells(initial) & (src.t_grid > t0 - recent_hours * 3600)
    return initial, seeds


def run_model(src, t0, horizon_hours=HORIZON_HOURS, recent_hours=RECENT_HOURS):
    """Arrival minutes after t0 for every cell (inf if not reached), plus the initial and seed masks."""
    initial, seeds = recent_seed_mask(src, t0, recent_hours)
    if not seeds.any():
        raise ValueError('No recent boundary cells to spread from; no artificial seed is created.')
    window = rf._weather_window(src, t0)
    phase = (t0 % 3600) / 60.0
    horizon_min = horizon_hours * 60.0
    if phase + horizon_min > 60 * len(window):
        raise ValueError('Hourly wind does not cover the horizon.')
    hourly = [(rec['windFromDeg'], rec['windSpeedMps']) for rec in window]
    arrival = rf.propagate(src.dem, src.grid['cellM'], initial, hourly, phase, horizon_min, seed_mask=seeds)
    return arrival, initial, seeds


def cell_polygon(r, c, grid):
    """Closed WGS84 ring of grid cell (row r, col c); row 0 is the northern edge. Coordinates rounded to 5 decimals."""
    half = grid['cellM'] / 2.0
    cx, cy = grid['x0'] + c * grid['cellM'], grid['y0'] - r * grid['cellM']
    corners = [(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half), (cx - half, cy + half), (cx - half, cy - half)]
    return [[round(x / grid['mPerDegLon'] + grid['lon0'], 5), round(y / grid['mPerDegLat'] + grid['lat0'], 5)] for x, y in corners]


def next_overpass(eval_epoch):
    """The saved overpass whose time is exactly eval_epoch; refuses to substitute another."""
    for over in json.loads(OVERPASSES.read_text())['overpasses']:
        if over['t'] == eval_epoch:
            return over
    raise ValueError('No saved overpass at %s' % _iso(eval_epoch))


def build(src=None):
    src = src or rf.load_sources()
    t0, t_end = _epoch(START_UTC), _epoch(START_UTC) + HORIZON_HOURS * 3600
    t_eval = _epoch(EVAL_UTC)
    grid = src.grid
    cell_ha = grid['cellM'] ** 2 / 10000.0
    arrival, initial, seeds = run_model(src, t0)
    over = next_overpass(t_eval)

    new = np.isfinite(arrival) & ~initial
    rows, cols = np.nonzero(new)
    arr_sec = np.rint(t0 + arrival[rows, cols] * 60.0).astype(np.int64)
    order = np.lexsort((cols, rows, arr_sec))
    rows, cols, arr_sec = rows[order], cols[order], arr_sec[order]
    if len(arr_sec) and (arr_sec.min() < t0 or arr_sec.max() > t_end):
        raise ValueError('Arrival outside the model interval.')

    features = [{'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [cell_polygon(int(r), int(c), grid)]},
                 'properties': {'arrivalSec': int(a), 'cellAreaHa': cell_ha, 'dataClass': 'modelled'}}
                for r, c, a in zip(rows, cols, arr_sec)]

    n_init = int(initial.sum())
    times = list(range(t0, t_end + 1, STEP_SEC))
    if times[-1] != t_end:
        times.append(t_end)
    counts = np.searchsorted(arr_sec, times, side='right')
    series, prev = [], round(n_init * cell_ha, 2)
    for t, n in zip(times, counts):
        total = round((n_init + int(n)) * cell_ha, 2)
        series.append({'timeSec': t, 'modelledAreaHa': total, 'newAreaHa': round(total - n_init * cell_ha, 2), 'incrementAreaHa': round(total - prev, 2)})
        prev = total

    eval_min = (t_eval - t0) / 60.0
    predicted = arrival <= eval_min + 1e-9
    reference = src.t_grid <= t_eval
    metrics = rf.compare(initial, predicted, reference, cell_ha)
    outside = int((predicted & ~src.footprint).sum())
    evaluation = {
        'timeUtc': _iso(t_eval), 'timeSec': t_eval, 'horizonHours': round(eval_min / 60.0, 3),
        'overpass': {'source': over['source'], 'acquiredUtc': over['acquiredUtc'], 'detections': over['detections']},
        'predictedAreaHa': metrics['predictedHa'], 'referenceAreaHa': metrics['referenceHa'], 'initialAreaHa': metrics['initialHa'],
        'iou': metrics['iou'], 'growthIou': metrics['growthIou'],
        'growthPredictedAreaHa': metrics['growthPredictedHa'], 'growthReferenceAreaHa': metrics['growthReferenceHa'],
        'overpredictionHa': metrics['overpredictionHa'], 'underpredictionHa': metrics['underpredictionHa'],
        'modelledOutsideFinalFootprintHa': round(outside * cell_ha, 2),
        'metricDefinition': 'iou = |predicted ∩ reference| / |predicted ∪ reference| over 200 m cells; growthIou is the same restricted to cells outside the initial mask. Predicted = initial + cells reached by the model at the overpass time; reference = reconstruction cells with first detection at or before the same time.',
        'referenceClass': REFERENCE_CLASS,
        'note': 'Both sides are evaluated at exactly the overpass time. The reconstruction is confined to the final perimeter, so this is biased towards over-prediction. If growthReferenceAreaHa is 0 the reconstruction records no new cells by that overpass (the satellite reconstruction is frozen), so growthIou is 0 by construction and says nothing about spread skill.',
    }
    return {
        'type': 'FeatureCollection',
        'features': features,
        'properties': {
            'schema': SCHEMA, 'dataClass': 'modelled', 'validated': False,
            'startUtc': START_UTC, 'endUtc': _iso(t_end), 'startSec': t0, 'endSec': t_end,
            'videoStartUtc': VIDEO_START_UTC, 'videoEndUtc': VIDEO_END_UTC,
            'videoStartSec': _epoch(VIDEO_START_UTC), 'videoEndSec': _epoch(VIDEO_END_UTC),
            'horizonHours': HORIZON_HOURS, 'cellAreaHa': cell_ha, 'initialAreaHa': round(n_init * cell_ha, 2),
            'initialCells': n_init, 'activeSeedCount': int(seeds.sum()),
            'initialBoundaryCells': int(rf._boundary_cells(initial).sum()),
            'recentSeedWindowHours': RECENT_HOURS, 'newCellCount': len(features),
            'source': SOURCE, 'assumptions': ASSUMPTIONS, 'limitations': LIMITATIONS,
            'method': {
                'engine': 'reconstruction_forecast.propagate with seed_mask',
                'integration': rf.METHOD,
                'seedSelection': 'boundary cells of the initial mask whose reconstruction time lies in (start - 12 h, start]',
                'coefficients': {'KW': rf.KW, 'KS': rf.KS, 'S_MIN': rf.S_MIN, 'S_MAX': rf.S_MAX, 'baseSpreadMMin': rf.BASE_SPREAD_M_MIN, 'fuelFactor': rf.FUEL_FACTOR},
                'fuelStatus': 'uniform-assumed-unvalidated', 'tuned': False,
            },
            'initialState': {'source': 'arrival-reconstructed.geojson', 'timeUtc': START_UTC, 'class': 'reconstructed from satellite detections; not a mapped front'},
            'provenance': {
                'arrivalSha256': src.arrival_sha, 'weatherSha256': src.weather_sha,
                'demSha256': src.dem_hashes['npzSha256'], 'demReceiptSha256': src.dem_hashes['receiptSha256'],
                'overpassesSha256': rf._sha256(OVERPASSES.read_bytes()),
                'grid': {'cellM': grid['cellM'], 'nx': grid['nx'], 'ny': grid['ny'], 'x0': grid['x0'], 'y0': grid['y0'],
                         'lat0': grid['lat0'], 'lon0': grid['lon0'], 'mPerDegLat': grid['mPerDegLat'], 'mPerDegLon': grid['mPerDegLon']},
            },
            'bias': {
                'initialFinalPerimeterBias': 'The initial mask is cut from the reconstruction of the final perimeter, which is known only retrospectively; the reference cannot exceed it.',
                'finalFootprintHa': round(int(src.footprint.sum()) * cell_ha, 2),
                'publishedAreaOverstatement': 'x1.53 (25 August), x1.38 (31 August)',
            },
            'series': series, 'evaluation': evaluation,
        },
    }


def write(path=OUT, src=None):
    doc = build(src)
    Path(path).write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')) + '\n')
    return doc


if __name__ == '__main__':
    d = write()
    p = d['properties']
    print('wrote', OUT, 'features', len(d['features']), 'seeds', p['activeSeedCount'], 'eval', p['evaluation']['iou'], file=sys.stdout)
