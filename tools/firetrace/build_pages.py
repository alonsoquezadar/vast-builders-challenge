"""Export the reviewed FireTrace replay and hourly model results for static hosting.

Run with the requirements in requirements-forecast.txt installed:
    python3 tools/firetrace/build_pages.py --output /tmp/firetrace-pages
Only the explicit public asset list below is copied; no server config is exported.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from incident_bundle import load_incident
from localisation import localise_payload
from reconstruction_forecast import forecast, load_sources
from satellite_bundle import FILES, load_satellite

ROOT = Path(__file__).parent.resolve()
ASSETS = ['firetrace.html', 'firetrace.js', 'firetrace.css', 'firetrace_model.mjs',
          'tour.js', 'tour.css', 'data-client.mjs', 'camera-player.js', 'video-clock.mjs']


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def build(output):
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Choose an empty output directory to avoid overwriting other files.')
    output.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        shutil.copyfile(ROOT / name, output / name)
    html = (output / 'firetrace.html').read_text().replace('<html lang="en-GB">', '<html lang="en-GB" data-deployment="static">')
    (output / 'firetrace.html').write_text(html)
    (output / 'index.html').write_text(html)
    (output / '.nojekyll').touch()
    for layer in FILES:
        write_json(output / 'data' / f'{layer}.json', localise_payload(load_satellite(layer)))
    incident = load_incident(ROOT / 'evidence/garnet')
    write_json(output / 'data/incident.json', localise_payload(incident))
    public_media = {frame['imagePath'] for frame in incident['frames']}
    public_media.update(camera['clipPath'] for camera in incident['cameras'])
    for relative in public_media:
        source = (ROOT / relative).resolve()
        source.relative_to(ROOT / 'evidence/garnet')
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    sources = load_sources()
    # All three horizons must be covered by the saved hourly weather.
    first = int((sources.first_t + 3599) // 3600 * 3600)
    end = min(int(datetime(2025, 9, 12, 23, tzinfo=timezone.utc).timestamp()), max(sources.weather) - 23 * 3600)
    times = []
    for stamp in range(first, end + 1, 3600):
        utc = datetime.fromtimestamp(stamp, timezone.utc).isoformat().replace('+00:00', 'Z')
        for horizon in (6, 12, 24):
            value = forecast({'timeUtc': utc, 'horizonHours': horizon}, sources=sources)
            write_json(output / 'data/projections' / f'{stamp}-{horizon}.json', localise_payload(value))
        times.append(stamp)
        if len(times) % 48 == 0:
            print(f'Exported {len(times)} hourly starting times', flush=True)
    if not times:
        raise ValueError('No covered hourly projection times were found.')
    write_json(output / 'data/projections.json', {'times': times, 'horizons': [6, 12, 24],
               'mode': 'saved-hourly-projections', 'validated': False})
    manifest = {str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(output.rglob('*')) if path.is_file()}
    write_json(output / 'build-manifest.json', {'sha256': manifest, 'projectionCount': len(times) * 3})
    print(f'Built {len(manifest)} public assets and {len(times) * 3} projections in {output}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
