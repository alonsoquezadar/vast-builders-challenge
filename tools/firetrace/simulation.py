"""Illustrative fire-spread scenario over a real DEM grid (stdlib only).

This is NOT a validated forecast and NOT Rothermel/FARSITE. It is a
minimum-travel-time (Dijkstra) propagation over an 8-neighbour grid where the
local rate of spread is a heuristic product:

    rate = baseSpreadMMin * fuelFactor * W * S                  [m/min]
    W    = exp(KW * windSpeedMps * cos(stepBearing - windToward))
    S    = clamp(exp(KS * tan(slope)), S_MIN, S_MAX)
    time = stepDistanceM / rate                                 [min]

KW, KS, S_MIN, S_MAX are heuristic coefficients chosen only to give a
qualitatively plausible shape (faster downwind and upslope). They were not
fitted to or validated against any fire. Fuel is one uniform hypothetical
factor; no fuel map, moisture, spotting, suppression or weather is modelled.
"""
import heapq
import math

KW = 0.06
KS = 3.0
S_MIN = 0.25
S_MAX = 4.0
M_PER_DEG_LAT = math.pi * 6371000 / 180
GRID_MIN, GRID_MAX = 21, 61
ORIGIN_TOL_DEG = 1e-6
TERRAIN_KEYS = ('terrainSource', 'terrainFetchedAt', 'terrainStatus')

LIMITATIONS = [
    'Escenario ilustrativo con supuestos del operador; no es una predicción ni un perímetro real.',
    'Coeficientes de viento y pendiente heurísticos, sin ajuste ni validación contra incendios reales.',
    'Combustible uniforme hipotético; sin mapa de combustible, humedad, spotting, supresión ni meteorología medida.',
    'Propagación por tiempo mínimo en rejilla de 8 vecinos: la forma tiene sesgo de la rejilla (hasta ~8 %).',
    'Geometría aproximada en escala métrica local (celdas cuadradas); no representa un área observada.',
    'La semilla la elige el operador; no se deriva de Cosmos ni de detección alguna.',
]


def _num(value, name, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} debe ser un número')
    if not math.isfinite(value):
        raise ValueError(f'{name} debe ser finito')
    if not lo <= value <= hi:
        raise ValueError(f'{name} fuera de rango [{lo}, {hi}]')
    return float(value)


def _lonlat(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f'{name} debe ser [lon, lat]')
    lon = _num(value[0], f'{name}[0]', -180, 180)
    lat = _num(value[1], f'{name}[1]', -80, 80)
    return lon, lat


def _validate(data):
    if not isinstance(data, dict):
        raise ValueError('data debe ser un objeto')
    for key in ('origin', 'grid', 'windFromDeg', 'windSpeedMps', 'baseSpreadMMin', 'fuelFactor', 'durationMin'):
        if key not in data:
            raise ValueError(f'falta {key}')
    origin = _lonlat(data['origin'], 'origin')
    grid = data['grid']
    if not isinstance(grid, dict):
        raise ValueError('grid debe ser un objeto')
    grid_origin = _lonlat(grid.get('origin'), 'grid.origin')
    if max(abs(origin[0] - grid_origin[0]), abs(origin[1] - grid_origin[1])) > ORIGIN_TOL_DEG:
        raise ValueError('origin y grid.origin deben coincidir')
    cell = _num(grid.get('cellSizeM'), 'grid.cellSizeM', 10, 200)
    rows = grid.get('elevations')
    if not isinstance(rows, (list, tuple)):
        raise ValueError('grid.elevations debe ser una lista de filas')
    n = len(rows)
    if n < GRID_MIN or n > GRID_MAX or n % 2 == 0:
        raise ValueError(f'la rejilla debe ser cuadrada e impar entre {GRID_MIN} y {GRID_MAX}')
    elev = []
    for r, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) != n:
            raise ValueError('la rejilla debe ser cuadrada (filas de igual longitud)')
        elev.append([_num(z, f'elevations[{r}][{c}]', -500, 9000) for c, z in enumerate(row)])
    params = {
        'windFromDeg': _num(data['windFromDeg'], 'windFromDeg', 0, 360),
        'windSpeedMps': _num(data['windSpeedMps'], 'windSpeedMps', 0, 30),
        'baseSpreadMMin': _num(data['baseSpreadMMin'], 'baseSpreadMMin', 0.1, 30),
        'fuelFactor': _num(data['fuelFactor'], 'fuelFactor', 0.1, 2),
        'durationMin': _num(data['durationMin'], 'durationMin', 1, 60),
    }
    terrain = data.get('terrain')
    if terrain is not None:
        if not isinstance(terrain, dict):
            raise ValueError('terrain debe ser un objeto')
        terrain = {k: str(terrain[k])[:120] for k in TERRAIN_KEYS if isinstance(terrain.get(k), str)}
    return origin, cell, elev, params, terrain


def _propagate(elev, cell, params):
    n = len(elev)
    c0 = n // 2
    toward = math.radians((params['windFromDeg'] + 180.0) % 360.0)
    base = params['baseSpreadMMin'] * params['fuelFactor']
    wind = params['windSpeedMps']
    steps = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr or dc:
                dx, dy = dc * cell, -dr * cell  # rows grow southwards
                steps.append((dr, dc, math.hypot(dx, dy), math.atan2(dx, dy)))
    inf = math.inf
    arrival = [[inf] * n for _ in range(n)]
    arrival[c0][c0] = 0.0
    heap = [(0.0, c0, c0)]
    horizon = params['durationMin']
    while heap:
        t, r, c = heapq.heappop(heap)
        if t > arrival[r][c] or t > horizon:
            continue
        for dr, dc, dist, bearing in steps:
            rr, cc = r + dr, c + dc
            if not (0 <= rr < n and 0 <= cc < n):
                continue
            w = math.exp(KW * wind * math.cos(bearing - toward))
            slope_exponent = KS * (elev[rr][cc] - elev[r][c]) / dist
            s = math.exp(min(math.log(S_MAX), max(math.log(S_MIN), slope_exponent)))
            nt = t + dist / (base * w * s)
            if nt < arrival[rr][cc] and nt <= horizon:
                arrival[rr][cc] = nt
                heapq.heappush(heap, (nt, rr, cc))
    return arrival


def simulate(data):
    """Return an illustrative arrival-time FeatureCollection; raises ValueError on bad input."""
    origin, cell, elev, params, terrain = _validate(data)
    arrival = _propagate(elev, cell, params)
    n = len(elev)
    c0 = n // 2
    lon0, lat0 = origin
    dlat = cell / M_PER_DEG_LAT
    dlon = cell / (M_PER_DEG_LAT * math.cos(math.radians(lat0)))
    features = []
    for r in range(n):
        for c in range(n):
            t = arrival[r][c]
            if not math.isfinite(t):
                continue
            x, y = c - c0, c0 - r
            west, east = lon0 + (x - 0.5) * dlon, lon0 + (x + 0.5) * dlon
            south, north = lat0 + (y - 0.5) * dlat, lat0 + (y + 0.5) * dlat
            features.append({
                'type': 'Feature',
                'geometry': {'type': 'Polygon', 'coordinates': [[
                    [west, south], [east, south], [east, north], [west, north], [west, south]]]},
                'properties': {'arrivalMin': min(round(t, 3), params['durationMin']), 'row': r, 'col': c, 'elevationM': round(elev[r][c], 1)},
            })
    props = {
        'mode': 'illustrative-scenario',
        'validated': False,
        'label': 'SIMULACIÓN ILUSTRATIVA · SUPUESTOS DEL OPERADOR',
        'origin': [lon0, lat0],
        'seedSource': 'operator-selected',
        'grid': {'size': n, 'cellSizeM': cell},
        'cellCount': len(features),
        'boundaryReached': any(f['properties']['row'] in (0, n-1) or f['properties']['col'] in (0, n-1) for f in features),
        'maxArrivalMin': round(max(f['properties']['arrivalMin'] for f in features), 3),
        'assumptions': {
            'inputs': params,
            'fuel': 'uniforme hipotético (un solo factor); no es un dato medido',
            'wind': 'windFromDeg es la dirección meteorológica DESDE donde sopla; valores son supuestos, no mediciones',
            'equation': 'tasa = base·combustible·W·S; W = exp(KW·v·cos(rumbo−haciaDondeSopla)); '
                        'S = clamp(exp(KS·pendiente), S_MIN, S_MAX); tiempo = distancia/tasa; llegada = camino mínimo (Dijkstra, 8 vecinos)',
            'coefficients': {'KW': KW, 'KS': KS, 'S_MIN': S_MIN, 'S_MAX': S_MAX, 'status': 'heurísticos, no validados'},
            'geometry': 'celdas cuadradas en escala métrica local (%.0f m/° de latitud, longitud escalada por cos(lat))' % M_PER_DEG_LAT,
        },
        'limitations': list(LIMITATIONS),
    }
    if terrain:
        props['terrain'] = terrain
    return {'type': 'FeatureCollection', 'features': features, 'properties': props}
