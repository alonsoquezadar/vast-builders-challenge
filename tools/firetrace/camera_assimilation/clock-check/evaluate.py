"""Compare agent-transcribed current overlays with their independent public catalog receipts."""
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path

ROOT=Path(__file__).parent
TRANSCRIBED={
 'Axis-DelilahLookout2':{'printedTime':'2026-10-17T07:21:13.54','xDeg':-51.99,'yDeg':-4.89,'zoom':1.0},
 'Axis-BuckRock1':{'printedTime':'2026-10-17T07:20:39.43','xDeg':-58.26,'yDeg':-7.35,'zoom':1.0},
}

def build():
 data=json.loads((ROOT/'receipt.json').read_text());results=[]
 for row in data['records']:
  transcription=TRANSCRIBED[row['cameraId']];props=row['catalog']['properties']
  assumed=datetime.fromisoformat(transcription['printedTime']).replace(tzinfo=timezone(timedelta(hours=-7)))
  printed_yaw=transcription['xDeg']%360
  residual=(props['az_current']-printed_yaw+180)%360-180
  results.append({'cameraId':row['cameraId'],'transcription':transcription,'reviewStatus':'agent-read-not-operator-reviewed',
   'clockUnderPdtErrorSeconds':round(assumed.timestamp()-props['last_frame_ts'],3),
   'printedXWrappedDeg':printed_yaw,'catalogAzimuthDeg':props['az_current'],'azimuthResidualDeg':round(residual,3)})
 return {'scope':'current frames on 2026-10-17 only','historicalClockVerified':False,'historicalPoseVerified':False,'results':results,
  'limitations':['One pose per camera cannot validate a motion/zoom transfer function.',
  'A current clock match does not prove historical camera configuration.',
  'Public catalog azimuth is an external consistency check, not a surveyed ground-truth calibration.']}

if __name__=='__main__':
 data=build();(ROOT/'comparison.json').write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(data))
