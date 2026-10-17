"""Frozen experiment configuration. Every value here is chosen BEFORE any held-out score is computed and is never tuned
against validation passes; the SHA-256 of this document is written into scenario.json (preregistration.configSha256)."""
import hashlib
import json

CONFIG = {
    'version': 'firetrace-assimilation-config-v1',
    'day': '2025-08-27',
    'clock': {'hypothesis': 'assumed-PDT', 'clockSigmaMin': 5.0, 'sensitivityMin': [2, 5, 10]},
    't0': {'primary': '2025-08-27T10:00:00-07:00', 'sensitivity': ['2025-08-27T04:00:00-07:00'],
           'why': 'No FIRMS pass exists between 03:36 and 11:17 PDT on 27/08, so support observed <= t0 is identical for any t0 in that gap; '
                  '10:00 precedes the first camera frame (printed 10:30) and keeps the uniform-rate integration short.'},
    'initialization': {'primary': 'observed-support-le-t0', 'alternatives': ['arrival-reconstructed-with-interpolated-le-t0']},
    'model': {'baseSpreadMMin': 4.0, 'fuelFactor': 1.0, 'baseSource': 'simulation.html default (4 m/min); not fitted to any fire',
              'coefficientsFrom': 'simulation.py (KW, KS, S_MIN, S_MAX) imported read-only', 'sectors': 12,
              'windTimeInterpolation': 'nearest hourly Open-Meteo value (single reanalysis point)'},
    'prior': {'windBiasDegSd': 20.0, 'windBiasDegClip': 50.0, 'lnSpeedMultSd': 0.30, 'lnSectorMultSd': 0.50, 'lnSectorClip': 1.2,
              'note': 'dispersion of the uncertain inputs, not knowledge: unvalidated, no fuel map, no tuning'},
    'ensemble': {'members': 300, 'seed': 20250827, 'composite': 'resample identified parameters by posterior weight, redraw the others from the prior'},
    'observationModel': {'activeWindowMin': 90, 'headFraction': 0.70, 'headFractionSensitivity': [0.5, 0.85], 'outlierFloor': 0.05,
                         'pixelSigmaX': 0.02, 'calibrationSigmaFromEnvelope': 0.5, 'sigmaFloorDeg': 1.0, 'sigmaGateDeg': 12.0, 'printedPriorSigmaDeg': 3.0, 'printedPriorSensitivityDeg': [1.0, 3.0, 5.0, 10.0],
                         'wedgeSigmaFactor': 2.0, 'wedgeMinSigmaDeg': 3.0, 'halfCellM': 100.0,
                         'poseTempering': 'likelihood of each pose within a cycle raised to 1/n_frames (frames of one pose are correlated)',
                         'headDefinition': 'model-spread cells with arrival in [T-clock-activeWindow, T+clock] and local rate >= headFraction*max rate'},
    'cycles': {'clusterGapMin': 10.0, 'maxObservationAgeMin': 0.0, 'nominalLeadsMin': [30, 60], 'leadToleranceMin': 20.0, 'forecastLeadsMin': [30, 60]},
    'identifiability': {'permutations': 400, 'alpha': 0.01, 'minEffectSd': 0.25, 'minEssFraction': 0.10, 'minKlNats': 0.05},
    'validation': {'activeBandMin': 60, 'tolM': {'VIIRS': 500.0, 'MODIS': 1000.0}, 'tolSensitivityFactor': [0.6, 1.0, 2.0],
                   'primaryMetric': 'medianNearestActiveBandM (lower is better)', 'verdictDeltaM': 100.0,
                   'validationPasses': 'printed-X model: every FIRMS pass after t0 (none fitted); fitted contrast: B held-out passes only. Passes at or before t0 are initialization data and are never scored. A pass is verified by a cycle only if issue < pass time.',
                   'maxEvalLeadFromT0Min': 390, 'maxEvalLeadFromLastObsMin': 90,
                   'defaultHeldOutPassIds': ['SNPP@2025-08-27T20:16:00Z', 'NOAA20@2025-08-27T20:38:00Z',
                                             'SNPP@2025-08-27T21:57:00Z', 'MODIS@2025-08-27T23:00:00Z'],
                   'defaultFitPassIds': ['NOAA21@2025-08-27T19:49:00Z', 'NOAA21@2025-08-27T21:29:00Z'],
                   'defaultExtraCheckPassIds': ['MODIS@2025-08-27T18:17:00Z']},
}


def config_sha256(cfg=CONFIG):
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()
