"""Decode every video frame (decode order, no cfr duplication; pts from ffprobe) of the original garnet.ogg and group runs of identical source images.

The compilation is a timelapse with irregular cadence; video seconds are NOT a clock. This scan only
finds where the pixels (outside the printed bar) change, so later OCR can read the printed time of each
distinct source image. Run with -I:  python3 -I scripts/scan_frames.py [video] [out.json]
"""
import hashlib, json, subprocess, sys
from pathlib import Path
import numpy as np

W, H, BAR_Y = 640, 360, 338
HERE = Path(__file__).resolve().parent.parent
video = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/firevids/garnet.ogg')
out = Path(sys.argv[2] if len(sys.argv) > 2 else HERE / 'data/frame_scan.json')

proc = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', str(video), '-an', '-vsync', '0', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                        stdout=subprocess.PIPE)
frames, prev = [], None
n = 0
while True:
    buf = proc.stdout.read(W * H)
    if len(buf) < W * H:
        break
    img = np.frombuffer(buf, np.uint8).reshape(H, W).astype(np.int16)
    scene, bar = img[:BAR_Y], img[BAR_Y:]
    if prev is None:
        frames.append((n, 255.0, 255.0))
    else:
        frames.append((n, float(np.abs(scene - prev[0]).mean()), float(np.abs(bar - prev[1]).mean())))
    prev = (scene, bar)
    n += 1
proc.wait()
pts = [float(x) for x in subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','frame=pts_time','-of','csv=p=0',str(video)],capture_output=True,text=True,check=True).stdout.split()]
assert len(pts) == n, (len(pts), n)

fps = 30000 / 1001
# a new source image = scene or bar changes more than the codec-noise floor
THR = 0.35
runs, start = [], 0
for i, (_, ds, db) in enumerate(frames):
    if i > 0 and (ds > THR or db > THR):
        runs.append((start, i - 1)); start = i
runs.append((start, n - 1))
result = {
    'schema': 'firetrace-vision-frame-scan-v1',
    'video': str(video), 'videoSha256': hashlib.sha256(video.read_bytes()).hexdigest(),
    'fps': fps, 'decodedFrames': n, 'changeThresholdMeanAbsDiff': THR,
    'note': 'runs = consecutive decoded frames whose pixels differ by <= threshold; each run is one distinct source image (or a codec-noise-only repeat).',
    'framePtsSeconds': pts,
    'runs': [{'firstFrame': a, 'lastFrame': b, 'startSecond': pts[a], 'endSecond': pts[min(b + 1, n - 1)]} for a, b in runs],
    'perFrameDiff': [[round(a, 3), round(b, 3)] for _, a, b in frames],
}
out.write_text(json.dumps(result, separators=(',', ':')) + '\n')
lens = [b - a + 1 for a, b in runs]
print(f'decoded {n} frames, {len(runs)} distinct runs; run length frames min/median/max = {min(lens)}/{int(np.median(lens))}/{max(lens)}')
