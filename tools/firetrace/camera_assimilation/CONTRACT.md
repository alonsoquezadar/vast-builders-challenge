# Camera-assisted wildfire experiment v1

Goal: prove whether camera evidence changes a scenario and improves held-out satellite compatibility, with all failures exposed. This is retrospective research, not an operational forecast.

`feasibility.py` reproduces temporal coverage under PDT/PST/UTC. On assumed PDT, G1 has four overpasses, G3b three and G4 three. G2 has none. The video covers only August 27, so August 26/28 cannot provide image-world calibration pairs for it. Pose boundaries are approximate; every analyzed frame must have its printed date/time and pose checked from the image. Never interpolate printed time from video seconds.

Clock: PDT is a hypothesis, not verified. The daylight at printed 10:35 is inconsistent with interpreting the print as UTC (03:35 California summer clock). This does not distinguish PDT from a camera clock offset by an hour. FRP/plume co-occurrence is supporting qualitative evidence, not clock synchronization. The public pages checked did not provide a historical per-camera clock receipt.

## Files and ownership

- Root: this contract, feasibility.*, main.py, observation_schema.py, update_visual_gateway.py, integration/UI/server/Git.
- A only: `camera_assimilation/vision/` (scripts, frames, raw Cosmos responses, observations.json, report.md).
- B only: `camera_assimilation/calibration/` (runnable calibration module/CLI, tests, calibration.json, report.md).
- C only: `camera_assimilation/assimilation/` (runnable model module/CLI, tests, scenario.json, report.md).
- All agents read but never write `evidence/garnet/satellite/`. No agent runs git mutations, changes servers/deployments, or writes another agent's directory.

## Observation interface

`vision/observations.json`: object with `schema: firetrace-camera-observations-v1`, `observations: [...]` and receipts/limitations. Rows: `id`, `cameraId` (delilah/buckrock), `poseId` (G1/G2/G3b/G4), `sourceVideoSecond`, `imagePath` (relative to tools/firetrace), `imageSha256`, `frameWidth`, `frameHeight`, `printedTime` (ISO without timezone), `printedTimeStatus` (verified-by-agent/uncertain), `timeUtcAssumed` (ISO Z, print +7h), `clockStatus: assumed-PDT`, `method` (cosmos/simple-detector), `smoke`, `base_visible`, normalized `x_base`/`y_base` [0,1] or null if hidden, `confidence` (uncalibrated), `reason`, `reviewStatus: pending-operator-review`. Method comparisons remain separate; heuristic output is never represented as Cosmos output. Nullable/invalid or uncertain-clock rows are rejected downstream. Agent visual inspection is not human review.

API: POST http://localhost:5173/api/analyze with `{image: data URL, task: smoke-base-v1}`. Response preserves raw `content`, model/time/SHA and parsed `observation` (or null + structuredError). No invented coordinates for hidden bases. Preserve logos and original frames. The original /tmp/firevids/garnet.ogg SHA is in evidence/garnet/manifest.json.

## Calibration interface

B reads observations and FIRMS. CLI can run after A finishes; do not wait or poll for A. Implement against this schema first, return a runnable artifact plus explicit missing-data status if needed. `calibration.json`: schema, status, assumptions, positions, `poses` array, per-pose cameraId/poseId/status/yaw0Deg/fovDeg/trainingIds/heldOutIds/errors/uncertainty and excluded observations. Expose mapping to bearing and uncertainty for C. Uncalibratable poses have null parameters and a reason. Preserve raw model/task evidence IDs.

Pre-register time/source split before fitting: for G1/G3b, prefer VIIRS 12:49 for fit, 13:16 and 13:38 held out under PDT. G4 fit 14:29, hold out 14:57 and 16:00. MODIS 11:17 can be an extra check for G1. Nearest frame maximum 5 min (show actual gap); clocks +/-2,5,10 min sensitivity. One direction cannot identify yaw + FOV: fix explicit unverified FOV prior 65.1 degrees at zoom1, use focal scaling for other zoom, unless rank/conditioning supports more. Candidate tower position uncertainty: evaluate 30/100/500 m scenarios, not claimed sigma bounds. Do not use CAL FIRE point. Do not transfer poses using printed X without validation. FIRMS groups have angular extent/multiple fronts: centroid is not an observed plume base. Report centroid residual and nearest-group residual separately. Meter error is cross-track compatibility at independent satellite range, not proof of 2D fire localization. Temporal holdout is not independent physical truth.

## Assimilation interface

C reads A/B outputs at runtime; implement first without waiting. `scenario.json`: schema/status, observed/reconstructed/modeled data classes, initialization time/source, explicit camera-use count and IDs, uncorrected vs corrected forecasts at +30/+60, held-out metrics, and limitations. If missing calibration, hidden bases or clock/correspondence uncertainty prevents use, return disabled/reason, never fabricate a correction. The retrospective arrival surface leaks final footprint and future observations; initialization must disclose this. Daily reconstructed extent is not ground truth. Compare held-out observed FIRMS, with actual forecast lead/time mismatch and errors. Do not tune parameters against validation passes. Never both assimilate and validate the same observations. Wind is historical point-model output, fuel remains unknown/hypothetical. Humidity is not fuel moisture. A bearing alone is not a location: use set-valued angular likelihood against model cells, not forced point triangulation. Only triangulate matched visible base features with explicit clock uncertainty. Retain an uncorrected baseline. If corrections do not improve reserved metrics, show that result.

## Product claims

Target cadence is camera-driven correction, satellite validation at available passes. The timelapse cannot prove corrections every minute; the 225 passes are not a fixed twice-daily cadence. Do not display the proposed slogan as an achieved capability. Show measured observation cadence, gates and uncertainty. No promised hundreds-of-meters accuracy until measured with independent evidence.
