"""Real DEM for the Garnet domain from AWS Terrarium tiles (zoom 12), resampled to the 200 m grid.

    python3 dem.py            # fetch missing tiles into dem/tiles, rebuild dem/dem-200m.npz and dem/receipt.json
    python3 dem.py --offline  # rebuild from cached tiles only

Terrarium is a global composite; US coverage comes mostly from USGS 3DEP. Per-cell value = mean of a 5x5 nearest-pixel
sampling inside the 200 m cell (a smoothed elevation, so 200 m slopes are underestimated relative to fine-scale terrain).
Tile retrieval time is not elevation acquisition time. Vertical accuracy is not verified here.
"""
import hashlib
import io
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np

from grid import Grid, to_lonlat

HERE = Path(__file__).resolve().parent
DEM_DIR = HERE / 'dem'
TILE_DIR = DEM_DIR / 'tiles'
ZOOM = 12
TILE_BASE = 'https://elevation-tiles-prod.s3.amazonaws.com/terrarium'
# Covers every Garnet satellite layer feature (arrival bbox -119.186..-118.971, 36.857..37.051) with ~5 km margin.
DOMAIN = dict(lon_min=-119.245, lon_max=-118.915, lat_min=36.815, lat_max=37.095)


def tile_xy(lon, lat):
    n = 2 ** ZOOM
    x = (np.asarray(lon, float) + 180) / 360 * n
    y = (1 - np.arcsinh(np.tan(np.radians(lat))) / math.pi) / 2 * n
    return x, y


def fetch_tile(tx, ty, offline=False):
    path = TILE_DIR / f'{ZOOM}_{tx}_{ty}.png'
    if not path.exists():
        if offline:
            raise FileNotFoundError(path)
        url = f'{TILE_BASE}/{ZOOM}/{tx}/{ty}.png'
        with urlopen(Request(url, headers={'User-Agent': 'FireTrace-research/0.1'}), timeout=30) as r:
            raw = r.read(4 * 1024 * 1024)
        TILE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return path


def load_height(path):
    from PIL import Image
    rgb = np.asarray(Image.open(path).convert('RGB'), dtype=np.float64)
    if rgb.shape[:2] != (256, 256):
        raise ValueError(f'unexpected tile size {path}')
    return rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768


def build(offline=False):
    grid = Grid(**DOMAIN)
    lon, lat = grid.centers_lonlat()
    offs = np.linspace(-80, 80, 5)
    acc = np.zeros(grid.size)
    tiles = {}
    heights = {}
    for ox in offs:
        for oy in offs:
            x, y = grid.centers_xy()
            lo, la = to_lonlat(x + ox, y + oy)
            fx, fy = tile_xy(lo, la)
            tx, ty = np.floor(fx).astype(int), np.floor(fy).astype(int)
            px = np.minimum(255, ((fx - tx) * 256).astype(int))
            py = np.minimum(255, ((fy - ty) * 256).astype(int))
            for key in set(zip(tx.tolist(), ty.tolist())):
                if key not in heights:
                    heights[key] = load_height(fetch_tile(*key, offline=offline))
            vals = np.empty(grid.size)
            for key in set(zip(tx.tolist(), ty.tolist())):
                m = (tx == key[0]) & (ty == key[1])
                vals[m] = heights[key][py[m], px[m]]
            acc += vals
    elev = (acc / (len(offs) ** 2)).reshape(grid.ny, grid.nx)
    if not np.isfinite(elev).all() or elev.min() < -100 or elev.max() > 6000:
        raise ValueError('implausible DEM values; refusing to emit (no flat substitution)')
    receipts = []
    for (tx, ty) in sorted(heights):
        p = TILE_DIR / f'{ZOOM}_{tx}_{ty}.png'
        receipts.append({'url': f'{TILE_BASE}/{ZOOM}/{tx}/{ty}.png', 'file': str(p.relative_to(HERE)),
                         'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size})
    DEM_DIR.mkdir(exist_ok=True)
    np.savez_compressed(DEM_DIR / 'dem-200m.npz', elevation=elev.astype(np.float32))
    receipt = {
        'schema': 'firetrace-assimilation-dem-v1', 'status': 'real-dem', 'source': 'AWS Terrarium (Mapzen) z12 tiles',
        'builtAt': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'grid': grid.spec(),
        'resampling': 'mean of 5x5 nearest-pixel samples (+-80 m) per 200 m cell; rows north-to-south', 'tiles': receipts,
        'stats': {'minM': round(float(elev.min()), 1), 'maxM': round(float(elev.max()), 1), 'meanM': round(float(elev.mean()), 1)},
        'npzSha256': hashlib.sha256((DEM_DIR / 'dem-200m.npz').read_bytes()).hexdigest(),
        'limitations': ['Retrieval time is not elevation acquisition time.', 'Vertical accuracy not verified.',
                        '200 m averaging underestimates local slopes.'],
    }
    (DEM_DIR / 'receipt.json').write_text(json.dumps(receipt, indent=1) + '\n')
    return grid, elev, receipt


def load():
    receipt = json.loads((DEM_DIR / 'receipt.json').read_text())
    elev = np.load(DEM_DIR / 'dem-200m.npz')['elevation'].astype(float)
    return Grid.from_spec(receipt['grid']), elev, receipt


if __name__ == '__main__':
    g, e, r = build(offline='--offline' in sys.argv)
    print(g.nx, g.ny, r['stats'], len(r['tiles']), 'tiles')
