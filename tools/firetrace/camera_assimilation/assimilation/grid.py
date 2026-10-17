"""200 m metric grid aligned to the Garnet arrival-reconstructed lattice (same local projection as build_layers.py)."""
import math

import numpy as np

LAT0, LON0 = 36.95, -119.05
M_LAT = 111_320.0
M_LON = 111_320.0 * math.cos(math.radians(LAT0))
CELL_M = 200.0
# Lattice phase of arrival-reconstructed cell centres relative to (LON0, LAT0), measured from the data (median of x%200, y%200).
LATTICE_X0, LATTICE_Y0 = 166.9, 173.5


def to_xy(lon, lat):
    return (np.asarray(lon, float) - LON0) * M_LON, (np.asarray(lat, float) - LAT0) * M_LAT


def to_lonlat(x, y):
    return np.asarray(x, float) / M_LON + LON0, np.asarray(y, float) / M_LAT + LAT0


class Grid:
    """Rows run north to south, columns west to east. Cell (r, c) centre = (x0 + c*cell, y0 - r*cell)."""

    def __init__(self, lon_min, lon_max, lat_min, lat_max, cell=CELL_M):
        self.cell = float(cell)
        xa, ya = to_xy(lon_min, lat_min)
        xb, yb = to_xy(lon_max, lat_max)
        ph_x, ph_y = LATTICE_X0 % cell, LATTICE_Y0 % cell
        ix0 = math.floor((xa - ph_x) / cell)
        ix1 = math.ceil((xb - ph_x) / cell)
        iy0 = math.floor((ya - ph_y) / cell)
        iy1 = math.ceil((yb - ph_y) / cell)
        self.nx = int(ix1 - ix0 + 1)
        self.ny = int(iy1 - iy0 + 1)
        self.x0 = ix0 * cell + ph_x
        self.y0 = iy1 * cell + ph_y  # northmost row centre
        self.size = self.nx * self.ny

    def spec(self):
        return {'cellM': self.cell, 'nx': self.nx, 'ny': self.ny, 'x0': round(self.x0, 3), 'y0': round(self.y0, 3),
                'projection': {'lat0': LAT0, 'lon0': LON0, 'mPerDegLat': M_LAT, 'mPerDegLon': round(M_LON, 3)}}

    @classmethod
    def from_spec(cls, spec):
        g = cls.__new__(cls)
        g.cell = float(spec['cellM'])
        g.nx, g.ny = int(spec['nx']), int(spec['ny'])
        g.x0, g.y0 = float(spec['x0']), float(spec['y0'])
        g.size = g.nx * g.ny
        return g

    def centers_xy(self):
        cols = self.x0 + np.arange(self.nx) * self.cell
        rows = self.y0 - np.arange(self.ny) * self.cell
        X, Y = np.meshgrid(cols, rows)
        return X.ravel(), Y.ravel()

    def centers_lonlat(self):
        return to_lonlat(*self.centers_xy())

    def index_of_xy(self, x, y):
        """Flat index of the cell containing (x, y); -1 when outside the grid."""
        c = np.rint((np.asarray(x, float) - self.x0) / self.cell).astype(int)
        r = np.rint((self.y0 - np.asarray(y, float)) / self.cell).astype(int)
        ok = (c >= 0) & (c < self.nx) & (r >= 0) & (r < self.ny)
        return np.where(ok, r * self.nx + c, -1)

    def index_of_lonlat(self, lon, lat):
        return self.index_of_xy(*to_xy(lon, lat))

    def cell_polygon(self, idx):
        r, c = divmod(int(idx), self.nx)
        x, y = self.x0 + c * self.cell, self.y0 - r * self.cell
        h = self.cell / 2
        xs = [x - h, x + h, x + h, x - h, x - h]
        ys = [y - h, y - h, y + h, y + h, y - h]
        lon, lat = to_lonlat(xs, ys)
        return [[round(float(a), 5), round(float(b), 5)] for a, b in zip(lon, lat)]


def bearing_deg(lon0, lat0, lon, lat):
    """Initial great-circle bearing (deg from north, clockwise) from a point to arrays of points."""
    p0, p1 = math.radians(lat0), np.radians(lat)
    dl = np.radians(np.asarray(lon, float) - lon0)
    y = np.sin(dl) * np.cos(p1)
    x = math.cos(p0) * np.sin(p1) - math.sin(p0) * np.cos(p1) * np.cos(dl)
    return np.degrees(np.arctan2(y, x)) % 360.0


def distance_m(lon0, lat0, lon, lat):
    x, y = to_xy(lon, lat)
    x0, y0 = to_xy(lon0, lat0)
    return np.hypot(x - x0, y - y0)


def ang_diff(a, b):
    """Smallest absolute angular difference in degrees."""
    return np.abs((np.asarray(a, float) - np.asarray(b, float) + 180.0) % 360.0 - 180.0)
