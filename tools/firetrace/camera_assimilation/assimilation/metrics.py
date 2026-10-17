"""Compatibility of a modelled arrival field with FIRMS detections of ONE held-out pass, at the pass's real time.

FIRMS pixel centres at overpass time are not fire area, front or spread rate, and absence of a detection is not absence of fire
(clouds, scan angle, smoke, saturation). So no exact-area claim is made: metrics are spatial compatibility within the
satellite pixel tolerance, interpretable only as baseline-vs-corrected differences.
"""
import math

import numpy as np
from scipy.spatial import cKDTree

from grid import to_xy


def _tree(xy):
    return cKDTree(xy) if len(xy) else None


def pass_metrics(arr, grid, init_mask, t_rel_min, det, tol_m, active_band_min):
    """arr: arrival field (rel min; <=0 initial footprint, >0 modelled, inf unreached). det: dict lon/lat.
    Returns metrics and counts for this product."""
    X, Y = grid.centers_xy()
    cells = np.column_stack([X, Y])
    dx, dy = to_xy(det['lon'], det['lat'])
    dxy = np.column_stack([dx, dy])
    n_det = len(dxy)
    new = (arr > 0) & (arr <= t_rel_min)
    active = new & (arr >= t_rel_min - active_band_min)
    init_tree, new_tree, act_tree = _tree(cells[init_mask]), _tree(cells[new]), _tree(cells[active])

    def nearest(tree):
        if tree is None or n_det == 0:
            return np.full(n_det, np.inf)
        return tree.query(dxy)[0]

    d_init, d_new, d_act = nearest(init_tree), nearest(new_tree), nearest(act_tree)
    growth = d_init > tol_m
    hit_act = d_act <= tol_m
    hit_any = np.minimum(np.minimum(d_init, d_new), d_act) <= tol_m
    n_growth = int(growth.sum())
    recall_growth = float((d_new[growth] <= tol_m).mean()) if n_growth else None
    precision = None
    if active.any() and n_det:
        pts = act_tree.data
        det_tree = cKDTree(dxy)
        precision = float((det_tree.query(pts)[0] <= tol_m).mean())
    recall_active = float(hit_act.mean()) if n_det else None
    f1 = None
    if precision is not None and recall_active is not None and precision + recall_active > 0:
        f1 = 2 * precision * recall_active / (precision + recall_active)
    finite = d_act[np.isfinite(d_act)]
    median_near = float(np.median(d_act)) if n_det and np.isfinite(d_act).all() and len(d_act) else None
    return {
        'detections': n_det, 'growthDetections': n_growth, 'activeBandCells': int(active.sum()), 'newBurnedCells': int(new.sum()),
        'modelNewAreaHaCellCount': round(float(new.sum()) * grid.cell ** 2 / 1e4, 1),
        'medianNearestActiveBandM': None if median_near is None else round(median_near, 1),
        'detectionsWithoutActiveBand': int((~np.isfinite(d_act)).sum()),
        'recallAnyFootprint': float(hit_any.mean()) if n_det else None,
        'recallGrowth': recall_growth, 'recallActive': recall_active, 'precisionActive': precision, 'f1Active': f1,
        'p90NearestActiveBandM': None if not len(finite) or len(finite) < n_det else round(float(np.percentile(d_act, 90)), 1),
    }


def verdict(base, corr, delta_m):
    """Preregistered: compare the primary metric (median nearest active-band distance, lower is better)."""
    b, c = base['medianNearestActiveBandM'], corr['medianNearestActiveBandM']
    if b is None or c is None:
        return 'not-evaluable', None
    d = c - b
    if abs(d) < delta_m:
        return ('identical' if abs(d) < 1e-6 else 'unchanged-within-tolerance'), round(d, 1)
    return ('improved' if d < 0 else 'worsened'), round(d, 1)


def tolerance(source, cfg, factor=1.0):
    return cfg['validation']['tolM']['MODIS' if source.startswith('MODIS') else 'VIIRS'] * factor
