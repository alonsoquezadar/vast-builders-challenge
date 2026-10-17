# FireTrace multi-camera replay: incident selection (ALERTCalifornia)

Prepared 2026-10-18 (Europe/London) for Alonso Quezada. Everything below was checked on the actual footage unless marked *unverified* or `null`.

## 1. Ranking (3 incidents compared; all from ALERTCalifornia's official YouTube channel compilations)

| Rank | Incident | Distinct camera locations | Common real interval (printed time) | Flames / fire base seen? | Main weakness |
|---|---|---|---|---|---|
| **1** | **Gann Fire, Calaveras Co., 3-5 Aug 2026** (video N_C9qivAWfA) | **4** (Valley Springs, Upper Bear, Southworth, Golden Gate) | **17:47:31 -> ~00:57:39 PDT = 7 h 10 min** (all four); plus a 2-camera daytime interval 4 Aug 12:31-19:59 | Yes, from all four (flame line, fire front, glow at night) | Compilation is sequential and sped up; no download offered; time zone not printed; no dated perimeter; FIRMS not retrieved |
| 2 | Little Fire, Alameda Co., 21 Jul 2026 (kEhM3KzDVag) | 2 (Sunol Ridge 1, Mt Allison) | 14:58:12 -> 21:13:28 (~6 h 15 min, TZ assumed PDT) | Smoke, burn scar and flame visible from Sunol Ridge | Only 2 locations; coordinates not retrieved |
| 3 | Vista Fire, San Bernardino Co., Jul 2024 (K67cvWlVuRU, probably; sibling 0YyYO-Q_BTk) | 3 (San Sevaine 1, Bailey Peak 1, Sunset Peak 1) | 11:02:24 -> 15:57:11 (~4 h 55 min) | Smoke clearly; flames/fire base not confirmed | Description says 7 Jul but printed date is 2024/07/08 (unresolved); WFIGS has only the final perimeter |

Not inspected (so not ranked): Gifford, Thorn, Pickett, Coyote and other compilations on the channel. I did not exhaustively test them.

## 2. Recommendation: Gann Fire (2026)

Reasons, in order of your criteria:
1. It is the only candidate with 4 geographically distinct camera locations (3.8, 4.3, 13.8 and 15.3 km from the WFIGS ignition point; sites are not co-located).
2. A 7 h 10 min common real-time window on the night of 3-4 Aug (start of the fire through the night), well over the 30 min target.
3. Burned-in bar is legible on every camera at 720p (name, elevation, pan/tilt/zoom, preset tag, date, time to 0.01 s).
4. Visible active flame lines, fire front and night glow from all four locations; plus daylight smoke columns.
5. Weather (two airport stations) and agency timeline of acreage exist. Dated *spatial* perimeters and FIRMS are the gaps (section 5).
6. The fire is recent and the WFIGS/Cal Fire records are complete (10,339 ac, 100% contained 12 Aug).

Honest limits: the video is a **sequential, sped-up compilation** (each camera is shown one after another, so the cameras are never on screen simultaneously). Real-world overlap is established from printed clocks, not from the video timeline. FireTrace needs the original per-camera footage (or its own time-mapping of this compilation) to replay them in sync. Four cameras do not prove separate ignitions, enable accurate triangulation, or validate a simulation; they only give four dated views of the same fire.

## 3. Camera-by-camera evidence (Gann Fire, night 1; analysed copy: 1280x720, 30 fps, 773.8 s)

Publication: https://www.youtube.com/watch?v=N_C9qivAWfA, "Gann Fire Compilation", ALERTCalifornia, published 2026-08-06 (YouTube metadata). Recording dates are the printed ones, 2026-08-03 to 2026-08-05. The description says the footage is "sped up and in chronological order" and that the bar shows camera name/date/time (from the ALERT images-and-video page).

| Camera (printed) / site id | Console URL | Coords (lat, lon) | Bearing/dist to ignition | Video seconds (night 1) | Printed start -> end | Anchors (video s -> printed) | Visible |
|---|---|---|---|---|---|---|---|
| axis-valleysprings, elev 1388' / `valleysprings` | cameras.alertcalifornia.org/?id=Axis-ValleySprings | 38.1115, -120.8177 | 89 deg, 3.8 km | 0-166 | 08-03 17:23:11 -> 08-04 06:58:11 | 0 -> 17:23:11; 34 -> 18:45:34; 67 -> 21:40:43; 100 -> 00:39:35 | smoke column from start, flame line and fire front at night, zoom changes (Z 1.0-11.1) |
| axis-upperbear, elev 2687' / `upperbear` (cam 1; Upper Bear 2 on same tower) | ?id=Axis-UpperBear | 38.1169, -120.7252 | 263 deg, 4.3 km | 167-329 | 08-03 17:04:50 -> 08-04 06:57:24 | 167 -> 17:04:50; 193 -> 19:17:29; 222 -> 22:01:38; 248 -> 00:11:47 | **no smoke in first frames (17:02-17:05)**, then large smoke, flame line along ridge at night, power-line towers in foreground; pan/zoom changes |
| axis-southworth, elev 348' / `southworth` | ?id=Axis-Southworth | 38.1479, -120.9248 | 107 deg, 13.8 km | 330-408.3 | 08-03 17:35:28 -> 08-04 ~00:57:39 (OCR last 00:53:31 at 407.0; eye-read 00:57:39 at 408.2) | 330 -> 17:35:28; 345 -> 19:08:55; 361 -> 20:43:13; 376 -> 22:14:27 | dark smoke column at start, glowing fire front at night |
| axis-goldengate, elev 1959' / `goldengate` | ?id=Axis-GoldenGate | 38.2486, -120.7473 | 189 deg, 15.3 km | ~408.4-564 | 08-03 17:47:2x -> 08-04 06:57:47 | 439 -> 20:31:59; 470 -> 23:44:15; 502 -> 01:39:22 (start 17:47:31 at ~408.5, eye-read) | smoke at dusk; glowing fire base on ridge at night; one over-exposed frame (IR/gain) |

Day 2 and 3 segments (also visible): valleysprings 565-657 s = 4 Aug 12:03:07 -> 20:56:29 and 738-770 s = 5 Aug 12:42:12 -> 15:54:06; goldengate 658-737 s = 4 Aug 12:31:29 -> 19:59:45.

Common to all rows:
- **Coordinates**: from the ALERTCalifornia ArcGIS "ALERTCalifornia_Camera_Feed" layer, queried 2026-10-18. It is a *current* camera layer (not historical evidence); uncertainty is not published (`null`). Bearing/distance are computed from these points to the WFIGS initial lat/lon (38.112384, -120.774225). Printed pan angles (X) are consistent with those bearings for Valley Springs, Southworth, Golden Gate (e.g. X +96 vs 89 deg; X +107.7 vs 107 deg; X -174.8 = 185 deg vs 189 deg) if pan 0 = north, which is my assumption.
- **Time zone**: not printed. Assumed America/Los_Angeles (PDT, UTC-7). Support: dusk/dark progression matches a ~19:55 PDT sunset; WFIGS discovery 2026-08-04T00:27:56Z = 17:27 PDT = Cal Fire "Date Started 08/03/2026 5:27 PM". **Caveat:** Valley Springs already shows a sizable smoke column at printed 17:22:21, ~5 min before that official time. The official time is a report/start time, not proof of ignition; the printed clock itself was not independently verified.
- **Timestamp reading method**: automatic OCR (RapidOCR) of the bar at 1 frame per video second, 736 of 774 samples parsed, plus visual checks of ~40 bar crops and all segment boundaries. Times are monotonic within each segment (0 violations). Video second labels are good to about +-1 s at cut boundaries. All sampled values in `samples/gann_ocr_timestamp_anchors_1s_sampling.csv`.
- **Duration vs elapsed**: 166 s of video = ~13.6 h (valleysprings night 1). Speed is variable: 1-8.4 min of real time per video second (median ~5.5). A test of consecutive frames shows the source images are ~5 s apart (00:38:08.21, :13.23, :18.26...), with some repeated video frames. So the mapping video second -> real time must be piecewise (use the anchor CSV), not linear.
- **Camera movement**: all four cameras change zoom and/or pan within segments (pan/zoom values are printed in the bar, so they can be logged). Hard cut between cameras. Preset tags in the bar change in sync with the clock.
- **Resolution/legibility**: 720p; bar text readable on every frame checked; fire-glow frames are overexposed in places but the bar stays legible.
- **Rights**: CC BY-NC-ND 4.0, credit "ALERTCalifornia | UC San Diego" (read at https://alertcalifornia.org/terms/ on 2026-10-18; also states commercial use requires a license from the OIC and that footage requests for media/scientists/partners/government go through the contact page; law firms use UCSD's Policy and Records Administration portal). The images-and-video page allows screen capture/sharing for public or educational use with that credit and says curated b-roll is on Photoshelter. ND means no derivatives/edits; whether embedding, re-timing or overlaying simulation layers on the footage counts as a derivative is a question for ALERTCalifornia, so **written permission is still needed** for any FireTrace redistribution, and certainly for commercial use.
- **Download**: no download is offered for the YouTube videos. I used HLS streams without cookies or login for viewing/analysis only. Photoshelter gallery content was not accessible to me. To obtain originals: use https://alertcalifornia.org/contact/ (media/scientist/partner/government route), naming the four site ids, 2026-08-03 17:00 PDT to 2026-08-04 07:00 PDT (00:00-14:00 UTC on 4 Aug), and 4 Aug 12:00-20:00 PDT.

## 4. Verified common recording interval (all four cameras, night 1)

- Local (PDT, assumed): **2026-08-03 17:47:31 -> 2026-08-04 ~00:57:39** (7 h 10 min; end is +-2 min because Southworth's last OCR sample was 00:53:31 and my eye-read at the cut was 00:57:39).
- UTC: **2026-08-04 00:47:31Z -> 07:57:39Z**.
- Limiting cameras: Golden Gate starts last (17:47:31), Southworth ends first (~00:57:39). Upper Bear's first 20 min (before ~17:25) show no smoke.
- Second window, 2 cameras only (Valley Springs + Golden Gate): 2026-08-04 12:31:29 -> 19:59:45 PDT (19:31:29Z -> 02:59:45Z on 5 Aug).
- The "interval" is the span of printed times each camera covers; it is not a guarantee that the sped-up video samples every second inside it.

## 5. FIRMS, weather, perimeters: what was actually checked

| Item | Checked | Result |
|---|---|---|
| WFIGS Interagency Perimeters (NIFC ArcGIS FeatureServer), `attr_IncidentName='Gann'`, CA | yes | **One** polygon: "Wildfire Daily Fire Perimeter", IR image interpretation, polygon time **2026-08-05 17:17 UTC** (10:17 PDT), 10,339 ac, record current 2026-08-09; discovery 2026-08-04 00:27:56Z; initial point 38.112384, -120.774225; Calaveras, CAL FIRE TCU, cause equipment/undetermined (feature says Undetermined; Cal Fire says Equipment). Attributes/geometry saved in `samples/WFIGS_Gann_polygon_attributes_and_geometry.json`. |
| Dated perimeters inside the common interval (3-4 Aug) | yes (WFIGS only) | **None found.** The only polygon is from 5 Aug, after the video interval. It must not be shown as the perimeter at 3-4 Aug times. Final perimeter vs dated: WFIGS labels it daily, not final; I did not find a separate final polygon. |
| Cal Fire incident page | yes (fire.ca.gov/incidents/2026/8/3/gann-fire) | 10,339 ac, 100% contained 12 Aug 17:50, start 08/03 5:27 PM. Timeline gives dated acreage *estimates* (no geometry): 100 ac 18:28; 250 ac 19:47; 310 ac 20:18 (03 Aug PDT); 1,800 ac 01:56; 2,100 ac 05:52; 3,000 ac 09:12; 6,495 ac 17:49 (04 Aug); 7,052 ac 02:07 (05 Aug). Page shows a map ("3D Map"), not downloaded. |
| InciWeb | **not checked** | |
| NASA FIRMS | tried API: needs a MAP_KEY (none available) | **Not retrieved.** Archive download is request/key-based; Alonso can create a free key at firms.modaps.eosdis.nasa.gov and query VIIRS SNPP/NOAA-20/21 and MODIS for bbox about -120.9,38.0,-120.6,38.3, 2026-08-03 to 08-05. Detections from VIIRS are 375 m pixels at a few overpasses per day, so they won't match every camera frame. |
| Weather, IEM ASOS (NOAA/FAA airport obs) | yes | JAQ Jackson Airport (38.374, -120.794, ~29 km N of ignition) and O22 Columbia (38.030, -120.415, ~35 km SE): hourly-ish obs, 3-5 Aug, UTC, saved as CSVs. At 00:15Z 4 Aug (17:15 PDT): JAQ 100.6 F, RH 12.6%, wind 300 deg 4 kt; O22 98.6 F, RH 10.5%, wind 6 kt gust 11. O22 winds are calm/missing at times. Nearest stations are distant and in different terrain than the fire. KCPU (San Andreas) returned no rows. |
| RAWS / Synoptic | not accessed (tokens) | |

## 6. Manifest

`manifest.json` (schema `firetrace-multicam-manifest/1`): camera ids, console URLs, coordinates with source, segments with printed start/end and 5-6 timestamp anchors each, common interval (local/UTC), time-zone evidence, rights notes, weather and perimeter references, plus compact records for the Little and Vista alternatives. Unknowns are `null`.

## 7. Samples (in `samples/`)

Only four full-frame stills (info bar left in place), one per camera near 22:00 PDT 3 Aug, captured from the public YouTube video for assessment, credit "ALERTCalifornia | UC San Diego", CC BY-NC-ND 4.0, **not cleared for redistribution beyond evaluation**. No video clips were cut because ND terms and no download offering; the compilation is also sequential so a "same real-world interval clip per camera" would be a re-edit. Also included: OCR anchor CSV, two weather CSVs, WFIGS JSON.

## 8. Alternatives

- **Best two-camera alternative: Little Fire** (Sunol Ridge 1 + Mt Allison): 14:58:12 -> 21:13:28 printed on 2026-07-21; I saw flames and burn scar from Sunol Ridge; time zone is PDT by inference from the discovery time. Missing: a third location, camera coordinates (my camera layer query was throttled with 429 errors), dated perimeter (WFIGS gave a single current daily polygon, 1,078 ac, no polygon time), FIRMS.
- **Vista Fire** (3 locations, 4 h 55 min) is weaker: unresolved 7 vs 8 July date, flames not confirmed, only final perimeter in WFIGS, coordinates not retrieved.

## 9. Not verified / open

- Time zone is inferred; smoke at 17:22 predates official 17:27 start.
- Exact end of Southworth (+-2 min) and whether the compilation drops any source frames.
- Camera coordinate uncertainty; pan convention (0 = north) assumed.
- Original-footage availability and permission (request pending, nothing sent).
- Vista analysed-video id (K67cvWlVuRU vs 0YyYO-Q_BTk) not recorded.
- FIRMS, InciWeb, RAWS not retrieved.
