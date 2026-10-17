"""Heuristic minimum-travel-time spread on the real-DEM grid with hourly wind.

Same rate law as simulation.py (imported read-only for KW, KS, S_MIN, S_MAX):
    rate = base * fuel * multipliers * exp(KW * v(t) * cos(stepBearing - windToward(t))) * clamp(exp(KS * dz/dist))
Uniform fuel is an assumption, not a measurement. Wind comes from one Open-Meteo reanalysis point (nearest hour).
This is NOT a validated fire-behaviour model; parameters (base rate, multipliers) are unvalidated.
"""
import heapq
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import simulation as sim  # noqa: E402  (pure constants; file is never edited)

DIRS = [(dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc]


class Model:
    def __init__(self, grid, elev, weather, t0_epoch, init_idx, init_arrival, base_m_min=4.0, fuel=1.0, n_sectors=12):
        self.grid, self.t0, self.n_sectors = grid, float(t0_epoch), n_sectors
        ny, nx = grid.ny, grid.nx
        self.pw = nx + 2
        n_pad = (ny + 2) * self.pw
        z = np.zeros((ny + 2, nx + 2))
        z[1:-1, 1:-1] = np.asarray(elev, float).reshape(ny, nx)
        z = z.ravel()
        valid = np.zeros((ny + 2, nx + 2), bool)
        valid[1:-1, 1:-1] = True
        self.valid = valid.ravel().tolist()
        self.dp = [dr * self.pw + dc for dr, dc in DIRS]
        c = grid.cell
        self.dist = [math.hypot(dr, dc) * c for dr, dc in DIRS]
        self.bear = [math.atan2(dc * c, -dr * c) for dr, dc in DIRS]
        self.sfac = []
        ks, lo, hi = sim.KS, math.log(sim.S_MIN), math.log(sim.S_MAX)
        for (dr, dc), dp, dist in zip(DIRS, self.dp, self.dist):
            dz = np.zeros(n_pad)
            idx = np.arange(n_pad)
            ok = np.array(self.valid) & np.roll(np.array(self.valid), -dp)
            dz[ok] = z[(idx + dp)[ok]] - z[ok]
            self.sfac.append(np.exp(np.clip(ks * dz / dist, lo, hi)).tolist())
        self.base = base_m_min * fuel
        self.elev = z[(np.arange(n_pad))].reshape(ny + 2, nx + 2)[1:-1, 1:-1].ravel()
        # padded index of each unpadded flat cell
        r, cc = np.divmod(np.arange(ny * nx), nx)
        self.pad_of = (r + 1) * self.pw + (cc + 1)
        # weather table (nearest hour)
        self.w_epoch, self.w_from, self.w_speed = weather['epoch'], weather['from'], weather['speed']
        # initial state
        self.init_idx = np.asarray(init_idx, int)
        self.init_arrival = np.asarray(init_arrival, float)
        burned = np.zeros(ny * nx, bool)
        burned[self.init_idx] = True
        self.burned = burned
        self.burned_pad = np.zeros(n_pad, bool)
        self.burned_pad[self.pad_of[burned]] = True
        self.burned_pad = self.burned_pad.tolist()
        bgrid = burned.reshape(ny, nx)
        pad = np.pad(bgrid, 1, constant_values=True)
        free_nb = np.zeros_like(bgrid)
        for dr, dc in DIRS:
            free_nb |= ~pad[1 + dr:1 + dr + ny, 1 + dc:1 + dc + nx]
        self.seeds = self.pad_of[(bgrid & free_nb).ravel()].tolist()
        # sectors by azimuth about the initial footprint centroid
        X, Y = grid.centers_xy()
        cx, cy = X[burned].mean(), Y[burned].mean()
        az = np.degrees(np.arctan2(X - cx, Y - cy)) % 360.0
        self.sector = np.minimum((az // (360.0 / n_sectors)).astype(int), n_sectors - 1)
        self.centroid_xy = (float(cx), float(cy))

    def wind_table(self, t_end_min, wind_bias_deg=0.0):
        """Per-hour step factors W[h][d] and the offset to index them from model minutes."""
        first = max(0, int(np.searchsorted(self.w_epoch, self.t0 - 1800)) - 1)
        last = min(len(self.w_epoch) - 1, int(np.searchsorted(self.w_epoch, self.t0 + t_end_min * 60 + 1800)) + 1)
        tab = []
        for k in range(first, last + 1):
            toward = math.radians((self.w_from[k] + wind_bias_deg + 180.0) % 360.0)
            tab.append([math.exp(sim.KW * self.w_speed[k] * math.cos(b - toward)) for b in self.bear])
        base_min = (self.t0 - (self.w_epoch[first] - 1800.0)) / 60.0
        return tab, base_min

    def run(self, theta, t_end_min):
        """theta: windBiasDeg, speedMult, sectorMult (array n_sectors). Returns (arrival_rel_min, rate_in) on the unpadded grid.
        arrival: <= 0 for the initial footprint (reconstructed), > 0 modelled, inf unreached within t_end_min."""
        tab, base_min = self.wind_table(t_end_min, theta.get('windBiasDeg', 0.0))
        nh = len(tab)
        mult_cell = (self.base * theta.get('speedMult', 1.0) * np.asarray(theta['sectorMult'], float)[self.sector])
        mult = np.zeros(len(self.valid))
        mult[self.pad_of] = mult_cell
        mult = mult.tolist()
        n_pad = len(self.valid)
        inf = math.inf
        tent = [inf] * n_pad
        rate_in = [0.0] * n_pad
        heap = []
        for p in self.seeds:
            tent[p] = 0.0
            heap.append((0.0, p))
        heapq.heapify(heap)
        valid, burned, dp, dist, sfac = self.valid, self.burned_pad, self.dp, self.dist, self.sfac
        ndir = len(dp)
        pop, push = heapq.heappop, heapq.heappush
        while heap:
            t, p = pop(heap)
            if t > tent[p] or t > t_end_min:
                continue
            h = int((t + base_min) // 60.0)
            wh = tab[0 if h < 0 else (nh - 1 if h >= nh else h)]
            for d in range(ndir):
                q = p + dp[d]
                if not valid[q] or burned[q]:
                    continue
                rate = mult[q] * wh[d] * sfac[d][p]
                nt = t + dist[d] / rate
                if nt < tent[q] and nt <= t_end_min:
                    tent[q] = nt
                    rate_in[q] = rate
                    push(heap, (nt, q))
        arr = np.array(tent, float)[self.pad_of]
        rin = np.array(rate_in, float)[self.pad_of]
        arr[self.init_idx] = self.init_arrival
        rin[self.init_idx] = 0.0
        return arr.astype(np.float32), rin.astype(np.float32)


BASELINE_THETA = None


def baseline_theta(n_sectors):
    return {'windBiasDeg': 0.0, 'speedMult': 1.0, 'sectorMult': np.ones(n_sectors)}


def sample_prior(n, n_sectors, prior, seed):
    """n prior draws as arrays. The baseline (all neutral) is NOT one of them."""
    rng = np.random.default_rng(seed)
    wb = np.clip(rng.normal(0, prior['windBiasDegSd'], n), -prior['windBiasDegClip'], prior['windBiasDegClip'])
    lm = rng.normal(0, prior['lnSpeedMultSd'], n)
    ls = np.clip(rng.normal(0, prior['lnSectorMultSd'], (n, n_sectors)), -prior['lnSectorClip'], prior['lnSectorClip'])
    return {'windBiasDeg': wb, 'lnSpeedMult': lm, 'lnSectorMult': ls}


def params_matrix(draws):
    """Stack the parameter vector per member: [windBias, lnSpeed, lnSector...]."""
    return np.column_stack([draws['windBiasDeg'], draws['lnSpeedMult'], draws['lnSectorMult']])


def draws_from_matrix(m):
    return {'windBiasDeg': m[:, 0], 'lnSpeedMult': m[:, 1], 'lnSectorMult': m[:, 2:]}


PARAM_NAMES_FIXED = ['windBiasDeg', 'lnSpeedMult']


def param_names(n_sectors):
    return PARAM_NAMES_FIXED + ['lnSectorMult[%d]' % s for s in range(n_sectors)]


def theta_of(draws, i):
    return {'windBiasDeg': float(draws['windBiasDeg'][i]), 'speedMult': float(np.exp(draws['lnSpeedMult'][i])),
            'sectorMult': np.exp(draws['lnSectorMult'][i])}


def run_ensemble(model, draws, t_end_min):
    n = len(draws['windBiasDeg'])
    arr = np.empty((n, model.grid.size), np.float32)
    rate = np.empty((n, model.grid.size), np.float32)
    for i in range(n):
        arr[i], rate[i] = model.run(theta_of(draws, i), t_end_min)
    return arr, rate
