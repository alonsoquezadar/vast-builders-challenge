"""Shared helpers for the vision pipeline (frame extraction, bar OCR parsing, pose assignment)."""
import hashlib, json, re, subprocess
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent.parent          # .../camera_assimilation/vision
TOOLS = HERE.parents[1]                                 # .../tools/firetrace
FPS = 30000 / 1001
W, H = 640, 360
BAR_Y0, BAR_Y1 = 345, 360                               # printed bar rows; the bar WIDTH depends on the operator label length
TS_WIDTH, CAM_WIDTH = 145, 330                          # timestamp = rightmost 145 px of the bar; camera/XYZ = leftmost 330 px
VIDEO = Path('/tmp/firevids/garnet.ogg')
SCRATCH = Path('/tmp/firetrace_vision_scratch')

# Pose definitions: planning/video-selection-shared-r1.md (approximate bounds; the printed bar decides).
POSES = {
    'G1':  dict(cameraId='delilah',  cam='delilahlookout2', x=26.27,  y=-0.70, z=1.2, sec=(0.0, 39.5)),
    'G2':  dict(cameraId='delilah',  cam='delilahlookout2', x=25.27,  y=7.34,  z=1.0, sec=(82.0, 136.0)),
    'G3b': dict(cameraId='buckrock', cam='buckrock1',       x=-39.19, y=-0.94, z=1.0, sec=(149.0, 188.0)),
    'G4':  dict(cameraId='buckrock', cam='buckrock1',       x=-26.13, y=7.89,  z=1.4, sec=(188.0, 279.7)),
}
PRINTED_RE = re.compile(r'(20\d\d)/(\d\d)/(\d\d)\s+(\d\d):(\d\d):(\d\d)[.:,](\d\d)')
XYZ_RE = re.compile(r'X:\s*([+-]?\d+\.\d+)\s*Y:\s*([+-]?\d+\.\d+)\s*Z:\s*(\d+\.\d+)')
CAM_RE = re.compile(r'(?:axis-)?(delilahlookout2|buckrock1)', re.I)


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def parse_printed(text):
    """Return ISO 'YYYY-MM-DDTHH:MM:SS.cc' or None if the OCR line is not a plausible timestamp."""
    m = PRINTED_RE.search(text.replace('O', '0'))
    if not m:
        return None
    y, mo, d, hh, mi, ss, cs = (int(g) for g in m.groups())
    if not (1 <= mo <= 12 and 1 <= d <= 31 and hh < 24 and mi < 60 and ss < 60):
        return None
    return f'{y:04d}-{mo:02d}-{d:02d}T{hh:02d}:{mi:02d}:{ss:02d}.{cs:02d}'


def parse_xyz(text):
    m = XYZ_RE.search(text)
    return tuple(float(g) for g in m.groups()) if m else None


def parse_cam(text):
    m = CAM_RE.search(text)
    return m[1].lower() if m else None


def pose_of(cam, xyz):
    """Pose id whose printed X/Y/Z matches (tolerance 0.05) for this camera, else None."""
    if not cam or not xyz:
        return None
    for pid, p in POSES.items():
        if p['cam'] == cam and abs(p['x'] - xyz[0]) < 0.05 and abs(p['y'] - xyz[1]) < 0.12 and abs(p['z'] - xyz[2]) < 0.05:
            return pid
    return None


def extract_frames(frame_numbers, outdir, fmt='png', quality=None):
    """Decode exact frame indices (0-based, decode order) with one ffmpeg pass -> outdir/f{n:05d}.{fmt}."""
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    nums = sorted(set(frame_numbers))
    todo = [n for n in nums if not (outdir / f'f{n:05d}.{fmt}').exists()]
    for i in range(0, len(todo), 400):                  # keep the select expression short
        chunk = todo[i:i + 400]
        expr = '+'.join(f'eq(n\\,{n})' for n in chunk)
        cmd = ['ffmpeg', '-v', 'error', '-i', str(VIDEO), '-vf', f'select={expr}', '-vsync', '0', '-start_number', '0',
               '-frame_pts', '0', str(outdir / f'_tmp_%05d.{fmt}')] + (['-q:v', str(quality)] if quality else [])
        subprocess.run(cmd, check=True)
        tmps = sorted(outdir.glob(f'_tmp_*.{fmt}'))
        assert len(tmps) == len(chunk), (len(tmps), len(chunk))
        for n, t in zip(chunk, tmps):
            t.rename(outdir / f'f{n:05d}.{fmt}')
    return {n: outdir / f'f{n:05d}.{fmt}' for n in nums}


def bar_end(im):
    """x where the black bar ends: rows 348-350 are pure bar background (text starts lower)."""
    import numpy as np
    strip = np.asarray(im.convert('L'))[348:351].mean(axis=0)
    x = 0
    while x < W and strip[x] < 30:
        x += 1
    return max(x, 200)


def crops(frame_path, outdir, end=None):
    """Write upscaled full-bar / timestamp / camera crops for OCR (bar width adapts per frame); return their paths."""
    im = Image.open(frame_path).convert('RGB')
    base = Path(frame_path).stem
    end = end or bar_end(im)
    paths = {}
    for name, box, k in [('bar', (0, BAR_Y0, end + 2, BAR_Y1), 4), ('ts', (max(end - TS_WIDTH, 0), BAR_Y0, end + 2, BAR_Y1), 6),
                         ('cam', (0, BAR_Y0, min(CAM_WIDTH, end), BAR_Y1), 5)]:
        c = im.crop(box); c = c.resize((c.width * k, c.height * k), Image.LANCZOS)
        p = Path(outdir) / f'{base}_{name}.png'; c.save(p); paths[name] = p
    return paths


def build_ocr_binary():
    exe = SCRATCH / 'ocr_bar'
    src = HERE / 'scripts/ocr_bar.swift'
    SCRATCH.mkdir(parents=True, exist_ok=True)
    if not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
        subprocess.run(['swiftc', '-O', str(src), '-o', str(exe)], check=True, capture_output=True)
    return exe


def run_ocr(exe, paths):
    """Return {path: [lines]} (batched to avoid arg-length limits)."""
    from concurrent.futures import ThreadPoolExecutor
    out = {}
    paths = [str(p) for p in paths]
    batches = [paths[i:i + 40] for i in range(0, len(paths), 40)]
    with ThreadPoolExecutor(4) as ex:
        for res in ex.map(lambda b: subprocess.run([str(exe)] + b, check=True, capture_output=True, text=True).stdout, batches):
            for line in res.splitlines():
                row = json.loads(line)
                out[row['path']] = [l['text'] for l in row.get('lines', [])]
    return out


def read_rows(numbers, pts):
    """OCR the printed bar of the given decode-order frames; one row per frame (see ocr_timeline.py for the method)."""
    files = extract_frames(numbers, SCRATCH / 'frames_png', 'png')
    cropdir = SCRATCH / 'crops'; cropdir.mkdir(parents=True, exist_ok=True)
    exe = build_ocr_binary()
    # the bar width is constant within a pose (same operator label); on dark/night frames the edge detector
    # runs off the frame (>=600), so those frames inherit the last valid width from the previous frame.
    ends, last = {}, None
    for n in numbers:
        e = bar_end(Image.open(files[n]).convert('RGB'))
        if e < 600: last = e
        ends[n] = e if e < 600 else last
    first = next((e for e in ends.values() if e), 470)
    allcrops = {n: crops(files[n], cropdir, ends[n] or first) for n in numbers}
    reads = run_ocr(exe, [p for c in allcrops.values() for p in c.values()])
    rows = []
    for n in numbers:
        c = allcrops[n]
        full, ts, cam = (' '.join(reads.get(str(c[k]), [])) for k in ('bar', 'ts', 'cam'))
        t_full, t_ts = parse_printed(full), parse_printed(ts)
        xyz = parse_xyz(full) or parse_xyz(cam)
        camid = parse_cam(full) or parse_cam(cam)
        agree = t_full is not None and (t_full == t_ts or (t_ts is not None and t_full[:-3] == t_ts[:-3]))
        rows.append({
            'frame': n, 'videoSecond': round(pts[n], 3), 'rawFull': full, 'rawTimestampCrop': ts, 'rawCamCrop': cam,
            'printedTime': t_full if agree else None, 'timeReadsAgree': agree,
            'xyz': list(xyz) if xyz else None, 'xyzReadsAgree': bool(xyz and xyz == parse_xyz(cam)),
            'camera': camid, 'pose': pose_of(camid, xyz) if agree else None})
    return rows
