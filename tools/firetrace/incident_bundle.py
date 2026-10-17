"""Load the reviewed Garnet replay and bind model outputs to exact image bytes."""
import hashlib
import json
from pathlib import Path


def load_incident(directory):
    directory = Path(directory)
    bundle = json.loads((directory / 'manifest.json').read_text())
    for frame in bundle['frames']:
        image = directory / Path(frame['imagePath']).name
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        if digest != frame['imageSha256']:
            raise ValueError('El fotograma no coincide con el manifiesto revisado.')
        saved = directory / frame['analysisPath']
        analysis = json.loads(saved.read_text()) if saved.is_file() else None
        verified = bool(analysis and analysis.get('imageSha256') == digest)
        frame['analysis'] = analysis if verified else None
        frame['analysisIntegrity'] = 'matched' if verified else 'unavailable-or-mismatched'
        frame.pop('analysisPath', None)
    return bundle
