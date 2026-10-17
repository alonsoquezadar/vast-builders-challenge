"""Sample a small metric grid from public Terrarium elevation tiles."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import io
import math
from urllib.request import Request, urlopen

EARTH_RADIUS_M = 6371000
ZOOM = 13
GRID_SIZE = 41
CELL_SIZE_M = 50
TILE_BASE = 'https://elevation-tiles-prod.s3.amazonaws.com/terrarium'


def validate_origin(origin):
    if not isinstance(origin, (list, tuple)) or len(origin) != 2:
        raise ValueError('Selecciona una semilla con longitud y latitud.')
    if not all(isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) for v in origin):
        raise ValueError('Coordenadas de semilla inválidas.')
    if not (-124.6 <= origin[0] <= -114 and 32.3 <= origin[1] <= 42):
        raise ValueError('El escenario está limitado al entorno de California.')
    return list(origin)


def tile_pixel(lon, lat):
    size = 2 ** ZOOM
    x = (lon + 180) / 360 * size
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * size
    tx, ty = math.floor(x), math.floor(y)
    return (tx, ty), (min(255, int((x - tx) * 256)), min(255, int((y - ty) * 256)))


@lru_cache(maxsize=32)
def fetch_tile(key):
    from PIL import Image
    x, y = key
    url = f'{TILE_BASE}/{ZOOM}/{x}/{y}.png'
    with urlopen(Request(url, headers={'User-Agent': 'FireTrace-research/0.1'}), timeout=12) as response:
        raw = response.read(2 * 1024 * 1024)
    image = Image.open(io.BytesIO(raw))
    if image.size != (256, 256):
        raise ValueError('La tesela de elevación tiene dimensiones inesperadas.')
    image = image.convert('RGB')
    return image, {'url': url, 'sha256': hashlib.sha256(raw).hexdigest(),
                   'fetchedAt': datetime.now(timezone.utc).isoformat()}


def terrain_grid(origin, tile_loader=None):
    origin = validate_origin(origin)
    loader = tile_loader or fetch_tile
    locations = []
    half = GRID_SIZE // 2
    for row in range(GRID_SIZE):
        line = []
        north = (half - row) * CELL_SIZE_M
        lat = origin[1] + math.degrees(north / EARTH_RADIUS_M)
        for col in range(GRID_SIZE):
            east = (col - half) * CELL_SIZE_M
            lon = origin[0] + math.degrees(east / (EARTH_RADIUS_M * math.cos(math.radians(origin[1]))))
            line.append(tile_pixel(lon, lat))
        locations.append(line)
    keys = sorted({key for line in locations for key, _ in line})
    with ThreadPoolExecutor(max_workers=4) as executor:
        tiles = dict(zip(keys, executor.map(loader, keys)))
    elevations = []
    for line in locations:
        output = []
        for key, pixel in line:
            red, green, blue = tiles[key][0].getpixel(pixel)
            height = red * 256 + green + blue / 256 - 32768
            if not math.isfinite(height) or not -500 <= height <= 10000:
                raise ValueError('Faltan elevaciones válidas. No se sustituye el relieve por un plano.')
            output.append(round(height, 2))
        elevations.append(output)
    return {'origin': origin, 'cellSizeM': CELL_SIZE_M, 'elevations': elevations,
            'terrainSource': 'AWS Terrarium', 'terrainStatus': 'real-dem',
            'terrainFetchedAt': max((tiles[key][1].get('fetchedAt', '') for key in keys), default='') or datetime.now(timezone.utc).isoformat(),
            'terrainMode': 'fetched', 'tiles': [tiles[key][1] for key in keys],
            'sampling': 'nearest-pixel; local spherical metric grid; rows north-to-south, columns west-to-east',
            'limitations': 'DEM retrieval time is not elevation acquisition time. No fuel, wind or moisture observations.'}
