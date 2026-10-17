"""British English presentation copies; recorded evidence and numerical data stay unchanged."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

CATALOGUE = json.loads((Path(__file__).parent / 'locales/en-GB.json').read_text())
FRAGMENTS = sorted(CATALOGUE.items(), key=lambda item: len(item[0]), reverse=True)
SPANISH = re.compile(r'[áéíóúñ¿¡]|\b(?:debe|requiere|fuente|modelo|fuego|hora|sin|con|para|desde|donde|pendiente|tiene|necesita|del|una|está|las|los|no |el |la |falta|requerido|coincidencia|exceso|defecto|recibo|prensa|bundle de|° por)', re.I)
PRINTF = re.compile(r'%(?:\.\d+)?[sdf]')


def _template(source, target):
    parts = PRINTF.split(source)
    slots = PRINTF.findall(source)
    if not slots:
        return None
    pattern = re.compile('^' + '(.*?)'.join(re.escape(p) for p in parts) + '$', re.S)
    return pattern, PRINTF.split(target)


TEMPLATES = [t for source, target in FRAGMENTS if (t := _template(source, target))]


@lru_cache(maxsize=4096)
def translate_text(text):
    """Translate known copy or formatted messages, without changing unknown source material."""
    if text in CATALOGUE:
        return CATALOGUE[text]
    if not SPANISH.search(text):
        return text
    for pattern, parts in TEMPLATES:
        match = pattern.fullmatch(text)
        if match:
            return ''.join(piece for pair in zip(parts, (*match.groups(), '')) for piece in pair)
    for source, target in FRAGMENTS:
        if source in text:
            text = text.replace(source, target)
    return text


def localise_payload(value):
    """Create an English display payload. Never mutate a loaded or hash-checked source object."""
    if isinstance(value, str):
        return translate_text(value)
    if isinstance(value, list):
        return [localise_payload(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: localise_payload(item) for key, item in value.items()}
    content = value.get('content')
    if isinstance(content, str) and content not in CATALOGUE:
        result['content'] = content
    if isinstance(content, str) and result.get('content') != content:
        result['translationNote'] = 'British English display translation of a model response. The original evidence has not been rewritten; the translation does not correct the model claims.'
        result['translation'] = {
            'locale': 'en-GB', 'sourceLanguage': 'es' if re.search(r'[áéíóúñ¿¡]|\b(?:imagen|muestra|esta|captura|incendio|llamas)\b', content, re.I) else 'en',
            'method': 'reviewable-display-catalogue',
            'originalContentSha256': hashlib.sha256(content.encode()).hexdigest()
        }
    return result
