"""Retrospective forecast that starts from the reconstructed Garnet burned mask (NOT from a seed point).

    forecast({'timeUtc': '2025-08-27T23:00:00Z', 'horizonHours': 6 | 12 | 24}) -> GeoJSON FeatureCollection

The initial state is the set of 200 m cells of ``arrival-reconstructed.geojson`` with ``t <= timeUtc``; every
cell of that mask starts burning at minute 0 and the burned front is the mask boundary. Spread uses the same
heuristic rate model and coefficients as ``simulation.py`` (KW, KS, S_MIN, S_MAX imported from it), over the real
200 m DEM of ``forecast_data/`` and the HOURLY wind of ``weather-hourly.json``:

    rate = BASE_SPREAD_M_MIN * FUEL_FACTOR * W * S                      [m/min]
    W    = exp(KW * windSpeedMps(hour) * cos(stepBearing - windToward(hour)))     windToward = windFrom + 180
    S    = clamp(exp(KS * dz / dist), S_MIN, S_MAX)
    arrival = multi-source minimum travel time (Dijkstra, 8 neighbours), integrating hour by hour

This is NOT Rothermel/FARSITE, NOT calibrated and NOT validated. The comparison against the reconstruction
at ``t + horizon`` is retrospective and is not an independent validation.
"""
import hashlib
import io
import itertools
import heapq
import json
import math
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import simulation

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / 'forecast_data'
SOURCE_RECEIPT = 'source-receipt.json'

HORIZONS = (6, 12, 24)
BASE_SPREAD_M_MIN = 4.0
FUEL_FACTOR = 1.0
KW, KS, S_MIN, S_MAX = simulation.KW, simulation.KS, simulation.S_MIN, simulation.S_MAX
CELL_HA_TOLERANCE_M = 5.0  # max distance between a 5-decimal cell centre and the DEM lattice
MAX_RESPONSES, MAX_FIELDS = 64, 8

MODE = 'retrospective-forecast'
METHOD = ('Tiempo mínimo multifuente (Dijkstra, 8 vecinos) desde TODAS las celdas de la máscara reconstruida con t ≤ timeUtc; '
          'tasa = base·combustible·W·S, W = exp(KW·v·cos(rumbo − haciaDondeSopla)), S = clamp(exp(KS·dz/dist), S_MIN, S_MAX); '
          'el viento se toma de la hora UTC vigente y se integra tramo a tramo al cruzar cada hora (FIFO).')

LIMITATIONS = [
    'Retrospectivo y NO validado: se compara contra la reconstrucción satelital, no contra una verdad observada independiente.',
    'Referencia reconstruida: primera detección VIIRS ≤ 400 m, no es el frente exacto; sobrestima el área publicada (×1,53 el 25/08 y ×1,38 el 31/08).',
    'La referencia usa la huella final retrospectivamente: la reconstrucción no puede crecer fuera del perímetro final, así que toda expansión modelada fuera de ella cuenta como sobrepredicción.',
    'La máscara inicial hereda las mismas limitaciones de la reconstrucción; no es un frente cartografiado.',
    'Modelo heurístico con los coeficientes de simulation.py (sin ajuste ni validación); no es Rothermel ni FARSITE; sin spotting, supresión, cortafuegos ni cambios de combustible.',
    'Combustible uniforme (factor 1) supuesto en todo el dominio, también fuera de la huella; no hay mapa de combustible ni humedad del combustible.',
    'Viento de UN solo punto de modelo (Open-Meteo, mejor ajuste histórico, 10 m), igual en todo el dominio y constante dentro de cada hora; no es una medición local. Las ráfagas no se usan.',
    'La humedad relativa y la temperatura son contexto: no modifican la tasa de propagación.',
    'DEM de 200 m (AWS Terrarium z12, media 5×5): subestima pendientes locales; precisión vertical no verificada.',
    'Los resultados dependen de supuestos congelados antes de medir: los parámetros no se ajustaron para mejorar el IoU.',
    'Frente inicial = TODO el borde de la máscara reconstruida tratado como activo. Eso reaviva bordes antiguos que ya no ardían; no es un frente observado y explica en parte la sobrepredicción. No se usó la referencia para elegir qué bordes están activos.',
]


class ForecastDataError(RuntimeError):
    """A pinned local source is missing or fails its SHA-256 check (server-side problem, not a bad request)."""


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _read_checked(path, expected_sha, label):
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ForecastDataError(f'Falta la fuente {label}: {path.name} ({error.strerror}); no hay sustituto plano.') from error
    digest = _sha256(raw)
    if digest != expected_sha:
        raise ForecastDataError(f'La fuente {label} ({path.name}) no coincide con su SHA-256 fijado.')
    return raw, digest


def _iso(epoch):
    return datetime.fromtimestamp(int(epoch), timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


_tokens = itertools.count()


class Sources:
    """Verified, immutable inputs shared between requests."""

    def __init__(self, dem, grid, dem_hashes, t_grid, footprint, arrival_sha, weather, weather_sha, weather_meta, receipt):
        self.dem, self.grid, self.dem_hashes = dem, grid, dem_hashes
        self.t_grid, self.footprint = t_grid, footprint
        self.arrival_sha, self.weather, self.weather_sha, self.weather_meta = arrival_sha, weather, weather_sha, weather_meta
        self.receipt = receipt
        self.token = next(_tokens)
        self.first_t, self.last_t = float(t_grid[footprint].min()), float(t_grid[footprint].max())
        self.dem.setflags(write=False)
        self.t_grid.setflags(write=False)
        self.footprint.setflags(write=False)


def load_sources(arrival_path=None, weather_path=None, data_dir=None, receipt_path=None):
    """Load and verify every source against the SHA-256 values pinned in forecast_data/source-receipt.json."""
    data_dir = Path(data_dir) if data_dir else DATA_DIR
    receipt = json.loads(Path(receipt_path or data_dir / SOURCE_RECEIPT).read_text())
    arrival_path = Path(arrival_path or HERE / receipt['arrival']['path'])
    weather_path = Path(weather_path or HERE / receipt['weather']['path'])

    dem_receipt_raw, dem_receipt_sha = _read_checked(data_dir / receipt['demReceipt']['file'], receipt['demReceipt']['sha256'], 'recibo DEM')
    dem_receipt = json.loads(dem_receipt_raw)
    npz_raw, npz_sha = _read_checked(data_dir / receipt['dem']['file'], receipt['dem']['sha256'], 'DEM')
    if dem_receipt.get('npzSha256') != npz_sha or dem_receipt.get('status') != 'real-dem':
        raise ForecastDataError('El recibo del DEM no corresponde al DEM cargado o no es un DEM real.')
    spec = dem_receipt['grid']
    ny, nx, cell = int(spec['ny']), int(spec['nx']), float(spec['cellM'])
    dem = np.load(io.BytesIO(npz_raw))['elevation'].astype(np.float64)
    if dem.shape != (ny, nx) or not np.isfinite(dem).all() or dem.min() < -100 or dem.max() > 6000:
        raise ForecastDataError('DEM inválido (forma o valores implausibles); se rechaza sin sustituir por terreno plano.')
    if float(dem.max() - dem.min()) < 50:
        raise ForecastDataError('DEM prácticamente plano: se rechaza (sin sustituto plano).')

    arrival_raw, arrival_sha = _read_checked(arrival_path, receipt['arrival']['sha256'], 'llegada reconstruida')
    weather_raw, weather_sha = _read_checked(weather_path, receipt['weather']['sha256'], 'meteorología')

    proj = spec['projection']
    m_lat, m_lon, lat0, lon0 = float(proj['mPerDegLat']), float(proj['mPerDegLon']), float(proj['lat0']), float(proj['lon0'])
    grid = {'cellM': cell, 'nx': nx, 'ny': ny, 'x0': float(spec['x0']), 'y0': float(spec['y0']),
            'lat0': lat0, 'lon0': lon0, 'mPerDegLat': m_lat, 'mPerDegLon': m_lon}

    arrivals = json.loads(arrival_raw)
    t_grid = np.full((ny, nx), np.inf)
    for feature in arrivals['features']:
        ring = np.asarray(feature['geometry']['coordinates'][0], float)
        lo, la = (ring.min(0) + ring.max(0)) / 2
        col = (((lo - lon0) * m_lon) - grid['x0']) / cell
        row = (grid['y0'] - ((la - lat0) * m_lat)) / cell
        r, c = int(round(row)), int(round(col))
        if max(abs(row - r), abs(col - c)) * cell > CELL_HA_TOLERANCE_M or not (0 <= r < ny and 0 <= c < nx):
            raise ForecastDataError('Una celda reconstruida no coincide con la rejilla del DEM.')
        if np.isfinite(t_grid[r, c]):
            raise ForecastDataError('Celda reconstruida duplicada en la rejilla del DEM.')
        t_grid[r, c] = float(feature['properties']['t'])
    footprint = np.isfinite(t_grid)
    if footprint.sum() != len(arrivals['features']) or not footprint.any():
        raise ForecastDataError('Reconstrucción vacía o inconsistente.')

    weather_doc = json.loads(weather_raw)
    hours = {}
    for rec in weather_doc['hours']:
        stamp = datetime.fromisoformat(rec['timeUtc'].replace('Z', '+00:00')).timestamp()
        if stamp % 3600:
            raise ForecastDataError('La meteorología debe ser horaria exacta.')
        hours[int(stamp)] = {k: rec[k] for k in ('timeUtc', 'windFromDeg', 'windSpeedMps', 'gustMps', 'rhPct', 'tempC')}
    meta = {'status': weather_doc.get('status'), 'source': weather_doc.get('source'), 'point': weather_doc.get('point'),
            'firstUtc': _iso(min(hours)), 'lastUtc': _iso(max(hours))}
    dem_hashes = {'npzSha256': npz_sha, 'receiptSha256': dem_receipt_sha,
                  'tilesDigestSha256': _sha256(''.join(t['sha256'] for t in dem_receipt['tiles']).encode()),
                  'tileCount': len(dem_receipt['tiles']), 'source': dem_receipt['source'],
                  'resampling': dem_receipt['resampling'], 'stats': dem_receipt['stats']}
    return Sources(dem, grid, dem_hashes, t_grid, footprint, arrival_sha, hours, weather_sha, meta, receipt)


_lock = threading.RLock()
_default_sources = None
_fields = OrderedDict()
_responses = OrderedDict()


def _sources():
    global _default_sources
    with _lock:
        if _default_sources is None:
            _default_sources = load_sources()
        return _default_sources


def reset_caches():
    global _default_sources
    with _lock:
        _default_sources = None
        _fields.clear()
        _responses.clear()


# --- propagation (pure) ---------------------------------------------------------------------------------------------

_DIRECTIONS = [(dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc]


def wind_factors(wind_from_deg, wind_speed_mps, cell):
    """Per-direction W for the 8 steps; windFrom is meteorological (blows FROM), spread goes TO windFrom + 180."""
    toward = math.radians((wind_from_deg + 180.0) % 360.0)
    return [math.exp(KW * wind_speed_mps * math.cos(math.atan2(dc * cell, -dr * cell) - toward)) for dr, dc in _DIRECTIONS]


def propagate(elevation, cell, initial_mask, hourly_wind, phase_min, horizon_min,
              base_spread=BASE_SPREAD_M_MIN, fuel_factor=FUEL_FACTOR, seed_mask=None):
    """Minutes after the initial instant at which each cell burns (0 inside the mask, inf if not reached in time).

    ``hourly_wind[i]`` = (windFromDeg, windSpeedMps) for the i-th UTC hour; the initial instant lies ``phase_min``
    minutes after the start of hour 0. Crossing an edge integrates distance hour by hour, so travel time is FIFO and
    Dijkstra is exact. Rows run north to south.

    ``seed_mask`` (optional, subset of the mask) restricts which boundary cells start spreading; default: the whole boundary.
    """
    elevation = np.asarray(elevation, float)
    mask = np.asarray(initial_mask, bool)
    ny, nx = elevation.shape
    if mask.shape != elevation.shape:
        raise ValueError('máscara y DEM con formas distintas')
    if not mask.any():
        raise ValueError('la máscara inicial está vacía')
    if not np.isfinite(elevation).all():
        raise ValueError('DEM con valores no finitos')
    if not hourly_wind or not 0 <= phase_min < 60 or horizon_min <= 0 or phase_min + horizon_min > 60 * len(hourly_wind):
        raise ValueError('el viento horario no cubre el horizonte')
    width = nx + 2
    padded = np.full((ny + 2, width), np.nan)
    padded[1:-1, 1:-1] = elevation
    base = base_spread * fuel_factor
    offsets, dists, factors = [], [], []
    for dr, dc in _DIRECTIONS:
        dist = math.hypot(dr, dc) * cell
        shifted = np.full_like(padded, np.nan)
        shifted[1 - dr: ny + 1 - dr, 1 - dc: nx + 1 - dc] = elevation  # shifted[p] = elevation of the neighbour at p + (dr, dc)
        with np.errstate(invalid='ignore'):
            slope = np.clip(np.exp(KS * (shifted - padded) / dist), S_MIN, S_MAX)
        slope = np.where(np.isfinite(shifted) & np.isfinite(padded), slope, 0.0)
        offsets.append(dr * width + dc)
        dists.append(dist)
        factors.append((base * slope).ravel().tolist())
    wind = [wind_factors(f, v, cell) for f, v in hourly_wind]
    n_hours = len(wind)

    pm = np.zeros((ny + 2, width), bool)
    pm[1:-1, 1:-1] = mask
    active = _boundary_cells(mask)  # interior mask cells cannot start any new burn
    if seed_mask is not None:
        seed_mask = np.asarray(seed_mask, bool)
        if seed_mask.shape != mask.shape or (seed_mask & ~mask).any():
            raise ValueError('seed_mask debe ser un subconjunto de la máscara inicial')
        active = active & seed_mask
    seeds = np.flatnonzero(np.pad(active, 1).ravel())
    arrival = np.where(pm, 0.0, np.inf).ravel().tolist()
    inf = math.inf
    heap = [(0.0, int(s)) for s in seeds]
    heapq.heapify(heap)
    push, pop = heapq.heappush, heapq.heappop
    ks = range(len(_DIRECTIONS))
    while heap:
        t, u = pop(heap)
        if t > arrival[u]:
            continue
        for k in ks:
            f = factors[k][u]
            if f <= 0.0:
                continue
            v = u + offsets[k]
            if arrival[v] <= t:
                continue
            rem = dists[k]
            m = phase_min + t
            h = int(m // 60)
            while True:
                rate = f * wind[h][k]
                seg_end = (h + 1) * 60.0
                can = rate * (seg_end - m)
                if can >= rem:
                    nm = m + rem / rate
                    break
                rem -= can
                m = seg_end
                h += 1
                if h >= n_hours or m - phase_min > horizon_min:
                    nm = inf
                    break
            nt = nm - phase_min
            if nt <= horizon_min and nt < arrival[v]:
                arrival[v] = nt
                push(heap, (nt, v))
    return np.asarray(arrival).reshape(ny + 2, width)[1:-1, 1:-1].copy()


# --- metrics (pure) -------------------------------------------------------------------------------------------------

def compare(initial, predicted, reference, cell_ha):
    """IoU / growth IoU / hectares from boolean masks; every mask is on the same grid."""
    initial, predicted, reference = (np.asarray(m, bool) for m in (initial, predicted, reference))
    inter = int((predicted & reference).sum())
    union = int((predicted | reference).sum())
    growth_p, growth_r = predicted & ~initial, reference & ~initial
    g_inter, g_union = int((growth_p & growth_r).sum()), int((growth_p | growth_r).sum())
    metrics = {
        'iou': round(inter / union, 4) if union else None,
        'growthIou': round(g_inter / g_union, 4) if g_union else None,
        'intersectionHa': round(inter * cell_ha, 2),
        'overpredictionHa': round(int((predicted & ~reference).sum()) * cell_ha, 2),
        'underpredictionHa': round(int((reference & ~predicted).sum()) * cell_ha, 2),
        'predictedHa': round(int(predicted.sum()) * cell_ha, 2),
        'referenceHa': round(int(reference.sum()) * cell_ha, 2),
        'initialHa': round(int(initial.sum()) * cell_ha, 2),
        'growthPredictedHa': round(int(growth_p.sum()) * cell_ha, 2),
        'growthReferenceHa': round(int(growth_r.sum()) * cell_ha, 2),
        'growthIntersectionHa': round(g_inter * cell_ha, 2),
        'growthIouReason': None if g_union else 'Sin crecimiento ni modelado ni de referencia desde el estado inicial: el IoU de crecimiento no está definido.',
    }
    return metrics


# --- geometry -------------------------------------------------------------------------------------------------------

def _rectangles(mask):
    """Row runs merged vertically into (xmin, ymin, xmax, ymax) rectangles in cell-index space (y up = -row); far fewer than cells."""
    padded = np.pad(mask, ((0, 0), (1, 1))).astype(np.int8)
    edges = np.diff(padded, axis=1)
    open_runs, rects = {}, []
    for r in range(mask.shape[0]):
        starts, ends = np.flatnonzero(edges[r] == 1), np.flatnonzero(edges[r] == -1)
        current = {}
        for c0, c1 in zip(starts.tolist(), ends.tolist()):
            r0 = open_runs.pop((c0, c1), r)
            current[(c0, c1)] = r0
        for (c0, c1), r0 in open_runs.items():
            rects.append((c0 - 0.5, -r + 0.5, c1 - 0.5, -r0 + 0.5))
        open_runs = current
    for (c0, c1), r0 in open_runs.items():
        rects.append((c0 - 0.5, -mask.shape[0] + 0.5, c1 - 0.5, -r0 + 0.5))
    return rects


def mask_geometry(mask, grid):
    """Dissolved outline (Polygon/MultiPolygon) of the True cells; coordinates rounded to 5 decimals."""
    import shapely
    from shapely.geometry.polygon import orient
    if not mask.any():
        return {'type': 'MultiPolygon', 'coordinates': []}
    boxes = shapely.box(*zip(*_rectangles(mask)))
    merged = shapely.union_all(boxes).simplify(1e-9, preserve_topology=True)
    polys = [merged] if merged.geom_type == 'Polygon' else list(merged.geoms)
    cell = grid['cellM']

    def ring(coords):
        out = []
        for c, negr in coords:
            x, y = grid['x0'] + c * cell, grid['y0'] + negr * cell
            out.append([round(x / grid['mPerDegLon'] + grid['lon0'], 5), round(y / grid['mPerDegLat'] + grid['lat0'], 5)])
        return out

    coordinates = []
    for poly in polys:
        poly = orient(poly)
        coordinates.append([ring(poly.exterior.coords)] + [ring(r.coords) for r in poly.interiors])
    if len(coordinates) == 1:
        return {'type': 'Polygon', 'coordinates': coordinates[0]}
    return {'type': 'MultiPolygon', 'coordinates': coordinates}


# --- request handling -----------------------------------------------------------------------------------------------

def parse_request(data):
    if not isinstance(data, dict):
        raise ValueError('La solicitud debe ser un objeto JSON.')
    raw = data.get('timeUtc')
    if not isinstance(raw, str) or not 10 < len(raw) <= 40:
        raise ValueError('timeUtc debe ser una fecha ISO 8601 con zona horaria.')
    try:
        when = datetime.fromisoformat(raw.strip().replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('timeUtc debe ser una fecha ISO 8601 con zona horaria.') from None
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError('timeUtc debe incluir zona horaria (por ejemplo 2025-08-27T23:00:00Z).')
    horizon = data.get('horizonHours')
    if isinstance(horizon, bool) or not isinstance(horizon, (int, float)) or horizon not in HORIZONS:
        raise ValueError(f'horizonHours debe ser uno de {list(HORIZONS)}.')
    return int(round(when.timestamp())), int(horizon)


def _weather_window(src, t0):
    """Consecutive hourly records starting at the hour that contains t0 (list), stopping at the first gap."""
    hour = t0 - t0 % 3600
    window = []
    while hour in src.weather and len(window) < 26:
        window.append(src.weather[hour])
        hour += 3600
    return window


def _field(src, t0):
    """Arrival field (minutes, up to min(24 h, weather coverage)) for initial instant t0; cached per t0."""
    key = (src.token, t0)
    with _lock:
        cached = _fields.get(key)
        if cached is not None:
            _fields.move_to_end(key)
            return cached
        initial = src.t_grid <= t0
        if not initial.any():
            first = _iso(src.first_t)
            raise ValueError(f'No hay área inicial reconstruida en {_iso(t0)}: la primera celda llega en {first}. '
                             'Selecciona una hora con área inicial; no se genera una semilla artificial.')
        window = _weather_window(src, t0)
        phase = (t0 % 3600) / 60.0
        horizon = min(24 * 60.0, len(window) * 60.0 - phase)
        if not window or horizon < min(HORIZONS) * 60:
            raise ValueError('La meteorología horaria del archivo (Open-Meteo, hasta %s) no cubre ni 6 h desde %s.'
                             % (src.weather_meta['lastUtc'], _iso(t0)))
        hourly = [(rec['windFromDeg'], rec['windSpeedMps']) for rec in window]
        arrival = propagate(src.dem, src.grid['cellM'], initial, hourly, phase, horizon)
        arrival.setflags(write=False)
        entry = {'arrival': arrival, 'initial': initial, 'window': window, 'phase': phase, 'horizonMin': horizon}
        _fields[key] = entry
        while len(_fields) > MAX_FIELDS:
            _fields.popitem(last=False)
        return entry


def _boundary_cells(mask):
    """Mask cells with at least one in-grid 8-neighbour outside the mask (the seeds of the propagation)."""
    ny, nx = mask.shape
    unburned = np.pad(~mask, 1, constant_values=False)
    touches = np.zeros_like(mask)
    for dr, dc in _DIRECTIONS:
        touches |= unburned[1 + dr: ny + 1 + dr, 1 + dc: nx + 1 + dc]
    return mask & touches


def _edge_touched(mask):
    return bool(mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any())


def _feature(role, data_class, label, mask, grid, cell_ha):
    return {'type': 'Feature', 'geometry': mask_geometry(mask, grid),
            'properties': {'role': role, 'dataClass': data_class, 'label': label,
                           'cellCount': int(mask.sum()), 'areaHa': round(int(mask.sum()) * cell_ha, 2)}}


def _build(src, t0, horizon):
    field = _field(src, t0)
    if horizon * 60 > field['horizonMin'] + 1e-9:
        raise ValueError('La meteorología horaria del archivo (Open-Meteo, hasta %s) no cubre %d h desde %s.'
                         % (src.weather_meta['lastUtc'], horizon, _iso(t0)))
    grid = src.grid
    cell_ha = grid['cellM'] ** 2 / 10000.0
    valid = t0 + horizon * 3600
    initial = field['initial']
    predicted = field['arrival'] <= horizon * 60 + 1e-9
    reference_available = valid <= src.last_t
    reference = (src.t_grid <= valid) if reference_available else None

    features = [
        _feature('initial-extent', 'reconstructed', 'Máscara inicial reconstruida', initial, grid, cell_ha),
        _feature('modeled-extent', 'modeled', 'Extensión modelada', predicted, grid, cell_ha),
    ]
    if reference_available:
        features += [
            _feature('reference-extent', 'reconstructed', 'Referencia reconstruida', reference, grid, cell_ha),
            _feature('overlap', 'modeled-comparison', 'Coincidencia', predicted & reference, grid, cell_ha),
            _feature('overprediction', 'modeled-comparison', 'Exceso modelado', predicted & ~reference, grid, cell_ha),
            _feature('underprediction', 'modeled-comparison', 'Defecto modelado', reference & ~predicted, grid, cell_ha),
        ]
        metrics = compare(initial, predicted, reference, cell_ha)
    else:
        metrics = {k: None for k in ('iou', 'growthIou', 'intersectionHa', 'overpredictionHa', 'underpredictionHa', 'referenceHa',
                                     'growthPredictedHa', 'growthReferenceHa', 'growthIntersectionHa')}
        metrics.update({
            'predictedHa': round(int(predicted.sum()) * cell_ha, 2), 'initialHa': round(int(initial.sum()) * cell_ha, 2),
            'growthPredictedHa': round(int((predicted & ~initial).sum()) * cell_ha, 2),
            'growthIouReason': 'Sin referencia reconstruida en %s: el archivo de llegadas termina en %s; no se asume un fuego congelado.'
                               % (_iso(valid), _iso(src.last_t))})

    window = field['window']
    n_used = int(math.ceil((field['phase'] + horizon * 60) / 60.0))
    used = [dict(rec, windToDeg=(rec['windFromDeg'] + 180) % 360) for rec in window[:n_used]]
    first = used[0]
    weather = {
        'windFromDeg': first['windFromDeg'], 'windToDeg': first['windToDeg'], 'windSpeedMps': first['windSpeedMps'],
        'gustMps': first['gustMps'], 'rhPct': first['rhPct'], 'tempC': first['tempC'], 'timeUtc': first['timeUtc'],
        'hoursUsed': len(used), 'hourly': used, 'dataClass': 'model-single-point', 'source': src.weather_meta['source'],
        'point': src.weather_meta['point'], 'convention': 'windFromDeg = dirección meteorológica DESDE donde sopla (grados); la propagación va hacia windFromDeg + 180.',
        'note': 'Tramo horario constante: se integra hora a hora; rhPct, tempC y gustMps son contexto y no cambian la tasa.',
    }
    outside_hist = int((predicted & ~src.footprint).sum())
    edge = _boundary_cells(initial)
    recent = edge & (src.t_grid > t0 - 12 * 3600)
    return {
        'type': 'FeatureCollection',
        'features': features,
        'properties': {
            'mode': MODE, 'validated': False,
            'label': 'PRONÓSTICO RETROSPECTIVO · DESDE EL FRENTE RECONSTRUIDO · NO VALIDADO',
            'timeUtc': _iso(t0), 'validUtc': _iso(valid), 'horizonHours': horizon,
            'referenceAvailable': reference_available,
            'referenceThroughUtc': _iso(src.last_t),
            'domainBoundaryReached': _edge_touched(predicted),
            'domainBoundaryReachedAtInitial': _edge_touched(initial),
            'metrics': metrics,
            'diagnostics': {
                'modeledOutsideFinalFootprintHa': round(outside_hist * cell_ha, 2),
                'finalFootprintHa': round(int(src.footprint.sum()) * cell_ha, 2),
                'initialCells': int(initial.sum()), 'modeledCells': int(predicted.sum()),
                'initialFrontCells': int(edge.sum()), 'initialFrontCellsArrivedLast12h': int(recent.sum()),
                'initialFrontNote': 'Todo el borde de la máscara inicial es fuente de propagación; solo las celdas llegadas en las últimas 12 h (según la reconstrucción) podrían ser frente reciente. El resto reaviva bordes antiguos.',
                'note': 'La huella final se conoce solo retrospectivamente; el pronóstico no se recorta a ella.',
            },
            'weather': weather,
            'assumptions': {
                'seed': 'Sin semilla: la propagación parte de todas las celdas de arrival-reconstructed con t ≤ timeUtc; su borde es el frente inicial.',
                'baseSpreadMMin': BASE_SPREAD_M_MIN, 'fuelFactor': FUEL_FACTOR,
                'fuel': 'uniforme (factor 1) supuesto; sin mapa de combustible y sin humedad del combustible',
                'coefficients': {'KW': KW, 'KS': KS, 'S_MIN': S_MIN, 'S_MAX': S_MAX, 'origin': 'simulation.py', 'status': 'heurísticos, no validados'},
                'wind': 'viento horario histórico (Open-Meteo, un punto), constante en cada hora UTC; windFrom meteorológico, propagación hacia +180°',
                'relativeHumidity': 'contexto; no modifica la propagación',
                'neighbours': 8, 'spotting': False, 'suppression': False,
                'equation': METHOD,
                'frozenBeforeMeasurement': True,
            },
            'limitations': list(LIMITATIONS),
            'provenance': {
                'method': METHOD,
                'fuelStatus': 'uniform-assumed-unvalidated',
                'validation': 'retrospective-forecast-not-independently-validated',
                'demSha256': src.dem_hashes['npzSha256'], 'demReceiptSha256': src.dem_hashes['receiptSha256'],
                'dem': src.dem_hashes,
                'arrivalSha256': src.arrival_sha, 'weatherSha256': src.weather_sha,
                'inputHashes': {'arrival-reconstructed.geojson': src.arrival_sha, 'weather-hourly.json': src.weather_sha,
                                'dem-200m.npz': src.dem_hashes['npzSha256']},
                'grid': {'cellM': grid['cellM'], 'nx': grid['nx'], 'ny': grid['ny'], 'x0': grid['x0'], 'y0': grid['y0'],
                         'projection': {'lat0': grid['lat0'], 'lon0': grid['lon0'], 'mPerDegLat': grid['mPerDegLat'], 'mPerDegLon': grid['mPerDegLon']},
                         'cellAreaHa': cell_ha, 'extentKm': [round(grid['nx'] * grid['cellM'] / 1000, 1), round(grid['ny'] * grid['cellM'] / 1000, 1)]},
                'referenceBias': 'La reconstrucción supera el área publicada ×1,53 (25/08) y ×1,38 (31/08); la primera detección no es el instante exacto de llegada.',
                'weatherSource': src.weather_meta['source'],
            },
        },
    }


def forecast(data, sources=None):
    """Pure function of (timeUtc, horizonHours) and the pinned sources; ValueError on bad input, ForecastDataError on bad sources."""
    t0, horizon = parse_request(data)
    src = sources or _sources()
    key = (src.token, t0, horizon)
    with _lock:
        text = _responses.get(key)
        if text is not None:
            _responses.move_to_end(key)
        else:
            text = json.dumps(_build(src, t0, horizon), ensure_ascii=False, separators=(',', ':'))
            _responses[key] = text
            while len(_responses) > MAX_RESPONSES:
                _responses.popitem(last=False)
    return json.loads(text)  # a fresh object on every call; nothing mutable is shared with the cache
