"""Set-valued angular assimilation of camera bases into a parameter ensemble.

A bearing is not a location. Each ensemble member predicts which model cells are the fast-spreading active head at the frame
time; the likelihood is how close that SET comes to the observed bearing (+/- calibration, pixel and cell-size angular
uncertainty), with an outlier floor. Range along the line of sight is never inferred. Parameters are updated only when a
permutation test says the weights actually moved them; the rest keep their prior. Corrections apply inside a viewing wedge only.
"""
import math

import numpy as np

import model as mdl
from data import utc_iso
from grid import ang_diff, bearing_deg, distance_m


class CameraGeometry:
    """Bearing and half-cell angular size of every grid cell as seen from one camera (cached)."""

    def __init__(self, grid, lonlat, half_cell_m):
        lon, lat = grid.centers_lonlat()
        self.bearing = bearing_deg(lonlat[0], lonlat[1], lon, lat)
        rng = np.maximum(distance_m(lonlat[0], lonlat[1], lon, lat), 1.0)
        self.half_ang = np.degrees(np.arctan(half_cell_m / rng))
        self.range_m = rng


def head_mask(arr, rate, t_min, clock_min, act_min, q):
    """(N, cells) bool: model-spread cells active at t (+/- clock), restricted to those with rate >= q * max active rate."""
    lo, hi = t_min - clock_min - act_min, t_min + clock_min
    active = (arr > 0) & (arr >= lo) & (arr <= hi)
    rmax = np.where(active, rate, 0.0).max(axis=1)
    head = active & (rate >= (q * rmax)[:, None]) & (rmax > 0)[:, None]
    return head


def obs_likelihood(arr, rate, obs, geom, t0_epoch, cfg):
    om = cfg['observationModel']
    t_min = (obs['t'] - t0_epoch) / 60.0
    head = head_mask(arr, rate, t_min, cfg['clock']['clockSigmaMin'], om['activeWindowMin'], om['headFraction'])
    eff = np.maximum(ang_diff(geom.bearing, obs['bearingDeg']) - geom.half_ang, 0.0)
    dmin = np.where(head, eff[None, :], np.inf).min(axis=1)
    eps = om['outlierFloor']
    like = eps + (1 - eps) * np.exp(-0.5 * (np.minimum(dmin, 1e6) / obs['sigmaDeg']) ** 2)
    like = np.where(np.isfinite(dmin), like, eps)
    return like, dmin


def cycle_loglik(arr, rate, rows, geoms, t0_epoch, cfg):
    """Sum of tempered log-likelihoods. Frames of one pose are correlated: each pose counts as one effective observation."""
    by_pose = {}
    for r in rows:
        by_pose.setdefault((r['cameraId'], r['poseId']), []).append(r)
    total = np.zeros(arr.shape[0])
    detail = []
    for key, items in sorted(by_pose.items()):
        for r in items:
            like, dmin = obs_likelihood(arr, rate, r, geoms[r['cameraId']], t0_epoch, cfg)
            total += np.log(like) / len(items)
            detail.append({'id': r['id'], 'cameraId': r['cameraId'], 'poseId': r['poseId'], 'bearingDeg': round(r['bearingDeg'], 3),
                           'sigmaDeg': round(r['sigmaDeg'], 3), 'temperingExponent': round(1 / len(items), 4),
                           'likelihoodMin': float(np.exp(np.log(like).min())), 'likelihoodMax': float(like.max()),
                           'fractionMembersCompatible': float((dmin <= r['sigmaDeg']).mean()),
                           'fractionMembersWithNoHead': float((~np.isfinite(dmin)).mean())})
    return total, detail


def normalized_weights(loglik):
    w = np.exp(loglik - loglik.max())
    return w / w.sum()


def ess(w):
    return float(1.0 / np.sum(w ** 2))


def kl_nats(w):
    n = len(w)
    nz = w > 0
    return float(np.sum(w[nz] * np.log(n * w[nz])))


def identifiability(P, w, cfg, names, seed):
    """Per-parameter permutation test: does the weight vector shift this parameter more than random weights do?"""
    idc = cfg['identifiability']
    mean0, sd0 = P.mean(axis=0), P.std(axis=0)
    sd0 = np.where(sd0 > 0, sd0, 1.0)
    Z = (P - mean0) / sd0
    obs_shift = np.abs(w @ Z)
    post_mean = w @ P
    post_sd = np.sqrt(np.maximum(w @ (P - post_mean) ** 2, 0.0))
    rng = np.random.default_rng(seed)
    perms = np.stack([w[rng.permutation(len(w))] for _ in range(idc['permutations'])])
    null = np.abs(perms @ Z)
    pval = (1 + (null >= obs_shift).sum(axis=0)) / (1 + idc['permutations'])
    out = []
    for j, name in enumerate(names):
        ident = bool(pval[j] < idc['alpha'] and obs_shift[j] >= idc['minEffectSd'])
        out.append({'name': name, 'priorMean': float(mean0[j]), 'priorSd': float(sd0[j]), 'posteriorMean': float(post_mean[j]),
                    'posteriorSd': float(post_sd[j]), 'shiftInPriorSd': float(obs_shift[j]), 'contraction': float(post_sd[j] / sd0[j]),
                    'pValuePermutation': float(pval[j]), 'identified': ident})
    return out


def systematic_resample(w, n, rng):
    pos = (rng.random() + np.arange(n)) / n
    return np.minimum(np.searchsorted(np.cumsum(w), pos), len(w) - 1)


def wedge_weight(geom, rows, cfg):
    om = cfg['observationModel']
    s = np.zeros(geom_size(geom, rows))
    for r in rows:
        g = geom[r['cameraId']]
        sw = max(om['wedgeSigmaFactor'] * r['sigmaDeg'], om['wedgeMinSigmaDeg'])
        s = np.maximum(s, np.exp(-0.5 * (ang_diff(g.bearing, r['bearingDeg']) / sw) ** 2))
    s[s < 0.01] = 0.0
    return s


def geom_size(geoms, rows):
    return next(iter(geoms.values())).bearing.size


def blend_arrival(base, ens_median, s):
    out = base.astype(float).copy()
    fb, fe = np.isfinite(base), np.isfinite(ens_median)
    both = fb & fe
    out[both] = s[both] * ens_median[both] + (1 - s[both]) * base[both]
    out[fb & ~fe & (s >= 0.5)] = np.inf
    out[~fb & fe & (s >= 0.5)] = ens_median[~fb & fe & (s >= 0.5)]
    return out


def make_clusters(rows, gap_min):
    clusters, cur = [], []
    for r in sorted(rows, key=lambda r: (r['t'], r['id'])):
        if cur and (r['t'] - cur[-1]['t']) / 60.0 > gap_min:
            clusters.append(cur)
            cur = []
        cur.append(r)
    if cur:
        clusters.append(cur)
    return clusters


class Context:
    """Everything a cycle needs; built once per (t0, initialization, headFraction) variant."""

    def __init__(self, model, cfg, base_arr, base_rate, prior_draws, prior_arr, prior_rate, t_end_min, cam_lonlat):
        self.model, self.cfg, self.t_end = model, cfg, t_end_min
        self.base_arr, self.base_rate = base_arr, base_rate
        self.prior_draws, self.prior_arr, self.prior_rate = prior_draws, prior_arr, prior_rate
        self.prior_median = np.median(prior_arr, axis=0)
        self.geoms = {cam: CameraGeometry(model.grid, ll, cfg['observationModel']['halfCellM']) for cam, ll in cam_lonlat.items()}
        self.names = mdl.param_names(model.n_sectors)
        self.P = mdl.params_matrix(prior_draws)


def run_cycle(ctx, rows, cycle_id, seed):
    """Assimilate `rows` (all with t <= issue) and return corrected fields. Raises if causality is violated."""
    cfg = ctx.cfg
    issue = max(r['t'] for r in rows)
    if any(r['t'] > issue for r in rows):
        raise AssertionError('causality violated')
    t0 = ctx.model.t0
    loglik, detail = cycle_loglik(ctx.prior_arr, ctx.prior_rate, rows, ctx.geoms, t0, cfg)
    w = normalized_weights(loglik)
    n = len(w)
    idc = cfg['identifiability']
    e, kl = ess(w), kl_nats(w)
    ident = identifiability(ctx.P, w, cfg, ctx.names, seed)
    identified = [p['identified'] for p in ident]
    status, reason = 'updated', None
    if e / n < idc['minEssFraction']:
        status, reason = 'gated-weight-collapse', 'ESS %.1f of %d below %.0f%%: posterior untrusted, baseline kept' % (e, n, 100 * idc['minEssFraction'])
    elif kl < idc['minKlNats']:
        status, reason = 'no-effect', 'information gain %.3f nats below %.2f: observation is compatible with the prior ensemble' % (kl, idc['minKlNats'])
    elif not any(identified):
        status, reason = 'no-effect', 'no parameter passed the permutation identifiability test; prior kept'
    s = wedge_weight(ctx.geoms, rows, cfg)
    result = {'cycleId': cycle_id, 'issueEpoch': issue, 'issueUtc': utc_iso(issue), 'status': status, 'reason': reason,
              'observationIds': [r['id'] for r in rows], 'rows': rows, 'ess': e, 'essFraction': e / n, 'klNats': kl,
              'likelihood': detail, 'parameters': ident, 'identifiedParameters': [p['name'] for p in ident if p['identified']],
              'wedgeCells': int((s > 0).sum()), 'wedgeWeight': s}
    if status != 'updated':
        result.update(corrected_arr=ctx.base_arr.astype(float), neutral_arr=ctx.base_arr.astype(float), posterior_arr=None)
        return result
    rng = np.random.default_rng(seed + 1)
    idx = systematic_resample(w, n, rng)
    fresh = mdl.params_matrix(mdl.sample_prior(n, ctx.model.n_sectors, cfg['prior'], seed + 2))
    Pn = fresh.copy()
    cols = np.array(identified)
    Pn[:, cols] = ctx.P[idx][:, cols]
    arr_post, _ = mdl.run_ensemble(ctx.model, mdl.draws_from_matrix(Pn), ctx.t_end)
    med = np.median(arr_post, axis=0)
    result['corrected_arr'] = blend_arrival(ctx.base_arr, med, s)
    result['neutral_arr'] = blend_arrival(ctx.base_arr, ctx.prior_median, s)
    result['posterior_arr'] = arr_post
    return result
