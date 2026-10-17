"""Rebuild the extended 200 m forecast DEM (about 12 km margin around the Garnet footprint) from real Terrarium z12 tiles.

    python3 forecast_data/build_dem.py --tiles-dir camera_assimilation/assimilation/dem/tiles

Same projection, lattice phase and resampling as camera_assimilation/assimilation/dem.py (mean of 5x5 nearest-pixel
samples, +-80 m, per 200 m cell). Tiles missing from --tiles-dir are fetched once from AWS into forecast_data/tiles-extra/;
the forecast itself never touches the network. No flat or synthetic substitute is ever produced.
"""
import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ZOOM = 12
TILE_BASE = 'https://elevation-tiles-prod.s3.amazonaws.com/terrarium'
LAT0, LON0, M_LAT, M_LON, CELL = 36.95, -119.05, 111_320.0, 88_962.534, 200.0
PHASE_X, PHASE_Y = 166.9, 173.5  # lattice phase of the arrival-reconstructed cell centres
DOMAIN = dict(lon_min=-119.3265, lon_max=-118.8305, lat_min=36.752, lat_max=37.158)
OUT_NPZ, OUT_RECEIPT = HERE / 'dem-extended-200m.npz', HERE / 'dem-extended-receipt.json'


def tile_xy(lon, lat):
    n = 2 ** ZOOM
    return (lon + 180) / 360 * n, (1 - np.arcsinh(np.tan(np.radians(lat))) / math.pi) / 2 * n


def tile_path(tiles_dirs, tx, ty, fetch):
    name = f'{ZOOM}_{tx}_{ty}.png'
    for d in tiles_dirs:
        if (d / name).is_file():
            return d / name
    if not fetch:
        raise FileNotFoundError(name)
    dest = tiles_dirs[-1] / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(Request(f'{TILE_BASE}/{ZOOM}/{tx}/{ty}.png', headers={'User-Agent': 'FireTrace-research/0.1'}), timeout=30) as r:
        dest.write_bytes(r.read(4 * 1024 * 1024))
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tiles-dir', required=True, help='read-only cache of already downloaded tiles')
    ap.add_argument('--offline', action='store_true')
    args = ap.parse_args()
    tiles_dirs = [Path(args.tiles_dir).resolve(), HERE / 'tiles-extra']

    xa, ya = (DOMAIN['lon_min'] - LON0) * M_LON, (DOMAIN['lat_min'] - LAT0) * M_LAT
    xb, yb = (DOMAIN['lon_max'] - LON0) * M_LON, (DOMAIN['lat_max'] - LAT0) * M_LAT
    ix0, ix1 = math.floor((xa - PHASE_X) / CELL), math.ceil((xb - PHASE_X) / CELL)
    iy0, iy1 = math.floor((ya - PHASE_Y) / CELL), math.ceil((yb - PHASE_Y) / CELL)
    nx, ny = int(ix1 - ix0 + 1), int(iy1 - iy0 + 1)
    x0, y0 = ix0 * CELL + PHASE_X, iy1 * CELL + PHASE_Y
    xs, ys = np.meshgrid(x0 + np.arange(nx) * CELL, y0 - np.arange(ny) * CELL)
    xs, ys = xs.ravel(), ys.ravel()

    heights, acc = {}, np.zeros(xs.size)
    offs = np.linspace(-80, 80, 5)
    for ox in offs:
        for oy in offs:
            fx, fy = tile_xy((xs + ox) / M_LON + LON0, (ys + oy) / M_LAT + LAT0)
            tx, ty = np.floor(fx).astype(int), np.floor(fy).astype(int)
            px, py = np.minimum(255, ((fx - tx) * 256).astype(int)), np.minimum(255, ((fy - ty) * 256).astype(int))
            vals = np.empty(xs.size)
            for key in set(zip(tx.tolist(), ty.tolist())):
                if key not in heights:
                    rgb = np.asarray(Image.open(tile_path(tiles_dirs, *key, fetch=not args.offline)).convert('RGB'), float)
                    if rgb.shape[:2] != (256, 256):
                        sys.exit('unexpected tile size')
                    heights[key] = rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768
                m = (tx == key[0]) & (ty == key[1])
                vals[m] = heights[key][py[m], px[m]]
            acc += vals
    elev = (acc / len(offs) ** 2).reshape(ny, nx)
    if not np.isfinite(elev).all() or elev.min() < -100 or elev.max() > 6000:
        sys.exit('implausible DEM values; refusing to write (no flat substitution)')

    tiles = []
    for tx, ty in sorted(heights):
        p = tile_path(tiles_dirs, tx, ty, fetch=False)
        tiles.append({'url': f'{TILE_BASE}/{ZOOM}/{tx}/{ty}.png', 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                      'bytes': p.stat().st_size, 'cache': 'base' if p.parent == tiles_dirs[0] else 'forecast_data/tiles-extra'})
    np.savez_compressed(OUT_NPZ, elevation=elev.astype(np.float32))
    receipt = {
        'schema': 'firetrace-forecast-dem-v1', 'status': 'real-dem', 'source': 'AWS Terrarium (Mapzen) z12 tiles',
        'builtAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'grid': {'cellM': CELL, 'nx': nx, 'ny': ny, 'x0': round(x0, 3), 'y0': round(y0, 3),
                 'projection': {'lat0': LAT0, 'lon0': LON0, 'mPerDegLat': M_LAT, 'mPerDegLon': M_LON}},
        'resampling': 'mean of 5x5 nearest-pixel samples (+-80 m) per 200 m cell; rows north-to-south (same as the 149x158 base DEM)',
        'tiles': tiles,
        'stats': {'minM': round(float(elev.min()), 1), 'maxM': round(float(elev.max()), 1), 'meanM': round(float(elev.mean()), 1)},
        'npzSha256': hashlib.sha256(OUT_NPZ.read_bytes()).hexdigest(),
        'limitations': ['Retrieval time is not elevation acquisition time.', 'Vertical accuracy not verified.', '200 m averaging underestimates local slopes.'],
    }
    OUT_RECEIPT.write_text(json.dumps(receipt, indent=1) + '\n')
    print(nx, ny, receipt['stats'], len(tiles), 'tiles', receipt['npzSha256'])


if __name__ == '__main__':
    main()
