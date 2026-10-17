"""One end-to-end variant: initialization at t0 -> baseline + prior ensemble -> causal camera cycles -> verification at pass time."""
import copy
import math
from datetime import datetime, timezone

import numpy as np

import assimilate as asm
import data as dat
import metrics as met
import model as mdl
from grid import to_xy

NOMINAL_FORECAST_LEADS = (30, 60)


def eval_passes(sat, split, t0, limit_epoch):
    """Roles for every FIRMS pass: validation | diagnostic | not-scored (with reason)."""
    table = dat.pass_table(sat)
    roles = {}
    for pid, p in sorted(table.items(), key=lambda kv: kv[1]['t']):
        if p['t'] <= t0:
            roles[pid] = ('initialization-not-scored', 'pass at or before t0: its detections are initialization data')
        elif pid in split['fit']:
            roles[pid] = ('calibration-fit-not-scored', 'used by the calibration fit')
        elif p['t'] > limit_epoch:
            roles[pid] = ('beyond-horizon-not-scored', 'later than the evaluation horizon')
        elif pid in split['heldOut']:
            roles[pid] = ('validation', None)
        elif pid in split['extraCheck']:
            roles[pid] = ('diagnostic', 'calibration extra check; excluded from headline aggregate')
        else:
            roles[pid] = ('unassigned-not-scored', 'not in the calibration split')
    return table, roles


def build_context(sat, grid, elev, cfg, t0, init_mode, cam_lonlat, t_end_min, members, seed, head_fraction=None):
    cfg = copy.deepcopy(cfg)
    if head_fraction is not None:
        cfg['observationModel']['headFraction'] = head_fraction
    idx, rel = dat.init_cells(grid, sat['arrival'], t0, init_mode)
    m = cfg['model']
    mod = mdl.Model(grid, elev.ravel(), sat['weather'], t0, idx, rel, m['baseSpreadMMin'], m['fuelFactor'], m['sectors'])
    base_arr, base_rate = mod.run(mdl.baseline_theta(m['sectors']), t_end_min)
    draws = mdl.sample_prior(members, m['sectors'], cfg['prior'], seed)
    p_arr, p_rate = mdl.run_ensemble(mod, draws, t_end_min)
    ctx = asm.Context(mod, cfg, base_arr, base_rate, draws, p_arr, p_rate, t_end_min, cam_lonlat)
    return ctx


def match_cycles(passes_eval, cycles, cfg):
    """For each (pass, nominal lead) pick the cycle whose actual lead is closest to nominal, strictly issue < pass."""
    tol = cfg['cycles']['leadToleranceMin']
    out = []
    for pid, p in passes_eval:
        for lead in cfg['cycles']['nominalLeadsMin']:
            best = None
            for c in cycles:
                actual = (p['t'] - c['issueEpoch']) / 60.0
                if actual <= 0:
                    continue
                gap = abs(actual - lead)
                if gap <= tol and (best is None or gap < best[0]):
                    best = (gap, c, actual)
            out.append({'passId': pid, 'nominalLeadMin': lead, 'cycle': best[1] if best else None, 'actualLeadMin': best[2] if best else None})
    return out


def run_variant(sat, grid, elev, cfg, t0_iso, init_mode, usable_rows, cam_lonlat, passes_table, roles, members, seed, head_fraction=None,
                with_arrays=True):
    t0 = dat.parse_epoch(t0_iso)
    clusters = asm.make_clusters([r for r in usable_rows if r['t'] > t0], cfg['cycles']['clusterGapMin'])
    eval_list = [(pid, passes_table[pid]) for pid, (role, _) in roles.items() if role in ('validation', 'diagnostic')]
    t_need = [p['t'] for _, p in eval_list] + [max(r['t'] for r in c) + 60 * 60 for c in clusters]
    t_end_min = (max(t_need) - t0) / 60.0 + 5.0 if t_need else 60.0
    ctx = build_context(sat, grid, elev, cfg, t0, init_mode, cam_lonlat, t_end_min, members, seed, head_fraction)
    cycles = []
    for k, rows in enumerate(clusters):
        issue = max(r['t'] for r in rows)
        cid = 'C%02d-%s' % (k + 1, datetime.fromtimestamp(issue, timezone.utc).strftime('%H%MZ'))
        cycles.append(asm.run_cycle(ctx, rows, cid, seed + 1000 * (k + 1)))
    # verification pairs (pass, cycle) with actual lead
    matches = match_cycles(eval_list, cycles, ctx.cfg)
    X_det = {}
    verifs = {}
    unmatched = []
    for mt in matches:
        pid = mt['passId']
        if mt['cycle'] is None:
            unmatched.append({'passId': pid, 'nominalLeadMin': mt['nominalLeadMin'],
                              'reason': 'no camera cycle issued before the pass with lead within +-%.0f min of nominal' % ctx.cfg['cycles']['leadToleranceMin']})
            continue
        key = (pid, mt['cycle']['cycleId'])
        v = verifs.setdefault(key, {'passId': pid, 'cycle': mt['cycle'], 'nominalLeadsMin': [], 'actualLeadMin': mt['actualLeadMin']})
        v['nominalLeadsMin'].append(mt['nominalLeadMin'])
    return {'ctx': ctx, 't0': t0, 'cycles': cycles, 'verifs': verifs, 'unmatched': unmatched, 'eval_list': eval_list, 't_end_min': t_end_min,
            'init_idx': ctx.model.init_idx}


def score(sat, grid, cfg, run, passes_table, roles):
    """Metrics for baseline / neutral ensemble / corrected at the REAL pass time; baseline-only rows always present."""
    ctx, t0 = run['ctx'], run['t0']
    init_mask = ctx.model.burned
    vcfg = cfg['validation']

    def one(arr, pid, factor=1.0):
        p = passes_table[pid]
        det = dat.pass_detections(sat, p['source'], p['t'])
        tol = met.tolerance(p['source'], cfg, factor)
        return met.pass_metrics(arr, grid, init_mask, (p['t'] - t0) / 60.0, det, tol, vcfg['activeBandMin']), tol

    baseline_rows = []
    for pid, p in run['eval_list']:
        m, tol = one(ctx.base_arr, pid)
        baseline_rows.append({'passId': pid, 'role': roles[pid][0], 'source': p['source'], 'passUtc': dat.utc_iso(p['t']),
                              'leadFromT0Min': round((p['t'] - t0) / 60.0, 1), 'toleranceM': tol, 'metrics': m})
    rows = []
    for (pid, cid), v in sorted(run['verifs'].items(), key=lambda kv: (passes_table[kv[0][0]]['t'], kv[0][1])):
        p, c = passes_table[pid], v['cycle']
        if not c['issueEpoch'] < p['t']:
            raise AssertionError('causal cut violated: issue %s not before pass %s' % (c['issueUtc'], pid))
        if any(r['t'] > c['issueEpoch'] for r in c['rows']):
            raise AssertionError('observation after issue time in cycle %s' % cid)
        res = {}
        for name, arr in (('baseline', ctx.base_arr), ('neutralEnsemble', c['neutral_arr']), ('corrected', c['corrected_arr'])):
            res[name], tol = one(arr, pid)
        tolsens = []
        for f in vcfg['tolSensitivityFactor']:
            e = {'factor': f}
            for name, arr in (('baseline', ctx.base_arr), ('corrected', c['corrected_arr'])):
                mm, tt = one(arr, pid, f)
                e[name] = {'toleranceM': tt, 'recallActive': mm['recallActive'], 'precisionActive': mm['precisionActive'], 'f1Active': mm['f1Active']}
            tolsens.append(e)
        verdict, delta = met.verdict(res['baseline'], res['corrected'], vcfg['verdictDeltaM'])
        vn, dn = met.verdict(res['neutralEnsemble'], res['corrected'], vcfg['verdictDeltaM'])
        rows.append({
            'passId': pid, 'role': roles[pid][0], 'source': p['source'], 'passUtc': dat.utc_iso(p['t']), 'cycleId': cid,
            'issueUtc': c['issueUtc'], 'latestObservationUtc': dat.utc_iso(max(r['t'] for r in c['rows'])),
            'actualLeadMin': round(v['actualLeadMin'], 1), 'nominalLeadsMin': sorted(v['nominalLeadsMin']),
            'deltaFromNominalMin': {str(L): round(v['actualLeadMin'] - L, 1) for L in sorted(v['nominalLeadsMin'])},
            'declaredLeadMismatch': any(abs(v['actualLeadMin'] - L) > 1.0 for L in v['nominalLeadsMin']),
            'causalCheck': {'issueBeforePass': True, 'allObservationsAtOrBeforeIssue': True, 'fromTimestamps': True},
            'cycleStatus': c['status'], 'toleranceM': tol, 'metrics': res, 'tolerancesSensitivity': tolsens,
            'verdictCorrectedVsBaseline': verdict, 'deltaPrimaryM': delta,
            'verdictCorrectedVsNeutralEnsemble': vn, 'deltaPrimaryVsNeutralM': dn})
    return baseline_rows, rows


def aggregate(rows):
    head = [r for r in rows if r['role'] == 'validation']
    counts = {}
    for r in head:
        counts[r['verdictCorrectedVsBaseline']] = counts.get(r['verdictCorrectedVsBaseline'], 0) + 1
    deltas = [r['deltaPrimaryM'] for r in head if r['deltaPrimaryM'] is not None]
    return {'verifications': len(head), 'verdictCounts': counts,
            'medianDeltaPrimaryM': None if not deltas else round(float(np.median(deltas)), 1),
            'worsened': counts.get('worsened', 0), 'improved': counts.get('improved', 0),
            'note': 'unit = (pass, camera cycle); few non-independent passes: descriptive only, no statistical significance'}
