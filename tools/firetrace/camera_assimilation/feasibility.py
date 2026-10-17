"""Reproduce temporal coverage; this does not establish camera/satellite correspondence."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSES = [
    dict(id='G1', cameraId='delilah', videoStart=0, videoEnd=39.5, printedStart='10:30', printedEnd='13:44', zoom=1.2),
    dict(id='G2', cameraId='delilah', videoStart=82, videoEnd=136, printedStart='16:11', printedEnd='20:16', zoom=1.0),
    dict(id='G3', cameraId='buckrock', videoStart=137, videoEnd=148, printedStart='10:32', printedEnd='10:41', zoom=1.0),
    dict(id='G3b', cameraId='buckrock', videoStart=149, videoEnd=188, printedStart='11:27', printedEnd='13:59', zoom=1.0),
    dict(id='G4', cameraId='buckrock', videoStart=188, videoEnd=279.6, printedStart='14:08', printedEnd='20:54', zoom=1.4),
]
CAMERAS = {'delilah': [-119.1175,36.80417], 'buckrock': [-118.86067,36.73727]}


def bearing(origin, target):
    lon,lat = map(math.radians,origin)
    x,y = map(math.radians,target)
    return math.degrees(math.atan2(math.sin(x-lon)*math.cos(y), math.cos(lat)*math.sin(y)-math.sin(lat)*math.cos(y)*math.cos(x-lon))) % 360


def build():
    directory = ROOT/'evidence/garnet/satellite'
    overpasses = json.loads((directory/'overpasses.json').read_text())['overpasses']
    hotspots = json.loads((directory/'hotspots.geojson').read_text())['features']
    result = {'schema':'firetrace-camera-feasibility-v1', 'date':'2025-08-27',
              'clockStatus':'PDT-hypothesis-not-verified', 'positionStatus':'candidate',
              'poseBoundsSource':'planning/video-selection-shared-r1.md; minute bounds approximate, OCR must check each frame',
              'inputs':{name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in ['overpasses.json','hotspots.geojson']},
              'poses':POSES, 'hypotheses':{}}
    for label,offset in [('PDT',-7),('PST',-8),('UTC',0)]:
        rows=[]
        for pose in POSES:
            start=datetime.fromisoformat('2025-08-27T'+pose['printedStart']).replace(tzinfo=timezone(timedelta(hours=offset)))
            end=datetime.fromisoformat('2025-08-27T'+pose['printedEnd']).replace(tzinfo=start.tzinfo)
            selected=[]
            for row in overpasses:
                stamp=datetime.fromisoformat(row['acquiredUtc'].replace('Z','+00:00'))
                if start <= stamp <= end:
                    points=[f for f in hotspots if f['properties']['t']==row['t'] and f['properties']['source']==row['source']]
                    angles=[bearing(CAMERAS[pose['cameraId']],f['geometry']['coordinates']) for f in points]
                    selected.append({**row,'printedTimeHypothesis':stamp.astimezone(start.tzinfo).isoformat(),
                                     'centroidBearingDeg':bearing(CAMERAS[pose['cameraId']],row['centroid']),
                                     'pointBearingMinDeg':min(angles) if angles else None,'pointBearingMaxDeg':max(angles) if angles else None})
            rows.append({'poseId':pose['id'],'cameraId':pose['cameraId'],'passes':selected,
                         'hasTemporalHoldout':len({r['t'] for r in selected})>=2})
        result['hypotheses'][label]=rows
    result['adjacentDayPasses']=[r for r in overpasses if r['acquiredPdt'][:10] in ['2025-08-26','2025-08-28']]
    result['limitations']=[
        'Temporal overlap is necessary but not proof a camera smoke base corresponds to a satellite hotspot.',
        'A centroid of a multi-front fire is not a measured smoke base. Preserve clusters and angular extent.',
        'One matched direction cannot identify yaw and FOV together; fix FOV to an explicit prior unless additional spread identifies it.',
        'Camera footage covers August 27 only; adjacent-day passes cannot calibrate this video directly.',
        'Under PDT G1 and G3b permit temporal holdouts; Delilah G2 has no exact pass and cannot inherit G1 pose calibration unchecked.',
        'Both cameras can be explored together during G1/G3b, but synchrony and same-plume identity remain unverified.',
        'All arrival reconstruction uses final footprint and future support: retrospective initialization must disclose leakage; validate against held-out observed detections, not reconstructed daily truth.',
        'Camera cadence is irregular; this video cannot substantiate minute-by-minute corrections. Satellite cadence is actual overpass availability, not fixed twice daily.'
    ]
    return result

if __name__=='__main__':
    output=build()
    (Path(__file__).parent/'feasibility.json').write_text(json.dumps(output,indent=2)+'\n')
    for hypothesis,rows in output['hypotheses'].items():
        print(hypothesis, [(r['poseId'],len(r['passes']),r['hasTemporalHoldout']) for r in rows])
